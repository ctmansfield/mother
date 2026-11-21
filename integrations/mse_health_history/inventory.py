"""Stream an Apple Health XML or ZIP without extracting members to disk."""

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePosixPath
import stat
import unicodedata
from xml.parsers import expat
from zipfile import (
    ZIP_DEFLATED,
    ZIP_STORED,
    ZipFile,
    _ECD_ENTRIES_TOTAL,
    _ECD_SIZE,
    _EndRecData,
)

from .files import CHUNK, InvalidHistory, hash_stream

BP_TYPE = "HKCorrelationTypeIdentifierBloodPressure"
BP_TYPES = {
    "HKQuantityTypeIdentifierBloodPressureSystolic": "systolic",
    "HKQuantityTypeIdentifierBloodPressureDiastolic": "diastolic",
}


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 4 * 1024**3
    expanded_bytes: int = 8 * 1024**3
    member_bytes: int = 4 * 1024**3
    members: int = 4096
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


def _scan_xml(stream, member_index, limits, on_row, on_nested):
    parser = expat.ParserCreate()
    parser.specified_attributes = True
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
    root_seen = False
    dtd_start = None

    def doctype(name, system, public, _internal_subset):
        nonlocal dtd_start
        # Apple exports may carry an inline grammar. No DTD entity or external
        # resolution is needed to interpret source records.
        if name != "HealthData" or system is not None or public is not None:
            _forbidden()
        dtd_start = parser.CurrentByteIndex

    def check_dtd(position):
        if dtd_start is not None and position - dtd_start > limits.xml_dtd_bytes:
            raise InvalidHistory("inline HealthData DTD limit exceeded")

    def end_doctype():
        nonlocal dtd_start
        check_dtd(parser.CurrentByteIndex)
        dtd_start = None

    def attlist(_element, _attribute, _type, default, _required):
        if default is not None:
            _forbidden()

    def start(tag, attrs):
        nonlocal depth, pending, root_seen, elements
        elements += 1
        if elements > limits.total_xml_elements:
            raise InvalidHistory("XML total element limit exceeded")
        depth += 1
        if depth > 2 and on_nested is not None:
            source_type = attrs.get("type", "")
            on_nested(_kind(tag, source_type), source_type or tag)
        if depth > limits.xml_depth:
            raise InvalidHistory("XML depth limit exceeded")
        if sum(len(k) + len(v) for k, v in attrs.items()) > limits.xml_token_bytes:
            raise InvalidHistory("XML attribute limit exceeded")
        if depth == 1:
            if tag != "HealthData":
                raise InvalidHistory("expected Apple HealthData root")
            root_seen = True
        elif depth == 2:
            pending = [tag, attrs, []]
        elif (
            depth == 3
            and pending[0] == "Correlation"
            and pending[1].get("type") == BP_TYPE
        ):
            if len(pending[2]) >= 16:
                raise InvalidHistory(
                    "blood pressure correlation component limit exceeded"
                )
            pending[2].append((tag, attrs))

    def end(_tag):
        nonlocal depth, ordinal, pending
        if depth == 2:
            ordinal += 1
            if ordinal > limits.top_level_rows:
                raise InvalidHistory("HealthData row limit exceeded")
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
    hashing = sha256()
    try:
        while chunk := stream.read(CHUNK):
            cursor += len(chunk)
            if cursor > limits.member_bytes:
                raise InvalidHistory("XML member limit exceeded")
            hashing.update(chunk)
            parser.Parse(chunk, False)
            check_dtd(cursor)
            if cursor - parser.CurrentByteIndex > limits.xml_token_bytes:
                raise InvalidHistory("XML token limit exceeded")
        parser.Parse(b"", True)
    except expat.ExpatError:
        raise InvalidHistory("invalid HealthData XML") from None
    if not root_seen:
        raise InvalidHistory("HealthData XML is empty")
    return hashing.hexdigest(), cursor


def scan(stream, limits, on_row, on_member, on_nested=None):
    """Read an already-open, stable local file and return its exact byte identity."""
    stream.seek(0)
    original = hash_stream(stream, limits.archive_bytes)
    stream.seek(0)
    directory = _EndRecData(stream)
    if directory is None:
        stream.seek(0)
        member = _scan_xml(stream, 1, limits, on_row, on_nested)
        if member != original:
            raise InvalidHistory("original changed during inventory")
        on_member(1, None, "healthdata_xml", *member)
        return original
    if (
        directory[_ECD_ENTRIES_TOTAL] > limits.members
        or directory[_ECD_SIZE] > limits.directory_bytes
    ):
        raise InvalidHistory("ZIP directory bounds exceeded")
    stream.seek(0)
    with ZipFile(stream) as archive:
        infos = archive.infolist()
        if len(infos) > limits.members:
            raise InvalidHistory("ZIP member count exceeded")
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
                if (
                    info.file_size > limits.member_bytes
                    or info.file_size > max(1, info.compress_size) * limits.ratio
                ):
                    raise InvalidHistory("ZIP member size or ratio exceeded")
                expanded += info.file_size
                if expanded > limits.expanded_bytes:
                    raise InvalidHistory("ZIP expanded byte limit exceeded")
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
            with archive.open(info) as member:
                result = (
                    _scan_xml(member, index, limits, on_row, on_nested)
                    if kind == "healthdata_xml"
                    else hash_stream(member, limits.member_bytes)
                )
            if result[1] != info.file_size:
                raise InvalidHistory("ZIP member length mismatch")
            on_member(index, info.filename, kind, *result)
    stream.seek(0)
    if hash_stream(stream, limits.archive_bytes) != original:
        raise InvalidHistory("original changed during inventory")
    return original
