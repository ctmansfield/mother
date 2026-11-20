"""Read-only Nightscout v1 acquisition into an immutable local archive.

The installed server has not been inspected. API acquisition therefore requires
an explicit capability assertion for bounded queries and the requested count;
otherwise it refuses before any HTTP call. Complete means the declared bounded
query was exhausted under that capability, not a transactional server snapshot
or complete lifetime sensor coverage. Reconcile older intervals to find edits
whose measurement time lies outside the incremental overlap.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

import pandas as pd
import requests

from mother.physiology.archive import Archive
from mother.physiology.contracts import (
    canonical_json,
    content_hash,
    make_event,
    make_observation,
    stable_id,
)
from mother.physiology.time import epoch_ms, parse_timestamp, utc_iso
from mother.physiology.units import normalize_scalar

ADAPTER_VERSION = "nightscout-v1/1.0.0"
DEFAULT_ARCHIVE = "storage/physiology/archive.sqlite3"
NS_URL = os.getenv("NIGHTSCOUT_URL", "")
NS_SECRET = os.getenv("NIGHTSCOUT_API_SECRET", "")
NS_TOKEN = os.getenv("NIGHTSCOUT_TOKEN", "")
NS_VERIFY = os.getenv("NIGHTSCOUT_VERIFY", "true").lower() not in ("0", "false", "no")
HEADERS = {}
if NS_SECRET:
    secret = NS_SECRET.strip()
    is_hash = len(secret) == 40 and all(c in "0123456789abcdefABCDEF" for c in secret)
    HEADERS["API-SECRET"] = (
        secret if is_hash else hashlib.sha1(secret.encode("utf-8")).hexdigest()
    )


class IncompleteImportError(RuntimeError):
    """The response cannot establish exhaustion of the requested interval."""


class CapabilityError(IncompleteImportError):
    """An instance-specific API capability has not been established."""


def _now():
    return utc_iso(datetime.now(timezone.utc))


def _iso(value):
    return utc_iso(value)


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _decode_json(content):
    def reject_constant(unused):
        raise ValueError("Non-finite JSON number")

    return json.loads(
        content, object_pairs_hook=_strict_object, parse_constant=reject_constant
    )


def _measurement_time(raw, collection):
    if collection == "entries":
        numeric = raw.get("date")
        if numeric is not None:
            time = parse_timestamp(numeric, numeric_unit="ms")
            if raw.get("dateString") is not None:
                alternative = parse_timestamp(raw["dateString"])
                if time != alternative:
                    raise ValueError("Conflicting measurement timestamps")
            return time
        return parse_timestamp(raw.get("dateString"))
    return parse_timestamp(raw.get("created_at"))


def _native_id(raw):
    if isinstance(raw, dict):
        for field in ("_id", "identifier"):
            value = raw.get(field)
            if isinstance(value, str) and value:
                return field, value
    return None, None


@dataclass(frozen=True)
class Page:
    records: list
    content: bytes
    sha256: str
    received_at: str
    start_ms: int
    end_ms: int
    saturated: bool


class NightscoutV1Client:
    """Bounded v1 reads with recursive subdivision instead of offset guesses.

    ``verified_page_size`` means the operator has established that this
    instance honors ``count=page_size`` and the date bounds without a smaller
    hidden cap. ``capability_evidence`` identifies that evidence. The software
    records this caller assertion; it cannot turn the assertion into live proof.
    Treatment imports additionally require normalized UTC created_at storage.
    """

    def __init__(
        self,
        base_url: str,
        *,
        page_size=1000,
        verified_page_size=None,
        capability_evidence=None,
        treatment_dates_normalized=False,
        sgv_unit="mg/dL",
        headers=None,
        token=None,
        verify=True,
        request_get=None,
        max_requests=100000,
    ):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("A Nightscout HTTP(S) base URL is required")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Use credential configuration, not credentials or query parameters in the base URL"
            )
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
        ):
            raise ValueError("page_size must be a positive integer")
        if not isinstance(max_requests, int) or max_requests < 1:
            raise ValueError("max_requests must be positive")
        self.base_url = base_url.rstrip("/")
        self.page_size = page_size
        self.verified_page_size = verified_page_size
        self.capability_evidence = capability_evidence
        self.treatment_dates_normalized = treatment_dates_normalized
        self.sgv_unit = sgv_unit
        self.headers = dict(headers or {})
        self.token = token
        self.verify = verify
        self.request_get = request_get or requests.get
        self.max_requests = max_requests
        self.source_instance = (
            "nightscout:" + hashlib.sha256(self.base_url.encode()).hexdigest()
        )

    def capabilities(self):
        return {
            "api": "v1",
            "page_size": self.page_size,
            "verified_page_size": self.verified_page_size,
            "capability_evidence": self.capability_evidence,
            "treatment_dates_normalized": self.treatment_dates_normalized,
            "sgv_unit": self.sgv_unit,
            "snapshot_isolation": False,
        }

    def _require_capability(self, collection):
        if collection not in ("entries", "treatments"):
            raise ValueError("Unsupported Nightscout collection")
        if self.verified_page_size != self.page_size or not self.capability_evidence:
            raise CapabilityError(
                "Bounded v1 query/count capability is unverified; no request sent"
            )
        if collection == "treatments" and not self.treatment_dates_normalized:
            raise CapabilityError(
                "UTC treatment timestamp storage is unverified; no request sent"
            )
        if collection == "entries" and self.sgv_unit not in ("mg/dL", "mmol/L"):
            raise CapabilityError(
                "Nightscout SGV source unit is unverified; no request sent"
            )

    def iter_pages(self, collection, start, end, on_response=None):
        """Yield exhausted half-open leaf intervals; preserve capped parents too.

        A full response is split even if its count might exactly equal the
        total. A full one-millisecond interval is unresolvable and fails. No
        assumption about timestamp uniqueness or source response ordering is
        needed. Every returned row must satisfy the requested measurement range.
        """
        self._require_capability(collection)
        start_dt, end_dt = parse_timestamp(start), parse_timestamp(end)
        if start_dt.microsecond % 1000 or end_dt.microsecond % 1000:
            raise ValueError(
                "Nightscout bounds must have at most millisecond precision"
            )
        if end_dt <= start_dt:
            raise ValueError("A positive bounded interval is required")
        pending = [(epoch_ms(start_dt), epoch_ms(end_dt))]
        requests_made = 0
        seen_native = {}
        while pending:
            left, right = pending.pop()
            requests_made += 1
            if requests_made > self.max_requests:
                raise IncompleteImportError(
                    "Maximum bounded requests reached; interval remains incomplete"
                )
            if collection == "entries":
                endpoint = "/api/v1/entries/sgv.json"
                params = {
                    "count": self.page_size,
                    "find[date][$gte]": left,
                    "find[date][$lt]": right,
                }
            else:
                endpoint = "/api/v1/treatments.json"
                params = {
                    "count": self.page_size,
                    "find[created_at][$gte]": utc_iso(left, numeric_unit="ms"),
                    "find[created_at][$lt]": utc_iso(right, numeric_unit="ms"),
                }
            if self.token:
                params["token"] = self.token
            try:
                response = self.request_get(
                    self.base_url + endpoint,
                    headers=self.headers,
                    params=params,
                    timeout=30,
                    verify=self.verify,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                # requests errors can contain a URL with an access token.
                raise IncompleteImportError(
                    "Nightscout HTTP read failed: " + type(exc).__name__
                ) from None
            content = bytes(response.content)
            received_at = _now()
            digest = hashlib.sha256(content).hexdigest()
            error = None
            try:
                records = _decode_json(content)
                if not isinstance(records, list):
                    raise ValueError("Expected an array")
            except (ValueError, UnicodeError):
                records = []
                error = "Nightscout returned malformed or non-array JSON"
            saturated = len(records) >= self.page_size
            page = Page(records, content, digest, received_at, left, right, saturated)
            if on_response is not None:
                on_response(page, error)
            if error:
                raise IncompleteImportError(error)
            if len(records) > self.page_size:
                raise IncompleteImportError(
                    "Server returned more records than the verified count"
                )
            for raw in records:
                try:
                    if not isinstance(raw, dict):
                        raise ValueError("Non-object record")
                    # The query field proves range membership; an inconsistent
                    # auxiliary dateString is quarantined during normalization.
                    time = (
                        parse_timestamp(raw.get("date"), numeric_unit="ms")
                        if collection == "entries"
                        else parse_timestamp(raw.get("created_at"))
                    )
                    if not (left <= epoch_ms(time) < right):
                        raise ValueError("Out-of-range record")
                    if collection == "entries" and raw.get("date") is None:
                        raise ValueError("Entry lacks the queried numeric time field")
                except (ValueError, TypeError, OverflowError):
                    raise IncompleteImportError(
                        "A response violated its declared time-range contract"
                    ) from None
            if saturated:
                if right - left <= 1:
                    raise IncompleteImportError(
                        "A one-millisecond interval is saturated; exact-time records may be missing"
                    )
                middle = left + (right - left) // 2
                pending.append((middle, right))
                pending.append((left, middle))
                continue
            for raw in records:
                field, native_id = _native_id(raw)
                if native_id:
                    key = (field, native_id)
                    revision_hash = content_hash(raw)
                    previous = seen_native.get(key)
                    if previous is not None and previous != revision_hash:
                        raise IncompleteImportError(
                            "A native record changed during the bounded scan; retry reconciliation"
                        )
                    seen_native[key] = revision_hash
            yield page


def _configured_client(count=None):
    verified = os.getenv("NS_VERIFIED_V1_PAGE_SIZE")
    return NightscoutV1Client(
        NS_URL,
        page_size=count or int(os.getenv("NS_PAGE_SIZE", "1000")),
        verified_page_size=int(verified) if verified else None,
        capability_evidence=os.getenv("NS_CAPABILITY_EVIDENCE") or None,
        treatment_dates_normalized=os.getenv(
            "NS_TREATMENT_DATES_NORMALIZED", "false"
        ).lower()
        == "true",
        sgv_unit=os.getenv("NS_SGV_UNIT", "mg/dL"),
        headers=HEADERS,
        token=NS_TOKEN,
        verify=NS_VERIFY,
    )


def _source_unit(raw, assumed_unit):
    original = raw.get("units", raw.get("unit"))
    unit = original if original is not None else assumed_unit
    if not isinstance(unit, str):
        raise ValueError("Unsupported glucose unit")
    factor, normalized = normalize_scalar("glucose", 1.0, unit)
    return original, normalized, factor


def _prepare_record(
    archive,
    run_id,
    raw,
    *,
    source_instance,
    collection,
    subject_id,
    artifact_sha256,
    observed_at,
    occurrence,
    sgv_unit,
):
    raw_json = canonical_json(raw)
    revision_hash = content_hash(raw)
    native_field, native_id = _native_id(raw)
    if native_id:
        source_key = native_field + ":" + native_id
        flags = []
    else:
        source_key = "fingerprint:" + revision_hash + ":" + str(occurrence)
        flags = ["ambiguous_identity", "full_payload_fingerprint_with_occurrence"]
    revision_id = stable_id(
        "source-revision", source_instance, collection, source_key, revision_hash
    )
    previous = archive.revision(revision_id)
    first_seen = previous["first_seen_at"] if previous else observed_at
    ingested = previous["ingested_at"] if previous else _now()
    revision = {
        "revision_id": revision_id,
        "source_instance": source_instance,
        "collection": collection,
        "source_key": source_key,
        "native_id": native_id,
        "revision_hash": revision_hash,
        "raw_json": raw_json,
        "first_seen_at": first_seen,
        "ingested_at": ingested,
        "source_available_at": None,
        "source_modified_at": None,
        "measurement_start": None,
        "measurement_end": None,
        "import_run_id": previous["import_run_id"] if previous else run_id,
        "disposition": "accepted",
        "rejection_reason": None,
        "artifact_sha256": previous["artifact_sha256"] if previous else artifact_sha256,
        "observed_at": observed_at,
    }
    if not isinstance(raw, dict):
        revision.update(
            disposition="unsupported", rejection_reason="source_record_not_object"
        )
        return revision, None
    if raw.get("srvModified") is not None:
        try:
            revision["source_modified_at"] = utc_iso(
                raw["srvModified"], numeric_unit="ms"
            )
        except ValueError:
            flags.append("invalid_source_modified_time")
    # This is an explicit supported marker, never an inference from absence.
    if raw.get("isValid") is False:
        revision["disposition"] = "deleted"
        return revision, None
    try:
        measured_at = utc_iso(_measurement_time(raw, collection))
        revision["measurement_start"] = measured_at
    except (ValueError, TypeError, OverflowError):
        revision.update(
            disposition="rejected",
            rejection_reason="invalid_or_conflicting_measurement_time",
        )
        return revision, None
    if collection == "entries":
        if raw.get("type", "sgv") != "sgv":
            revision.update(
                disposition="unsupported", rejection_reason="unsupported_entry_type"
            )
            return revision, None
        try:
            original_unit, unit, factor = _source_unit(raw, sgv_unit)
        except ValueError:
            revision.update(
                disposition="rejected", rejection_reason="unsupported_glucose_unit"
            )
            return revision, None
        original_value = raw.get("sgv")
        if original_value is None:
            value, status = None, "missing"
        else:
            try:
                if isinstance(original_value, bool) or isinstance(
                    original_value, (list, dict)
                ):
                    raise ValueError("Non-numeric glucose")
                value, unit = normalize_scalar(
                    "glucose",
                    original_value,
                    original_unit if original_unit is not None else sgv_unit,
                )
            except (ValueError, TypeError, OverflowError):
                revision.update(
                    disposition="rejected", rejection_reason="invalid_glucose_value"
                )
                return revision, None
            status = "valid"
        if original_unit is None:
            flags.append("unit_source_api_contract")
        if factor != 1:
            flags.append("unit_converted")
        record = make_observation(
            id=stable_id("observation", revision_id, "glucose", ADAPTER_VERSION),
            subject_id=subject_id,
            source_revision_id=revision_id,
            channel="glucose",
            native_type=raw.get("type", "sgv"),
            measurement_start=measured_at,
            first_seen_at=first_seen,
            ingested_at=ingested,
            original_value=original_value,
            original_unit=original_unit,
            value=value,
            unit=unit,
            value_status=status,
            epistemic_type="measured",
            method="nightscout_sgv",
            device_id=None,
            recording_app="Nightscout",
            quality_flags=flags,
            processing_version=ADAPTER_VERSION,
            metadata={
                "source_instance": source_instance,
                "source_collection": collection,
                "native_id": native_id,
                "native_id_field": native_field,
                "source_reported_device": raw.get("device"),
                "originating_sensor_verified": False,
                "direction": raw.get("direction"),
                "original_date": raw.get("date"),
                "original_dateString": raw.get("dateString"),
                "source_reported_utcOffset": raw.get("utcOffset"),
                "source_availability_basis": "unknown",
                "unit_basis": (
                    "reported" if original_unit is not None else "declared_api_contract"
                ),
                "unit_conversion_factor": factor,
            },
        )
    elif collection == "treatments":
        record = make_event(
            id=stable_id("event", revision_id, "context", ADAPTER_VERSION),
            subject_id=subject_id,
            event_kind="context",
            occurrence_start=measured_at,
            known_at=None,
            recorded_at=ingested,
            source="Nightscout",
            source_revision_id=revision_id,
            payload={
                "source_instance": source_instance,
                "source_collection": collection,
                "native_id": native_id,
                "native_event_type": raw.get(
                    "eventType", raw.get("event_type", raw.get("event"))
                ),
                "source_record": raw,
            },
            quality_flags=flags,
            processing_version=ADAPTER_VERSION,
        )
    else:
        revision.update(
            disposition="unsupported", rejection_reason="unsupported_collection"
        )
        record = None
    return revision, record


def _new_counts():
    return {
        "returned_records": 0,
        "accepted": 0,
        "rejected": 0,
        "unsupported": 0,
        "deleted": 0,
        "new_revisions": 0,
        "repeated_revisions": 0,
        "new_records": 0,
        "ambiguous_identity_records": 0,
        "response_artifacts": [],
        "measurement_start": None,
        "measurement_end": None,
    }


def _store_records(
    archive,
    run_id,
    records,
    *,
    source_instance,
    collection,
    subject_id,
    artifact_sha256,
    observed_at,
    occurrences,
    counts,
    sgv_unit,
):
    # Commit a complete leaf/file as a unit. Duplicate native revisions in one
    # batch need the same immutable first-seen/ingestion times as their first row.
    revisions, normalized = [], []
    prepared = {}
    for raw in records:
        fingerprint = content_hash(raw)
        native_field, native_id = _native_id(raw)
        occurrence = occurrences[fingerprint] if native_id is None else 0
        if native_id is None:
            occurrences[fingerprint] += 1
            counts["ambiguous_identity_records"] += 1
        key = (native_field, native_id, fingerprint, occurrence)
        if key in prepared:
            revision, record = prepared[key]
        else:
            revision, record = _prepare_record(
                archive,
                run_id,
                raw,
                source_instance=source_instance,
                collection=collection,
                subject_id=subject_id,
                artifact_sha256=artifact_sha256,
                observed_at=observed_at,
                occurrence=occurrence,
                sgv_unit=sgv_unit,
            )
            prepared[key] = (revision, record)
        counts["returned_records"] += 1
        counts[revision["disposition"]] += 1
        if revision["measurement_start"] is not None:
            time = revision["measurement_start"]
            if counts["measurement_start"] is None or parse_timestamp(
                time
            ) < parse_timestamp(counts["measurement_start"]):
                counts["measurement_start"] = time
            if counts["measurement_end"] is None or parse_timestamp(
                time
            ) > parse_timestamp(counts["measurement_end"]):
                counts["measurement_end"] = time
        revisions.append(revision)
        if record is not None:
            normalized.append(record)
    result = archive.commit_batch(run_id, revisions, normalized, counts=counts)
    for field in ("new_revisions", "repeated_revisions", "new_records"):
        counts[field] += result[field]


def _next_checkpoint(previous, start, end):
    start_ms, end_ms = epoch_ms(start), epoch_ms(end)
    if previous:
        old_start, old_end = previous["coverage_start_ms"], previous["through_ms"]
        if start_ms > old_end or end_ms < old_start:
            return previous  # A disjoint targeted read must not create claimed continuous coverage.
        start_ms, end_ms = min(start_ms, old_start), max(end_ms, old_end)
    return {
        "coverage_start_ms": start_ms,
        "through_ms": end_ms,
        "coverage_start": utc_iso(start_ms, numeric_unit="ms"),
        "through": utc_iso(end_ms, numeric_unit="ms"),
        "basis": "completed_bounded_queries_not_sensor_coverage",
        "adapter_version": ADAPTER_VERSION,
    }


def _sync_collection(
    archive, client, *, source_instance, collection, subject_id, start, end
):
    counts, occurrences = _new_counts(), Counter()
    run_id = archive.begin_run(
        source_instance,
        collection,
        ADAPTER_VERSION,
        {
            "mode": "bounded_api",
            "start": utc_iso(start),
            "end": utc_iso(end),
            "interval": "[start,end)",
            "subject_id": subject_id,
            "capabilities": client.capabilities(),
            "availability_assumption": "unknown",
            "reconciliation_basis": "measurement_time",
        },
    )

    def retain_response(page, error):
        counts["response_artifacts"].append(
            {
                "sha256": page.sha256,
                "start_ms": page.start_ms,
                "end_ms": page.end_ms,
                "received_at": page.received_at,
                "returned_count": len(page.records),
                "saturated": page.saturated,
                "parse_error": error,
            }
        )
        archive.commit_batch(
            run_id,
            artifacts=[
                {
                    "sha256": page.sha256,
                    "media_type": "application/json",
                    "content": page.content,
                    "created_at": page.received_at,
                }
            ],
            counts=counts,
        )

    try:
        for page in client.iter_pages(collection, start, end, retain_response):
            _store_records(
                archive,
                run_id,
                page.records,
                source_instance=source_instance,
                collection=collection,
                subject_id=subject_id,
                artifact_sha256=page.sha256,
                observed_at=page.received_at,
                occurrences=occurrences,
                counts=counts,
                sgv_unit=client.sgv_unit,
            )
        previous = archive.checkpoint(source_instance, collection)
        archive.commit_batch(
            run_id,
            complete=True,
            counts=counts,
            checkpoint=_next_checkpoint(previous, start, end),
        )
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, IncompleteImportError)
            else "Import failed: " + type(exc).__name__
        )
        archive.fail_run(
            run_id, message, counts, incomplete=isinstance(exc, IncompleteImportError)
        )
        raise
    return archive.import_run(run_id)


def import_json_file(
    source,
    *,
    archive_path=DEFAULT_ARCHIVE,
    source_instance,
    collection="entries",
    subject_id="self",
    sgv_unit=None,
):
    """Import an original JSON array without network or advancing an API cursor.

    Units must be reported per row or supplied as an explicit source contract.
    This establishes retention/mapping of the file, not remote archive coverage.
    """
    content = Path(source).read_bytes()
    observed_at = _now()
    digest = hashlib.sha256(content).hexdigest()
    with Archive(archive_path) as archive:
        counts = _new_counts()
        run_id = archive.begin_run(
            source_instance,
            collection,
            ADAPTER_VERSION,
            {
                "mode": "original_json_file",
                "artifact_sha256": digest,
                "subject_id": subject_id,
                "sgv_unit": sgv_unit,
            },
        )
        archive.commit_batch(
            run_id,
            artifacts=[
                {
                    "sha256": digest,
                    "media_type": "application/json",
                    "content": content,
                    "created_at": observed_at,
                }
            ],
        )
        try:
            records = _decode_json(content)
            if not isinstance(records, list):
                raise ValueError("Expected a JSON array")
            _store_records(
                archive,
                run_id,
                records,
                source_instance=source_instance,
                collection=collection,
                subject_id=subject_id,
                artifact_sha256=digest,
                observed_at=observed_at,
                occurrences=Counter(),
                counts=counts,
                sgv_unit=sgv_unit,
            )
            archive.commit_batch(run_id, complete=True, counts=counts)
        except Exception as exc:
            archive.fail_run(
                run_id, "File import failed: " + type(exc).__name__, counts
            )
            raise
        return archive.import_run(run_id)


def save_parquet(df, path):
    """Atomically replace one reproducible view; never the authoritative archive."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + target.name + ".", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    try:
        df.to_parquet(temporary, index=False)
        with open(temporary, "rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _check_view_target(archive, path, source_instance):
    """Never silently replace pre-archive data or a view of another archive."""
    if not Path(path).exists():
        return
    existing = pd.read_parquet(path)
    required = {"source_revision_id", "source_instance", "processing_version"}
    if not required.issubset(existing.columns):
        raise ValueError(
            "Legacy Parquet view is unarchived; preserve it and choose a new analytics directory"
        )
    sources = set(existing["source_instance"].dropna())
    if source_instance is not None and sources - {source_instance}:
        raise ValueError("Refusing to replace a view of another source instance")
    for revision_id in existing["source_revision_id"].drop_duplicates():
        if not isinstance(revision_id, str) or archive.revision(revision_id) is None:
            raise ValueError(
                "Parquet lineage is not retained in this archive; choose a new analytics directory"
            )


def _optional_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if result == result and abs(result) != float("inf") else None
    except (ValueError, TypeError, OverflowError):
        return None


def export_analysis_views(archive, directory="storage/analytics", source_instance=None):
    """Rebuild full retained current SGV/context views, including lineage columns."""
    for name in ("cgm.parquet", "treatments.parquet"):
        _check_view_target(archive, Path(directory) / name, source_instance)
    rows = []
    seen = set()
    for record in archive.current_records("observation", source_instance, "entries"):
        if (
            record["processing_version"] != ADAPTER_VERSION
            or record["channel"] != "glucose"
        ):
            continue
        key = (
            record["source_revision_id"],
            record["channel"],
            record["processing_version"],
        )
        if key in seen:
            raise ValueError(
                "Ambiguous duplicate glucose derivation for one source revision/version"
            )
        seen.add(key)
        rows.append(
            {
                "ts": epoch_ms(record["measurement_start"]),
                "sgv": record["value"] if record["value_status"] == "valid" else None,
                "direction": (
                    record["metadata"].get("direction")
                    if isinstance(record["metadata"].get("direction"), str)
                    else None
                ),
                "type": record["native_type"],
                "source_available_at": record["source_available_at"],
                "source_revision_id": record["source_revision_id"],
                "source_instance": record["metadata"]["source_instance"],
                "unit": record["unit"],
                "processing_version": record["processing_version"],
                "value_status": record["value_status"],
            }
        )
    columns = [
        "ts",
        "sgv",
        "direction",
        "type",
        "source_available_at",
        "source_revision_id",
        "source_instance",
        "unit",
        "processing_version",
        "value_status",
    ]
    cgm = pd.DataFrame(rows, columns=columns).sort_values("ts")
    cgm["ts"] = cgm["ts"].astype("int64")
    treatment_rows = []
    seen = set()
    for record in archive.current_records("event", source_instance, "treatments"):
        if record["processing_version"] != ADAPTER_VERSION:
            continue
        key = (
            record["source_revision_id"],
            record["event_kind"],
            record["processing_version"],
        )
        if key in seen:
            raise ValueError(
                "Ambiguous duplicate event derivation for one source revision/version"
            )
        seen.add(key)
        raw = record["payload"]["source_record"]
        native_event = record["payload"]["native_event_type"]
        notes = raw.get("notes", raw.get("notes_text"))
        treatment_rows.append(
            {
                "ts": epoch_ms(record["occurrence_start"]),
                "event": native_event if isinstance(native_event, str) else None,
                "carbs": _optional_number(raw.get("carbs")),
                "insulin": _optional_number(raw.get("insulin")),
                "notes": notes if isinstance(notes, str) else None,
                "source_available_at": record["known_at"],
                "source_revision_id": record["source_revision_id"],
                "source_instance": record["payload"]["source_instance"],
                "processing_version": record["processing_version"],
            }
        )
    treatment_columns = [
        "ts",
        "event",
        "carbs",
        "insulin",
        "notes",
        "source_available_at",
        "source_revision_id",
        "source_instance",
        "processing_version",
    ]
    treatments = pd.DataFrame(treatment_rows, columns=treatment_columns).sort_values(
        "ts"
    )
    treatments["ts"] = treatments["ts"].astype("int64")
    save_parquet(cgm, Path(directory) / "cgm.parquet")
    save_parquet(treatments, Path(directory) / "treatments.parquet")
    return {
        "entries": len(cgm),
        "treatments": len(treatments),
        "source": "full_current_archive_projection",
        "source_instance": source_instance,
        "directory": str(directory),
    }


def sync_range(
    start,
    end,
    *,
    archive_path=DEFAULT_ARCHIVE,
    analytics_dir="storage/analytics",
    source_instance=None,
    subject_id="self",
    client=None,
    include_treatments=False,
):
    client = client or _configured_client()
    source_instance = (
        source_instance or os.getenv("NS_SOURCE_INSTANCE") or client.source_instance
    )
    with Archive(archive_path) as archive:
        results = {}
        for collection in (
            ["entries", "treatments"] if include_treatments else ["entries"]
        ):
            results[collection] = _sync_collection(
                archive,
                client,
                source_instance=source_instance,
                collection=collection,
                subject_id=subject_id,
                start=start,
                end=end,
            )
        views = export_analysis_views(archive, analytics_dir, source_instance)
        return {"runs": results, "views": views, "archive": str(archive_path)}


def incremental_sync(
    days=14,
    *,
    archive_path=DEFAULT_ARCHIVE,
    analytics_dir="storage/analytics",
    source_instance=None,
    subject_id="self",
    client=None,
    include_treatments=False,
    end=None,
    overlap_days=2,
    reconcile=False,
):
    """Resume the persisted cursor with overlap; never replace the archive.

    ``days`` bounds only the first import. Explicit ``sync_range`` supplies a
    historical backfill. ``reconcile=True`` rereads the retained range so older
    revisions/late arrivals are eligible for discovery. API v1 cannot discover
    hard deletions or unreturned records, and absence is never a deletion.
    """
    if days <= 0 or overlap_days < 0:
        raise ValueError("days must be positive and overlap_days nonnegative")
    client = client or _configured_client()
    source_instance = (
        source_instance or os.getenv("NS_SOURCE_INSTANCE") or client.source_instance
    )
    end = (
        parse_timestamp(end)
        if end is not None
        else datetime.now(timezone.utc).replace(microsecond=0)
    )
    with Archive(archive_path) as archive:
        results = {}
        for collection in (
            ["entries", "treatments"] if include_treatments else ["entries"]
        ):
            previous = archive.checkpoint(source_instance, collection)
            if previous:
                start_ms = (
                    previous["coverage_start_ms"]
                    if reconcile
                    else max(
                        previous["coverage_start_ms"],
                        previous["through_ms"] - int(overlap_days * 86400000),
                    )
                )
                start = parse_timestamp(start_ms, numeric_unit="ms")
            else:
                start = end - timedelta(days=days)
            results[collection] = _sync_collection(
                archive,
                client,
                source_instance=source_instance,
                collection=collection,
                subject_id=subject_id,
                start=start,
                end=end,
            )
        views = export_analysis_views(archive, analytics_dir, source_instance)
        return {
            "entries": views["entries"],
            "treatments": views["treatments"],
            "runs": results,
            "views": views,
            "archive": str(archive_path),
        }


def _ephemeral_fetch(collection, start, end, count, client):
    if start is None or end is None:
        raise ValueError(
            "Explicit start/end required; use incremental_sync for retained capture"
        )
    client = client or _configured_client(count)
    rows = []
    for page in client.iter_pages(collection, start, end):
        for raw in page.records:
            rows.append(
                {
                    **raw,
                    "ts": epoch_ms(_measurement_time(raw, collection)),
                    "native_id": _native_id(raw)[1],
                    "raw_json": canonical_json(raw),
                    "artifact_sha256": page.sha256,
                }
            )
    return pd.DataFrame(rows)


def fetch_entries(start=None, end=None, count=1000, *, client=None):
    """Ephemeral source inspection only; production capture uses sync_range."""
    return _ephemeral_fetch("entries", start, end, count, client)


def fetch_treatments(start=None, end=None, count=1000, *, client=None):
    """Ephemeral source inspection only; production capture uses sync_range."""
    return _ephemeral_fetch("treatments", start, end, count, client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE)
    parser.add_argument("--analytics-dir", default="storage/analytics")
    parser.add_argument("--source-instance")
    parser.add_argument("--subject-id", default="self")
    parser.add_argument("--input-json")
    parser.add_argument(
        "--collection", choices=("entries", "treatments"), default="entries"
    )
    parser.add_argument("--sgv-unit", choices=("mg/dL", "mmol/L"))
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument(
        "--days", type=int, default=int(os.getenv("NS_SYNC_DAYS", "14"))
    )
    parser.add_argument("--overlap-days", type=float, default=2)
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--include-treatments", action="store_true")
    args = parser.parse_args()
    if args.input_json:
        if not args.source_instance:
            parser.error("--input-json requires a stable --source-instance")
        result = import_json_file(
            args.input_json,
            archive_path=args.archive,
            source_instance=args.source_instance,
            collection=args.collection,
            subject_id=args.subject_id,
            sgv_unit=args.sgv_unit,
        )
        with Archive(args.archive) as archive:
            export_analysis_views(archive, args.analytics_dir, args.source_instance)
    else:
        common = dict(
            archive_path=args.archive,
            analytics_dir=args.analytics_dir,
            source_instance=args.source_instance,
            subject_id=args.subject_id,
            include_treatments=args.include_treatments,
        )
        if args.start:
            if not args.end:
                parser.error("--start requires --end for a bounded backfill")
            result = sync_range(args.start, args.end, **common)
        else:
            result = incremental_sync(
                args.days,
                end=args.end,
                overlap_days=args.overlap_days,
                reconcile=args.reconcile,
                **common,
            )
    # Avoid printing source content, annotations, credentials or full manifests.
    if "runs" in result:
        print(
            json.dumps(
                {
                    "run_ids": {k: v["run_id"] for k, v in result["runs"].items()},
                    "views": result["views"],
                }
            )
        )
    else:
        print(
            json.dumps(
                {
                    "run_id": result["run_id"],
                    "status": result["status"],
                    "accepted": result["counts"]["accepted"],
                    "rejected": result["counts"]["rejected"],
                }
            )
        )


if __name__ == "__main__":
    main()
