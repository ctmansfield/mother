"""Offline ingestion of explicitly reported Coach events into Mother evidence.

Requires an already-open, explicit PF-001 Archive. No service, user prompt,
notification, recommendation, or therapeutic action is triggered here.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from .contracts import (
    canonical_json,
    content_hash,
    stable_id,
    validate_record,
)
from .time import utc_iso

COLLECTION = "coach_manual_events"
ADAPTER_VERSION = "coach-manual-ingest/0.1.0"
COACH_PROCESSING_VERSION = "coach-manual-events/0.1.0"
MAX_INPUT_BYTES = 256 * 1024

ALLOWED_PARENTS = {
    "answer": {"question"},
    "acknowledgment": {"recommendation"},
    "reported_action": {"recommendation", "acknowledgment"},
    "outcome": {"reported_action", "observed_action"},
}
REQUIRED_PARENT = {"answer", "acknowledgment", "outcome"}
MANUAL_KINDS = {
    "user_marker",
    "context",
    "answer",
    "acknowledgment",
    "reported_action",
    "outcome",
}


class ManualIngestError(ValueError):
    """An offline event draft cannot be safely archived as supplied."""


def _unique_pairs(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ManualIngestError("Duplicate JSON object key")
        output[key] = value
    return output


def _bad_constant(value):
    raise ManualIngestError("Non-finite JSON number is forbidden")


def _parse_input(data: bytes):
    if type(data) is not bytes:
        raise ManualIngestError("Input must be original JSON bytes")
    if not data or len(data) > MAX_INPUT_BYTES:
        raise ManualIngestError("Event exceeds bounded input size or is empty")
    try:
        draft = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_bad_constant,
        )
    except (ValueError, UnicodeError) as exc:
        raise ManualIngestError("Invalid event JSON input") from exc
    if not isinstance(draft, dict):
        raise ManualIngestError("An event must be a JSON object")
    return draft


def _parent_and_session_checks(archive, draft):
    kind = draft["event_kind"]
    references = draft["related_ids"]
    allowed = ALLOWED_PARENTS.get(kind)
    if not isinstance(references, list) or len(references) > 1:
        raise ManualIngestError("Manual event permits at most one related event")
    if kind in REQUIRED_PARENT and not references:
        raise ManualIngestError("A typed parent event is required")
    if references and allowed is None:
        raise ManualIngestError("Standalone manual event cannot attach a parent")
    if references:
        if references[0] == draft["id"]:
            raise ManualIngestError("Self-referential event is forbidden")
        parents = {
            record["id"]: record
            for record in archive.records(kind="event", current=False)
        }
        parent = parents.get(references[0])
        if parent is None:
            raise ManualIngestError("Referenced event has not been archived")
        if parent["subject_id"] != draft["subject_id"]:
            raise ManualIngestError("Cross-subject event reference")
        if parent["event_kind"] not in allowed:
            raise ManualIngestError("Incompatible parent event kind")
    if draft["session_id"] is not None:
        sessions = {
            record["id"]: record
            for record in archive.records(kind="session", current=False)
        }
        session = sessions.get(draft["session_id"])
        if session is None or session["subject_id"] != draft["subject_id"]:
            raise ManualIngestError("Unknown or cross-subject recording session")


def ingest_manual_event(
    archive,
    original_json: bytes,
    *,
    received_at: str | None = None,
) -> dict:
    """Commit one immutable manual event, its original bytes and source revision.

    Repeating identical bytes is idempotent. A changed event with the same
    event ID is rejected; create a separately identified corrective event
    rather than silently rewriting existing evidence.

    The archive path is selected by the caller; this function never chooses a
    host path or changes an application's running configuration.
    """
    raw = _parse_input(original_json)
    if raw.get("record_type") != "event":
        raise ManualIngestError("Only event drafts are accepted")
    if raw.get("event_kind") not in MANUAL_KINDS:
        raise ManualIngestError("Unsupported manually reported event kind")
    if raw.get("source") != "coach:manual":
        raise ManualIngestError("Manual event source must be coach:manual")
    if raw.get("processing_version") != COACH_PROCESSING_VERSION:
        raise ManualIngestError("Incompatible Coach event processing version")
    if raw.get("epistemic_type") != "reported":
        raise ManualIngestError("Manual events must be reported, not measured")
    if raw.get("source_revision_id") is not None:
        raise ManualIngestError("Source revision is assigned by Mother")
    if not isinstance(raw.get("subject_id"), str) or not raw["subject_id"]:
        raise ManualIngestError("Subject identifier is missing")
    if not isinstance(raw.get("id"), str) or not raw["id"]:
        raise ManualIngestError("Event identifier is missing")
    if len(raw["id"]) > 256 or len(raw["subject_id"]) > 256:
        raise ManualIngestError("Identity exceeds maximum length")
    validate_record(raw)
    _parent_and_session_checks(archive, raw)

    observed = utc_iso(received_at or datetime.now(timezone.utc))
    source = "coach:manual:" + raw["subject_id"]
    source_key = "native:" + raw["id"]
    revision_hash = content_hash(raw)
    revision_id = stable_id("revision", source, COLLECTION, source_key, revision_hash)
    previous = archive.revision(revision_id)
    first_seen_at = previous["first_seen_at"] if previous else observed
    ingested_at = previous["ingested_at"] if previous else observed
    normalized = dict(raw, source_revision_id=revision_id)
    validate_record(normalized)

    artifact_sha256 = hashlib.sha256(original_json).hexdigest()
    run_id = archive.begin_run(
        source,
        COLLECTION,
        ADAPTER_VERSION,
        {
            "subject_id": raw["subject_id"],
            "artifact_sha256": artifact_sha256,
            "source_format": "coach_manual_json",
        },
        started_at=observed,
    )
    revision = {
        "revision_id": revision_id,
        "source_instance": source,
        "collection": COLLECTION,
        "source_key": source_key,
        "native_id": raw["id"],
        "revision_hash": revision_hash,
        "raw_json": canonical_json(raw),
        "first_seen_at": first_seen_at,
        "ingested_at": ingested_at,
        "source_available_at": None,
        "source_modified_at": None,
        "measurement_start": raw["occurrence_start"],
        "measurement_end": raw["occurrence_end"],
        "import_run_id": run_id,
        "disposition": "accepted",
        "rejection_reason": None,
        "artifact_sha256": artifact_sha256,
        "observed_at": observed,
    }
    try:
        result = archive.commit_batch(
            run_id,
            [revision],
            [normalized],
            artifacts=[
                {
                    "sha256": artifact_sha256,
                    "content": original_json,
                    "media_type": "application/json",
                    "created_at": observed,
                }
            ],
            complete=True,
            counts={"received": 1, "accepted": 1, "normalized": 1},
        )
    except Exception as exc:
        archive.fail_run(run_id, type(exc).__name__)
        raise
    return {
        "run_id": run_id,
        "event_id": normalized["id"],
        "revision_id": revision_id,
        "artifact_sha256": artifact_sha256,
        "new_records": result["new_records"],
        "repeated_revisions": result["repeated_revisions"],
        "evidence_level": "offline_event_ingestion",
    }
