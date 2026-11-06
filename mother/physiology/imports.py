"""Bounded, offline export readers with original-byte retention.

Supported mappings are fixture-verified, not qualified against a wearer's export.
Unknown source fields remain in the original artifact/record. No reader infers
raw ECG, beat intervals, an originating H10, or historical availability.
"""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring

from .contracts import (
    canonical_json,
    content_hash,
    make_event,
    make_observation,
    stable_id,
)
from .time import utc_iso
from .units import normalize_scalar

ADAPTER_VERSION = "export-readers-0.1.0"
MAX_FILE_BYTES = 128 * 1024 * 1024
APPLE_CHANNELS = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKQuantityTypeIdentifierHeartRateVariabilityRMSSD": "hrv_rmssd",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wrist_temperature",
    "HKQuantityTypeIdentifierOxygenSaturation": "oxygen_saturation",
    "HKQuantityTypeIdentifierBloodGlucose": "glucose",
}
SPOT_CHANNELS = {
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "lactate",
    "ketone",
}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _raw_element(element):
    return {
        "tag": _local(element.tag),
        "attributes": dict(element.attrib),
        "xml": ElementTree.tostring(element, encoding="unicode"),
    }


def _leaf(element, name):
    for item in element:
        if _local(item.tag) == name:
            return item.text
    return None


def _apple_rows(data):
    root = fromstring(data)
    if _local(root.tag) != "HealthData":
        raise ValueError("Expected Apple HealthData XML root")
    for element in root:
        tag = _local(element.tag)
        if tag in {"ExportDate", "Me"}:
            continue  # Account/export metadata stays in the original file.
        raw = _raw_element(element)
        attr = element.attrib
        yield raw, attr.get("uuid"), {"format": "apple", "tag": tag, "attributes": attr}


def _tcx_rows(data):
    root = fromstring(data)
    if _local(root.tag) != "TrainingCenterDatabase":
        raise ValueError("Expected TCX TrainingCenterDatabase XML root")
    for activity in (x for x in root.iter() if _local(x.tag) == "Activity"):
        activity_id = _leaf(activity, "Id")
        activity_raw = _raw_element(activity)
        trackpoints = [x for x in activity.iter() if _local(x.tag) == "Trackpoint"]
        times = [_leaf(x, "Time") for x in trackpoints if _leaf(x, "Time")]
        laps = [x for x in activity if _local(x.tag) == "Lap"]
        # A session's exact cessation is not invented from its final HR sample.
        # The last recorded sample bounds this recording, not an exercise cutoff.
        yield activity_raw, activity_id, {
            "format": "tcx_activity",
            "times": times,
            "sport": activity.attrib.get("Sport"),
            "lap_count": len(laps),
        }
        occurrences = Counter()
        for point in trackpoints:
            raw = _raw_element(point)
            raw["activity_native_id"] = activity_id
            timestamp = _leaf(point, "Time")
            hr_nodes = [x for x in point if _local(x.tag) == "HeartRateBpm"]
            hr = _leaf(hr_nodes[0], "Value") if hr_nodes else None
            occurrences[timestamp] += 1
            # TCX has no native sample UUID; time-position identity is declared.
            native = None
            yield raw, native, {
                "format": "tcx_point",
                "ts": timestamp,
                "value": hr,
                "activity_native_id": activity_id,
                "sample_ordinal": occurrences[timestamp],
            }


def _spot_rows(data):
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    if not {"ts", "channel", "value", "unit"} <= set(rows.fieldnames or []):
        raise ValueError("Spot CSV requires ts, channel, value and unit")
    for row in rows:
        yield dict(row), row.get("native_id") or None, {"format": "spot", "row": row}


