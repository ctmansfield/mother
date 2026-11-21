"""Stream an Apple Health XML or ZIP without extracting members to disk."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
import stat
from struct import unpack_from
import unicodedata
from xml.parsers import expat
from zipfile import (
    ZIP_DEFLATED,
    ZIP_STORED,
    ZipFile,
    _ECD_ENTRIES_TOTAL,
    _ECD_LOCATION,
    _ECD_SIGNATURE,
    _ECD_SIZE,
    _EndRecData,
    sizeEndCentDir64,
    sizeEndCentDir64Locator,
    stringEndArchive64,
)

from .files import CHUNK, InvalidHistory, LimitKind, NamedHistoryLimit, hash_stream

BP_TYPE = "HKCorrelationTypeIdentifierBloodPressure"
BP_TYPES = {
    "HKQuantityTypeIdentifierBloodPressureSystolic": "systolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "diastolic",
}


DEFAULT_ZIP_MEMBERS = 4096
MAX_ZIP_MEMBERS = 25_000
CENTRAL_HEADER_BYTES = 46
CENTRAL_LENGTHS_OFFSET = 28


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 4 * 1024**3
    expanded_bytes: int = 8 * 1024**3
    member_bytes: int = 4 * 1024**3
    members: int = DEFAULT_ZIP_MEMBERS
    directory_bytes: int = 4 * 1024**2
    ratio: int = 2000
    xml_depth: int = 32
    xml_dtd_bytes: int = 128 * 1024
    xml_token_bytes: int = 256 * 1024
    top_level_rows: int = 30_000_000
    total_xml_elements: int = 90_000_000
    type_buckets: int = 4096

    def __post_init__(self):
        if any(type(value) is not int or value <= 0 for value in vars(self).values()):
            raise ValueError("history limits must be positive integers")
        if self.members > MAX_ZIP_MEMBERS:
            raise ValueError("history member limit exceeds hard ceiling")


def _forbidden(*_):
    raise InvalidHistory("unsupported XML declaration")


def _safe_name(name):
    path = PurePosixPath(name.rstrip("/"))
    if (
        not path.parts
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
        or "\\" in name
        or ":" in name
        or len(name.encode("utf-8")) > 4096
        or any(not char.isprintable() for char in name)
    ):
        raise InvalidHistory("unsafe ZIP member name")
    return unicodedata.normalize("NFC", path.as_posix()).casefold()


def _kind(tag, source_type):
    if tag == "Record":
        if source_type.startswith("HKQuantityTypeIdentifier"):
            return "quantity"
        if source_type.startswith("HKCategoryTypeIdentifier"):
            return "category"
        if source_type.startswith("HKClinicalTypeIdentifier"):
            return "clinical"
        return "record_other"
    return {
        "Correlation": "correlation",
        "Me": "characteristics",
        "Workout": "workout",
        "ActivitySummary": "activity",
        "Audiogram": "audiogram",
        "Electrocardiogram": "ecg",
        "ClinicalRecord": "clinical",
        "MedicationRecord": "medication",
        "HeartbeatSeries": "series",
        "WorkoutStatistics": "workout",
        "WorkoutEvent": "workout",
        "FileReference": "attachment_reference",
        "WorkoutRoute": "route",
        "VisionPrescription": "vision",
        "Medication": "medication",
        "ExportDate": "export_metadata",
    }.get(tag, "other")


def _scan_xml(
    stream,
    member_index,
    limits,
    on_row,
    on_nested,
    on_event=None,
    on_bytes=None,
    health_data=True,
):
    parser = expat.ParserCreate()
    parser.specified_attributes = True
    parser.ordered_attributes = on_event is not None
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.EntityDeclHandler = _forbidden
    parser.ExternalEntityRefHandler = _forbidden
    parser.UnparsedEntityDeclHandler = _forbidden
    parser.NotationDeclHandler = _forbidden
    cursor = 0
    depth = 0
    ordinal = 0
    elements = 0
    pending = None
    child_ordinal = 0
    root_seen = False
    dtd_start = None

    def emit(kind, data):
        if on_event is not None:
            occurrence = ordinal + 1 if depth >= 2 else 0
            on_event(member_index, occurrence, depth, kind, data)

    def doctype(name, system, public, _internal_subset):
        nonlocal dtd_start
        # Apple exports may carry an inline grammar. No DTD entity or external
        # resolution is needed to interpret source records.
        if (
            (health_data and name != "HealthData")
            or system is not None
            or public is not None
        ):
            _forbidden()
        dtd_start = parser.CurrentByteIndex
        emit("doctype", [name, bool(_internal_subset)])

    def check_dtd(position):
        if dtd_start is not None and position - dtd_start > limits.xml_dtd_bytes:
            raise NamedHistoryLimit(
                LimitKind.XML_DTD, "inline HealthData DTD limit exceeded"
            )

    def end_doctype():
        nonlocal dtd_start
        check_dtd(parser.CurrentByteIndex)
        dtd_start = None

    def attlist(_element, _attribute, _type, default, _required):
        if default is not None:
            _forbidden()

    def start(tag, attrs):
        nonlocal depth, pending, root_seen, elements, child_ordinal
        elements += 1
        if elements > limits.total_xml_elements:
            raise NamedHistoryLimit(
                LimitKind.XML_ELEMENTS, "XML total element limit exceeded"
            )
        depth += 1
        pairs = None
        if on_event is not None:
            pairs = list(zip(attrs[::2], attrs[1::2]))
            attrs = dict(pairs)
        if depth > 2 and on_nested is not None:
            source_type = attrs.get("type", "")
            on_nested(_kind(tag, source_type), source_type or tag)
        if depth > limits.xml_depth:
            raise NamedHistoryLimit(LimitKind.XML_DEPTH, "XML depth limit exceeded")
        if sum(len(k) + len(v) for k, v in attrs.items()) > limits.xml_token_bytes:
            raise NamedHistoryLimit(LimitKind.XML_TOKEN, "XML attribute limit exceeded")
        emit("start", [tag, pairs])
        if depth == 1:
            if health_data and tag != "HealthData":
                raise InvalidHistory("expected Apple HealthData root")
            root_seen = True
        elif depth == 2:
            pending = [tag, attrs, []]
            child_ordinal = 0
        elif (
            health_data
            and depth == 3
            and pending[0] == "Correlation"
            and pending[1].get("type") == BP_TYPE
        ):
            if len(pending[2]) >= 16:
                raise NamedHistoryLimit(
                    LimitKind.XML_CHILDREN,
                    "blood pressure correlation component limit exceeded",
                )
            child_ordinal += 1
            pending[2].append((child_ordinal, tag, attrs))

    def end(tag):
        nonlocal depth, ordinal, pending
        emit("end", tag)
        if depth == 2:
            ordinal += 1
            if ordinal > limits.top_level_rows:
                raise NamedHistoryLimit(
                    LimitKind.XML_ROWS, "HealthData row limit exceeded"
                )
            tag, attrs, children = pending
            source_type = attrs.get("type", "")
            on_row(
                member_index,
                ordinal,
                _kind(tag, source_type),
                source_type,
                tag,
                attrs,
                children,
            )
            pending = None
        depth -= 1

    parser.StartDoctypeDeclHandler = doctype
    parser.EndDoctypeDeclHandler = end_doctype
    parser.AttlistDeclHandler = attlist
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    if on_event is not None:
        parser.CharacterDataHandler = lambda data: emit("text", data)
        parser.CommentHandler = lambda data: emit("comment", data)
        parser.ProcessingInstructionHandler = lambda tag, data: emit(
            "processing_instruction", [tag, data]
        )
        parser.XmlDeclHandler = lambda *parts: emit("xml_declaration", list(parts))
        parser.StartCdataSectionHandler = lambda: emit("cdata_start", None)
        parser.EndCdataSectionHandler = lambda: emit("cdata_end", None)
    hashing = sha256()
    try:
        while chunk := stream.read(CHUNK):
            cursor += len(chunk)
            if cursor > limits.member_bytes:
                raise NamedHistoryLimit(
                    LimitKind.ZIP_MEMBER_BYTES, "XML member limit exceeded"
                )
            hashing.update(chunk)
            if on_bytes is not None:
                on_bytes(member_index, chunk)
            parser.Parse(chunk, False)
            check_dtd(cursor)
            if cursor - parser.CurrentByteIndex > limits.xml_token_bytes:
                raise NamedHistoryLimit(LimitKind.XML_TOKEN, "XML token limit exceeded")
        parser.Parse(b"", True)
    except expat.ExpatError:
        raise InvalidHistory("invalid HealthData XML") from None
    if not root_seen:
        raise InvalidHistory("HealthData XML is empty")
    return hashing.hexdigest(), cursor


def _check_zip_directory(stream, directory, limits):
    declared = directory[_ECD_ENTRIES_TOTAL]
    size = directory[_ECD_SIZE]
    if declared > limits.members:
        raise NamedHistoryLimit(LimitKind.ZIP_MEMBERS, "ZIP member count exceeded")
    if size > limits.directory_bytes:
        raise NamedHistoryLimit(
            LimitKind.ZIP_DIRECTORY, "ZIP directory bounds exceeded"
        )

    end = directory[_ECD_LOCATION]
    if directory[_ECD_SIGNATURE] == stringEndArchive64:
        # Older Python leaves the location at the conventional end record.
        # Newer Python gives the actual ZIP64 record, including any extension.
        stream.seek(end)
        if stream.read(4) != stringEndArchive64:
            end -= sizeEndCentDir64 + sizeEndCentDir64Locator
    start = end - size
    if start < 0:
        raise InvalidHistory("invalid ZIP directory offset")

    # Count actual central records before ZipFile creates one ZipInfo per row.
    # The end-record count is attacker-controlled and cannot bound allocations.
    offset = start
    count = 0
    while offset < end:
        if end - offset < CENTRAL_HEADER_BYTES:
            raise InvalidHistory("truncated ZIP directory")
        stream.seek(offset)
        header = stream.read(CENTRAL_HEADER_BYTES)
        if len(header) != CENTRAL_HEADER_BYTES or not header.startswith(b"PK\x01\x02"):
            raise InvalidHistory("invalid ZIP directory entry")
        offset += CENTRAL_HEADER_BYTES + sum(
            unpack_from("<HHH", header, CENTRAL_LENGTHS_OFFSET)
        )
        count += 1
        if count > limits.members:
            raise NamedHistoryLimit(LimitKind.ZIP_MEMBERS, "ZIP member count exceeded")
    if offset != end or count != declared:
        raise InvalidHistory("ZIP directory size or member count mismatch")
    return count, size


def scan(
    stream, limits, on_row, on_member, on_nested=None, *, on_event=None, on_bytes=None
):
    """Read an already-open, stable local file and return its exact byte identity."""
    stream.seek(0)
    original = hash_stream(stream, limits.archive_bytes, kind=LimitKind.ARCHIVE_BYTES)
    stream.seek(0)
    directory = _EndRecData(stream)
    if directory is None:
        stream.seek(0)
        member = _scan_xml(stream, 1, limits, on_row, on_nested, on_event, on_bytes)
        if member != original:
            raise InvalidHistory("original changed during inventory")
        on_member(1, None, "healthdata_xml", *member)
        return original
    _check_zip_directory(stream, directory, limits)
    stream.seek(0)
    with ZipFile(stream) as archive:
        infos = archive.infolist()
        if len(infos) > limits.members:
            raise NamedHistoryLimit(LimitKind.ZIP_MEMBERS, "ZIP member count exceeded")
        expanded = 0
        names = set()
        main_count = 0
        for info in infos:
            key = _safe_name(info.orig_filename)
            if key in names:
                raise InvalidHistory("duplicate or equivalent ZIP member path")
            names.add(key)
            mode = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir():
                if mode not in {0, stat.S_IFDIR} or info.file_size:
                    raise InvalidHistory("unsupported ZIP directory entry")
            else:
                if (
                    mode not in {0, stat.S_IFREG}
                    or info.flag_bits & 1
                    or info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}
                ):
                    raise InvalidHistory("unsupported ZIP member encoding or type")
                if info.file_size > limits.member_bytes:
                    raise NamedHistoryLimit(
                        LimitKind.ZIP_MEMBER_BYTES, "ZIP member size exceeded"
                    )
                if info.file_size > max(1, info.compress_size) * limits.ratio:
                    raise NamedHistoryLimit(
                        LimitKind.ZIP_RATIO, "ZIP member ratio exceeded"
                    )
                expanded += info.file_size
                if expanded > limits.expanded_bytes:
                    raise NamedHistoryLimit(
                        LimitKind.ZIP_EXPANDED, "ZIP expanded byte limit exceeded"
                    )
                if key.rsplit("/", 1)[-1] == "export.xml":
                    main_count += 1
        if main_count > 1:
            raise InvalidHistory("ambiguous HealthData XML members")
        for index, info in enumerate(infos, 1):
            if info.is_dir():
                on_member(index, info.filename, "directory", sha256(b"").hexdigest(), 0)
                continue
            kind = (
                "healthdata_xml"
                if info.filename.rsplit("/", 1)[-1].casefold() == "export.xml"
                else "attachment"
            )
            if (
                on_event is not None
                and kind == "attachment"
                and info.filename.casefold().endswith(".xml")
            ):
                kind = "source_xml"
            with archive.open(info) as member:
                if (
                    on_event is not None
                    and kind == "attachment"
                    and info.filename.casefold().endswith(".gpx")
                ):
                    probe = member.read(4096)
                    member.seek(0)
                    if probe.startswith((b"\xff\xfe", b"\xfe\xff")):
                        xml_prefix = (
                            probe.decode("utf-16", errors="replace")
                            .lstrip()
                            .startswith("<")
                        )
                    else:
                        xml_prefix = probe.startswith((b"<\x00", b"\x00<")) or (
                            probe.removeprefix(b"\xef\xbb\xbf")
                            .lstrip()
                            .startswith(b"<")
                        )
                    if xml_prefix:
                        kind = "source_xml"
                if kind in ("healthdata_xml", "source_xml"):

                    def report(
                        index, ordinal, family, source_type, tag, attrs, children
                    ):
                        if kind == "source_xml":
                            family = "auxiliary_xml"
                        on_row(
                            index, ordinal, family, source_type, tag, attrs, children
                        )

                    result = _scan_xml(
                        member,
                        index,
                        limits,
                        report,
                        on_nested,
                        on_event,
                        on_bytes,
                        health_data=kind == "healthdata_xml",
                    )
                else:
                    result = hash_stream(
                        member,
                        limits.member_bytes,
                        kind=LimitKind.ZIP_MEMBER_BYTES,
                        on_chunk=(
                            None
                            if on_bytes is None
                            else lambda raw: on_bytes(index, raw)
                        ),
                    )
            if result[1] != info.file_size:
                raise InvalidHistory("ZIP member length mismatch")
            on_member(index, info.filename, kind, *result)
    stream.seek(0)
    if (
        hash_stream(stream, limits.archive_bytes, kind=LimitKind.ARCHIVE_BYTES)
        != original
    ):
        raise InvalidHistory("original changed during inventory")
    return original
