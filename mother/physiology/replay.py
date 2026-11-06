"""Build explicit, source-aware replay bundles from a retained local archive."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
import json

from . import CONTRACT_VERSION, PROCESSING_VERSION
from .contracts import validate_record
from .time import parse_timestamp, utc_iso

DEFAULT_CHANNELS = [
    "glucose",
    "heart_rate",
    "hrv_sdnn",
    "hrv_rmssd",
    "sleep",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "ketone",
    "lactate",
]


def _overlaps(record, start, end):
    if record["record_type"] == "observation":
        first, last = record["measurement_start"], record["measurement_end"]
    elif record["record_type"] == "event":
        first, last = record["occurrence_start"], record["occurrence_end"]
        if first is None:
            # Select untimed annotations by recording time without presenting
            # that timestamp as their occurrence or historical availability.
            first, last = record["recorded_at"], record["recorded_at"]
    else:
        first, last = record.get("start"), record.get("end")
    if first is None:
        return False
    a = parse_timestamp(first)
    b = parse_timestamp(last) if last else a
    return a <= end and b >= start


def _source_record(row, subject_id):
    raw = json.loads(row["raw_json"])
    record = {
        "schema_version": CONTRACT_VERSION,
        "record_type": "source_revision",
        "id": row["revision_id"],
        "subject_id": subject_id,
        "processing_version": "source-record-1.0.0",
        "source_instance": row["source_instance"],
        "collection": row["collection"],
        "source_key": row["source_key"],
        "native_id": row["native_id"],
        "revision_hash": row["revision_hash"],
        "artifact_sha256": row["artifact_sha256"],
        "original_record": raw,
        "first_seen_at": row["first_seen_at"],
        "ingested_at": row["ingested_at"],
        "source_available_at": row["source_available_at"],
        "source_modified_at": row["source_modified_at"],
        "import_run_id": row["import_run_id"],
        "identity_basis": (
            "native_id" if row["native_id"] is not None else "payload_fingerprint"
        ),
        "quality_flags": [] if row["native_id"] is not None else ["ambiguous_identity"],
    }
    return validate_record(record)


def _coverage(observations, events, source_by_id, start, end, expected, cadences):
    groups = defaultdict(list)
    for record in observations:
        source = source_by_id[record["source_revision_id"]]["source_instance"]
        groups[(record["channel"], source)].append(record)
    for event in events:
        if event["event_kind"] == "sleep" and event["source_revision_id"]:
            source = source_by_id[event["source_revision_id"]]["source_instance"]
            groups[("sleep", source)].append(event)
    out = []
    for (channel, source), records in sorted(groups.items()):
        cadence = cadences.get(channel)
        if cadence is not None and (isinstance(cadence, bool) or float(cadence) <= 0):
            raise ValueError("Expected cadence must be positive or unknown")
        valid = [
            r
            for r in records
            if r["record_type"] == "event"
            or (
                r["value_status"] == "valid"
                and r["epistemic_type"] in {"measured", "vendor_derived", "reported"}
            )
        ]
        gaps = []
        if cadence is not None:
            # Cadence is explicitly supplied, never inferred from sparse values.
            ticks = sorted(
                {
                    parse_timestamp(r["measurement_start"])
                    for r in valid
                    if r["record_type"] == "observation"
                }
            )
            tolerance = timedelta(seconds=float(cadence))
            cursor = start
            for tick in ticks:
                if tick < start or tick > end:
                    continue
                if tick - cursor > tolerance:
                    gaps.append(
                        {
                            "start": utc_iso(cursor),
                            "end": utc_iso(tick),
                            "reason": "expected_samples_absent",
                        }
                    )
                cursor = tick
            if end - cursor > tolerance:
                gaps.append(
                    {
                        "start": utc_iso(cursor),
                        "end": utc_iso(end),
                        "reason": "expected_samples_absent",
                    }
                )
        quality = sorted({flag for r in records for flag in r.get("quality_flags", [])})
        status = (
            "partial"
            if not valid
            else "partial" if gaps else "observed" if cadence is not None else "unknown"
        )
        if not valid:
            gaps = [
                {
                    "start": utc_iso(start),
                    "end": utc_iso(end),
                    "reason": "no_valid_observations",
                }
            ]
        if cadence is None:
            quality.append("continuous_coverage_not_established")
        out.append(
            {
                "channel": channel,
                "source_instance": source,
                "start": utc_iso(start),
                "end": utc_iso(end),
                "count": len(records),
                "valid_count": len(valid),
                "expected_cadence_seconds": cadence,
                "gaps": gaps,
                "quality_flags": sorted(set(quality)),
                "status": status,
            }
        )
    seen = {c["channel"] for c in out}
    for channel in expected:
        if channel not in seen:
            out.append(
                {
                    "channel": channel,
                    "source_instance": "unobserved",
                    "start": utc_iso(start),
                    "end": utc_iso(end),
                    "count": 0,
                    "valid_count": 0,
                    "expected_cadence_seconds": cadences.get(channel),
                    "gaps": [
                        {
                            "start": utc_iso(start),
                            "end": utc_iso(end),
                            "reason": "no_records_in_selected_interval",
                        }
                    ],
                    "quality_flags": ["unobserved"],
                    "status": "absent",
                }
            )
    return out


def build_replay(
    archive,
    *,
    subject_id,
    start,
    end,
    expected_channels=None,
    cadence_seconds=None,
    evidence_level="imported_unvalidated",
    processing_versions=None,
):
    """Replay the current revision projection by occurrence time, without inference.

    This is explicitly retrospective. It is not a claim that the displayed
    observations or revisions were available to an earlier live predictor.
    """
    start, end = parse_timestamp(start), parse_timestamp(end)
    if end <= start:
        raise ValueError("Replay end must follow start")
    if evidence_level not in {
        "synthetic_integration",
        "imported_unvalidated",
        "real_data_reconciled",
    }:
        raise ValueError("Unknown replay evidence level")
    available = [r for r in archive.current_records() if r["subject_id"] == subject_id]
    if processing_versions is not None:
        available = [
            r for r in available if r["processing_version"] in processing_versions
        ]
    records = [r for r in available if _overlaps(r, start, end)]
    # A displayed observation may refer to a session whose declared interval
    # falls outside this view. Preserve that context and all its source links.
    sessions = {r["id"]: r for r in available if r["record_type"] == "session"}
    included = {r["id"] for r in records}
    for record in list(records):
        session_id = record.get("session_id")
        if session_id is not None and session_id not in included:
            if session_id not in sessions:
                raise ValueError("Replay contains an unresolved recording session")
            records.append(sessions[session_id])
            included.add(session_id)
    alternatives = defaultdict(set)
    for record in records:
        key = (
            record.get("source_revision_id")
            or tuple(record.get("source_revision_ids", [])),
            record["record_type"],
            record.get("channel") or record.get("event_kind"),
        )
        alternatives[key].add(record["processing_version"])
    if any(len(versions) > 1 for versions in alternatives.values()):
        raise ValueError(
            "Multiple processing versions require an explicit replay version selection"
        )
    for record in records:
        validate_record(record)
    revisions = {}
    for record in records:
        for revision_id in (
            record.get("lineage", [])
            + record.get("source_revision_ids", [])
            + (
                [record["source_revision_id"]]
                if record.get("source_revision_id")
                else []
            )
        ):
            row = archive.revision(revision_id)
            if row is None:
                raise ValueError("Replay contains an unresolved source revision")
            revisions[revision_id] = _source_record(row, subject_id)
    observations = sorted(
        [r for r in records if r["record_type"] == "observation"],
        key=lambda r: (parse_timestamp(r["measurement_start"]), r["id"]),
    )
    events = sorted(
        [r for r in records if r["record_type"] == "event"],
        key=lambda r: (r["occurrence_start"] or "", r["id"]),
    )
    coverage = _coverage(
        observations,
        events,
        revisions,
        start,
        end,
        expected_channels or DEFAULT_CHANNELS,
        cadence_seconds or {},
    )
    import_summaries = [
        {
            "run_id": run["run_id"],
            "source_instance": run["source_instance"],
            "collection": run["collection"],
            "status": run["status"],
            "adapter_version": run["adapter_version"],
            "started_at": run["started_at"],
            "completed_at": run["completed_at"],
            "counts": run["counts"],
            "error": run["error"],
        }
        for run in archive.import_runs()
        if run["request"].get("subject_id") == subject_id
    ]
    return {
        "schema_version": CONTRACT_VERSION,
        "subject_id": subject_id,
        "start": utc_iso(start),
        "end": utc_iso(end),
        "observations": observations,
        "events": events,
        "sessions": [r for r in records if r["record_type"] == "session"],
        "streams": [r for r in records if r["record_type"] == "stream"],
        "coverage": coverage,
        "source_revisions": list(revisions.values()),
        "metadata": {
            "evidence_level": evidence_level,
            "import_summaries": import_summaries,
            "processing_version": PROCESSING_VERSION,
            "selected_processing_versions": (
                sorted(processing_versions) if processing_versions is not None else None
            ),
            "timing_policy": "retrospective_current_revision_projection",
            "assumptions": [
                "Historical availability remains unknown unless supplied by a qualified source.",
                "Principal sleep is not inferred from overlapping stage records.",
                "Relayed-source reconciliation remains unresolved unless explicit lineage establishes it.",
                "Discrete measurements are not interpolated; unknown cadence does not establish continuous coverage.",
            ],
        },
    }