def _normalize(info, *, subject_id, revision_id, source_key, source_instance, now):
    fmt = info["format"]
    common = {
        "subject_id": subject_id,
        "source_revision_id": revision_id,
        "first_seen_at": now,
        "ingested_at": now,
        "source_available_at": None,
        "processing_version": ADAPTER_VERSION,
    }
    flags = [] if info.get("native_id") else ["ambiguous_identity"]
    if fmt == "apple":
        attr = info["attributes"]
        tag = info["tag"]
        typ = attr.get("type")
        if tag == "Workout":
            start, end = utc_iso(attr.get("startDate")), utc_iso(attr.get("endDate"))
            event = make_event(
                id=stable_id("event", revision_id, "exercise", ADAPTER_VERSION),
                subject_id=subject_id,
                event_kind="exercise",
                occurrence_start=start,
                occurrence_end=end,
                known_at=None,
                recorded_at=now,
                source=source_instance,
                source_revision_id=revision_id,
                payload={
                    "native_type": attr.get("workoutActivityType"),
                    "original_attributes": dict(attr),
                },
                epistemic_type="vendor_derived",
                quality_flags=flags + ["source_availability_unknown"],
                processing_version=ADAPTER_VERSION,
            )
            return [event], start, end
        if tag != "Record":
            raise NotImplementedError(
                "Unsupported Apple element; retained in original artifact"
            )
        start, end = utc_iso(attr.get("startDate")), utc_iso(attr.get("endDate"))
        if typ == "HKCategoryTypeIdentifierSleepAnalysis":
            event = make_event(
                id=stable_id("event", revision_id, "sleep", ADAPTER_VERSION),
                subject_id=subject_id,
                event_kind="sleep",
                occurrence_start=start,
                occurrence_end=end,
                known_at=None,
                recorded_at=now,
                source=source_instance,
                source_revision_id=revision_id,
                payload={
                    "native_type": typ,
                    "stage": attr.get("value"),
                    "recording_app": attr.get("sourceName"),
                    "principal_sleep": None,
                },
                epistemic_type="vendor_derived",
                quality_flags=flags
                + ["principal_sleep_not_inferred", "source_availability_unknown"],
                processing_version=ADAPTER_VERSION,
            )
            return [event], start, end
        channel = APPLE_CHANNELS.get(typ)
        if channel is None:
            raise NotImplementedError("Unsupported HealthKit type")
        original = attr.get("value")
        unit = attr.get("unit")
        value, normalized_unit = normalize_scalar(channel, original, unit)
        method = "vendor:" + typ
        record = make_observation(
            **common,
            id=stable_id("observation", revision_id, channel, ADAPTER_VERSION),
            channel=channel,
            native_type=typ,
            measurement_start=start,
            measurement_end=end,
            original_value=original,
            original_unit=unit,
            value=value,
            unit=normalized_unit,
            epistemic_type="vendor_derived",
            method=method,
            recording_app=attr.get("sourceName"),
            quality_flags=flags
            + ["source_availability_unknown", "originating_sensor_unverified"],
            clock={
                "original_start": attr.get("startDate"),
                "original_end": attr.get("endDate"),
            },
            metadata={
                "source_version": attr.get("sourceVersion"),
                "native_device": attr.get("device"),
                "source_creation_time_unqualified": attr.get("creationDate"),
                "relay_reconciliation": "unresolved",
            },
        )
        return [record], start, end
    if fmt == "tcx_activity":
        times = sorted(utc_iso(t) for t in info["times"])
        if not times:
            raise NotImplementedError("TCX activity contains no timestamped recording")
        event = make_event(
            id=stable_id("event", revision_id, "recording", ADAPTER_VERSION),
            subject_id=subject_id,
            event_kind="context",
            occurrence_start=times[0],
            occurrence_end=times[-1],
            recorded_at=now,
            source=source_instance,
            source_revision_id=revision_id,
            payload={
                "kind": "recording_extent",
                "sport": info["sport"],
                "lap_count": info["lap_count"],
                "exercise_end": None,
            },
            quality_flags=flags
            + ["exercise_cessation_unverified", "source_availability_unknown"],
            epistemic_type="vendor_derived",
            processing_version=ADAPTER_VERSION,
        )
        return [event], times[0], times[-1]
    if fmt == "tcx_point":
        timestamp = utc_iso(info["ts"])
        if info["value"] is None:
            raise NotImplementedError("TCX trackpoint has no HR measurement")
        value, unit = normalize_scalar("heart_rate", info["value"], "bpm")
        record = make_observation(
            **common,
            id=stable_id("observation", revision_id, "heart_rate", ADAPTER_VERSION),
            channel="heart_rate",
            native_type="TCX:HeartRateBpm",
            measurement_start=timestamp,
            original_value=info["value"],
            original_unit="bpm",
            value=value,
            unit=unit,
            method="TCX exported heart rate",
            recording_app="Polar-compatible TCX export",
            quality_flags=flags
            + ["source_availability_unknown", "originating_sensor_unverified"],
            clock={"original_timestamp": info["ts"]},
            metadata={
                "activity_native_id": info["activity_native_id"],
                "relay_reconciliation": "unresolved",
            },
        )
        return [record], timestamp, None
    row = info["row"]
    channel = row["channel"]
    if channel not in SPOT_CHANNELS:
        raise NotImplementedError("Unsupported spot channel")
    timestamp = utc_iso(row["ts"])
    value, unit = normalize_scalar(channel, row["value"], row["unit"])
    # These are manually transcribed meter observations until a device export is qualified.
    record = make_observation(
        **common,
        id=stable_id("observation", revision_id, channel, ADAPTER_VERSION),
        channel=channel,
        native_type=row.get("native_type") or channel,
        measurement_start=timestamp,
        original_value=row["value"],
        original_unit=row["unit"],
        value=value,
        unit=unit,
        epistemic_type="reported",
        method=row.get("method") or "manual meter transcription",
        device_id=row.get("device_id") or None,
        body_site=row.get("body_site") or None,
        specimen=row.get("specimen") or None,
        measurement_group_id=row.get("measurement_group_id") or None,
        quality_flags=flags
        + ["manual_transcription", "source_availability_unknown"]
        + (
            ["analyte_specimen_unverified"]
            if channel in {"ketone", "lactate"} and not row.get("specimen")
            else []
        ),
        clock={"original_timestamp": row["ts"]},
        metadata={"analyte": row.get("analyte") or None},
    )
    return [record], timestamp, None


def import_file(archive, source, *, format, source_instance, subject_id, now=None):
    """Import a bounded file; preserve rejected/unsupported records and raw bytes."""
    readers = {"apple_xml": _apple_rows, "polar_tcx": _tcx_rows, "spot_csv": _spot_rows}
    if format not in readers:
        raise ValueError("Unsupported file format")
    path = Path(source)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(
            "File exceeds the bounded 128 MiB reader limit; select a smaller export"
        )
    data = path.read_bytes()
    artifact_hash = hashlib.sha256(data).hexdigest()
    now = utc_iso(now or datetime.now(timezone.utc))
    run_id = archive.begin_run(
        source_instance,
        format,
        ADAPTER_VERSION,
        {
            "artifact_sha256": artifact_hash,
            "format": format,
            "subject_id": subject_id,
            "qualification": "synthetic-fixture-only",
        },
        started_at=now,
    )
    counts = {
        "received": 0,
        "accepted": 0,
        "rejected": 0,
        "unsupported": 0,
        "ambiguous_identity": 0,
        "normalized": 0,
    }
    artifact = {
        "sha256": artifact_hash,
        "media_type": "text/csv" if format == "spot_csv" else "application/xml",
        "content": data,
        "created_at": now,
    }
    archive.commit_batch(run_id, [], [], artifacts=[artifact])
    revisions, records = [], []
    occurrences = Counter()
    try:
        for raw, native_id, info in readers[format](data):
            counts["received"] += 1
            revision_hash = content_hash(raw)
            occurrences[revision_hash] += 1
            source_key = (
                ("native:" + str(native_id))
                if native_id
                else f"fingerprint:{revision_hash}:{occurrences[revision_hash]}"
            )
            revision_id = stable_id(
                "revision", source_instance, format, source_key, revision_hash
            )
            prior = archive.revision(revision_id)
            first_seen = prior["first_seen_at"] if prior else now
            ingested = prior["ingested_at"] if prior else now
            info["native_id"] = native_id
            if native_id is None:
                counts["ambiguous_identity"] += 1
            start = end = reason = None
            try:
                normalized, start, end = _normalize(
                    info,
                    subject_id=subject_id,
                    revision_id=revision_id,
                    source_key=source_key,
                    source_instance=source_instance,
                    now=first_seen,
                )
                for record in normalized:
                    if record["record_type"] == "observation":
                        record["ingested_at"] = ingested
                disposition = "accepted"
                counts["normalized"] += len(normalized)
                records.extend(normalized)
            except NotImplementedError as exc:
                disposition, reason = "unsupported", str(exc)
            except (ValueError, TypeError, KeyError) as exc:
                disposition, reason = (
                    "rejected",
                    type(exc).__name__ + ": " + str(exc)[:160],
                )
            counts[disposition] += 1
            revisions.append(
                {
                    "revision_id": revision_id,
                    "source_instance": source_instance,
                    "collection": format,
                    "source_key": source_key,
                    "native_id": native_id,
                    "revision_hash": revision_hash,
                    "raw_json": canonical_json(raw),
                    "first_seen_at": first_seen,
                    "ingested_at": ingested,
                    "source_available_at": None,
                    "source_modified_at": None,
                    "measurement_start": start,
                    "measurement_end": end,
                    "import_run_id": run_id,
                    "disposition": disposition,
                    "rejection_reason": reason,
                    "artifact_sha256": artifact_hash,
                    "observed_at": now,
                }
            )
        archive.commit_batch(
            run_id,
            revisions,
            records,
            counts=counts,
            complete=True,
            checkpoint={
                "artifact_sha256": artifact_hash,
                "format": format,
                "completed_at": now,
            },
        )
    except Exception as exc:
        archive.fail_run(run_id, type(exc).__name__, counts=counts)
        raise
    return {
        "run_id": run_id,
        "artifact_sha256": artifact_hash,
        "counts": counts,
        "qualification": "synthetic-fixture-only",
        "source_availability": "unknown",
    }
