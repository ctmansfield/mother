"""Receipt-backed PF-001 mapping and snapshots for the synthetic ATLAS trial."""

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
import json
import math
import re
import sqlite3

from jsonschema import ValidationError
from mother.physiology.archive import Archive
from mother.physiology.contracts import (
    canonical_json,
    content_hash,
    make_observation,
    stable_id,
)

from . import RecoveryError
from .receipt import _timestamp
from .v02 import SAFE_INTEGER, IngestV02, digest, requires_pf001_observation

NORMALIZER_VERSION = "forge-pf001-0.2"
PROCESSING_FIELDS = (
    "channel",
    "value",
    "unit",
    "event_start",
    "event_end",
    "epistemic_type",
    "classification_basis",
    "classification_evidence_sha256",
)
COMMIT_FIELDS = (
    "artifact_sha256",
    "receipt_id",
    "mother_received_at",
    "committed_at",
    "commit_sequence",
)


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value
    ):
        raise ValueError("Expected an exact normalizer version token")
    return value


def _processing(fact, version):
    values = {key: fact["observation"][key] for key in PROCESSING_FIELDS}
    return digest(
        "mse.processing-revision/0.2", fact["revision_sha256"], version, values
    )


def _source_row(scope, fact):
    raw = {
        "native_id": fact["native_id"],
        "operation": fact["operation"],
        "mse_source_revision_sha256": fact["revision_sha256"],
    }
    revision_id = stable_id(
        "revision",
        scope.archive_source,
        scope.collection,
        fact["native_id"],
        fact["revision_sha256"],
    )
    return revision_id, raw


def _record(scope, fact, version, received_at):
    observation = fact.get("observation")
    if observation is None or not requires_pf001_observation(observation):
        return None
    original_value = float(observation["original_value"])
    value = float(observation["value"])
    if not math.isfinite(original_value) or not math.isfinite(value):
        raise ValueError("Value exceeds the trial PF-001 numeric representation")
    processing = _processing(fact, version)
    revision_id, _ = _source_row(scope, fact)
    fields = {
        key: observation[key]
        for key in ("channel", "unit", "original_unit", "epistemic_type")
    }
    return make_observation(
        **fields,
        id=stable_id("observation", revision_id, processing),
        subject_id=scope.subject_id,
        source_revision_id=revision_id,
        processing_version=version,
        measurement_start=observation["event_start"],
        measurement_end=observation["event_end"],
        source_available_at=observation["source_available_at"],
        first_seen_at=received_at,
        ingested_at=received_at,
        original_value=original_value,
        value=value,
        recording_app=observation["bundle_id"],
        method="HealthKit SDNN" if observation["channel"] == "hrv_sdnn" else None,
        metadata={
            "source_name": observation["source_name"],
            "exact_decimal_value": observation["value"],
            "classification_basis": observation["classification_basis"],
            "classification_evidence_sha256": observation[
                "classification_evidence_sha256"
            ],
            "processing_revision_sha256": processing,
        },
    )


class ConnectedIngest(IngestV02):
    """Ingest real adapter exports and reopen authoritative snapshot membership."""

    def ingest_export(self, original, export, *, normalizer_version=NORMALIZER_VERSION):
        version = _version(normalizer_version)
        export = deepcopy(export)

        def normalize(_original, context):
            revisions, records = [], []
            for fact in export["revisions"]:
                revision_id, raw = _source_row(self.scope, fact)
                observation = fact.get("observation", {})
                revisions.append(
                    {
                        "revision_id": revision_id,
                        "source_instance": self.scope.archive_source,
                        "collection": self.scope.collection,
                        "source_key": fact["native_id"],
                        "native_id": fact["native_id"],
                        "revision_hash": content_hash(raw),
                        "raw_json": canonical_json(raw),
                        "first_seen_at": context.mother_received_at,
                        "ingested_at": context.mother_received_at,
                        "source_available_at": observation.get("source_available_at"),
                        "measurement_start": observation.get("event_start"),
                        "measurement_end": observation.get("event_end"),
                        "import_run_id": context.run_id,
                        "disposition": (
                            "deleted" if fact["operation"] == "delete" else "accepted"
                        ),
                        "artifact_sha256": context.artifact_sha256,
                    }
                )
                record = _record(self.scope, fact, version, context.mother_received_at)
                if record is not None:
                    records.append(record)
            return revisions, records

        return super().ingest(
            original, export, adapter_version=version, normalize=normalize
        )

    def verify_receipt(self, candidate):
        verified = super().verify_receipt(candidate)
        if verified["status"] == "normalized":
            with self._v02_write() as db:
                if not any(
                    receipt == verified
                    for _, _, receipt, _ in self._accepted(
                        db, verified["commit_sequence"], only_sequence=True
                    )
                ):
                    raise RecoveryError(
                        "Receipt is missing its bound source membership"
                    )
        return verified

    def _accepted(self, db, cutoff, *, only_sequence=False):
        orphaned = db.execute(
            """SELECT 1 FROM deliveries d LEFT JOIN stage_receipts s
                  ON s.batch_id=d.batch_id AND s.status='normalized'
                  AND s.sequence=d.commit_sequence
               WHERE d.commit_sequence IS NOT NULL AND d.commit_sequence<=?
                  AND s.sequence IS NULL LIMIT 1""",
            (cutoff,),
        ).fetchone()
        if orphaned:
            raise RecoveryError("Accepted delivery is missing its normalized stage")
        query = (
            "SELECT batch_id, sequence FROM stage_receipts WHERE status='normalized'"
            " AND sequence "
            + ("= ?" if only_sequence else "<= ?")
            + " ORDER BY sequence"
        )
        for stage in db.execute(query, (cutoff,)):
            batch = stage["batch_id"]
            row = self._delivery(db, (canonical_json(self.scope.fields()), batch))
            self._verify_custody(db, row)
            receipt = self._terminal(db, row)
            if (
                not receipt
                or receipt["status"] != "normalized"
                or receipt["commit_sequence"] != stage["sequence"]
            ):
                raise RecoveryError(
                    "Normalized commitment does not match its journal stage"
                )
            stored = db.execute(
                "SELECT export_json FROM trial_exports WHERE batch_id=?", (batch,)
            ).fetchone()
            export = json.loads(stored["export_json"])
            yield export, row["adapter_version"], receipt, self._members(
                export, row, receipt
            )

    def _members(self, export, row, receipt):
        version = row["adapter_version"]
        members, source_ids, record_ids = [], set(), set()
        with Archive(self.archive) as archive:
            run = archive.import_run(receipt["pf001_run_id"])
            if run is None or run["adapter_version"] != version:
                raise RecoveryError("Missing bound PF-001 normalizer version")
            counts = run["counts"]
            for fact in export["revisions"]:
                revision_id, raw = _source_row(self.scope, fact)
                source = archive.revision(revision_id)
                is_delete = fact["operation"] == "delete"
                expected_source = {
                    "source_instance": self.scope.archive_source,
                    "collection": self.scope.collection,
                    "source_key": fact["native_id"],
                    "native_id": fact["native_id"],
                    "revision_hash": content_hash(raw),
                    "raw_json": canonical_json(raw),
                    "disposition": "deleted" if is_delete else "accepted",
                    "source_available_at": fact.get("observation", {}).get(
                        "source_available_at"
                    ),
                    "measurement_start": fact.get("observation", {}).get("event_start"),
                    "measurement_end": fact.get("observation", {}).get("event_end"),
                }
                if source is None or any(
                    source[key] != value for key, value in expected_source.items()
                ):
                    raise RecoveryError(
                        "Archived source revision differs from accepted export"
                    )
                source_ids.add(revision_id)
                record = _record(
                    self.scope, fact, version, receipt["mother_received_at"]
                )
                if record is not None:
                    saved = archive.connection.execute(
                        "SELECT record_json FROM normalized_records WHERE record_id=? AND revision_id=?",
                        (record["id"], revision_id),
                    ).fetchone()
                    if saved is None:
                        raise RecoveryError("Archived processing revision is missing")
                    saved = json.loads(saved[0])
                    existing_clocks = {
                        key: saved[key] for key in ("first_seen_at", "ingested_at")
                    }
                    if saved != dict(record, **existing_clocks):
                        raise RecoveryError(
                            "Archived processing revision differs from accepted export"
                        )
                    record_ids.add(record["id"])
                member = {key: receipt[key] for key in COMMIT_FIELDS}
                member.update(pf001_revision_id=revision_id, source_revision=fact)
                if not is_delete:
                    member["processing_revision_sha256"] = _processing(fact, version)
                members.append(member)
            if source_ids != set(counts["revisions"]) or record_ids != set(
                counts["records"]
            ):
                raise RecoveryError(
                    "Receipt does not bind the complete archive membership"
                )
        return members

    def build_snapshot(
        self,
        *,
        measurement_start,
        measurement_end,
        knowledge_cutoff_sequence,
        normalizer_version,
    ):
        start, end = _timestamp(measurement_start), _timestamp(measurement_end)
        version = _version(normalizer_version)
        cutoff = knowledge_cutoff_sequence
        if start >= end or type(cutoff) is not int or not 0 <= cutoff <= SAFE_INTEGER:
            raise ValueError("Invalid snapshot interval or cutoff")

        upserts, deletes = defaultdict(list), {}
        source_exports = {}
        with self._v02_write() as db:
            latest = db.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM stage_receipts"
            ).fetchone()[0]
            if cutoff > latest:
                raise ValueError("Cutoff exceeds local durable sequence")
            for export, actual_version, receipt, members in self._accepted(db, cutoff):
                source_exports[receipt["receipt_id"]] = export
                for member in members:
                    fact = member["source_revision"]
                    native = fact["native_id"]
                    if fact["operation"] == "delete":
                        deletes.setdefault((native, fact["revision_sha256"]), member)
                    else:
                        upserts[native].append((actual_version, member))

        deleted = {native for native, _ in deletes}
        observations, losses = [], []
        for native in sorted(set(upserts) - deleted):
            candidates = upserts[native]
            if (
                len(
                    {
                        item["source_revision"]["revision_sha256"]
                        for _, item in candidates
                    }
                )
                != 1
            ):
                raise RecoveryError("Conflicting committed source facts at cutoff")
            event = candidates[0][1]["source_revision"]["observation"]
            if not start <= event["event_start"] < end or event["event_end"] > end:
                continue
            eligible = [item for actual, item in candidates if actual == version]
            if not eligible:
                losses.append(
                    {
                        "field": f"observations/{native}",
                        "reason": "normalizer_unavailable",
                        "locator": None,
                    }
                )
                continue
            if len({item["processing_revision_sha256"] for item in eligible}) != 1:
                raise RecoveryError("Ambiguous processing revision at cutoff")
            if Decimal(event["value"]) <= 0:
                representative = eligible[0]
                for pointer in representative["source_revision"]["locators"]:
                    losses.append(
                        {
                            "field": "value",
                            "reason": "outside_reference_positive_domain",
                            "locator": pointer + "/value",
                        }
                    )
                continue
            observations.append(eligible[0])

        tombstones = [deletes[key] for key in sorted(deletes)]
        for member in observations + tombstones:
            export = source_exports[member["receipt_id"]]
            locators = member["source_revision"]["locators"]
            losses.extend(
                loss
                for loss in export["losses"]
                if loss["locator"] is None
                or any(
                    loss["locator"] == locator
                    or loss["locator"].startswith(locator + "/")
                    for locator in locators
                )
            )
        snapshot = {
            "schema_version": "mse.evidence-snapshot/0.2",
            "scope": self.scope.fields(),
            "archive_id": self.archive_id,
            "purpose": "offline_synthetic_replay",
            "measurement_start": start,
            "measurement_end": end,
            "knowledge_cutoff_sequence": cutoff,
            "normalizer_version": version,
            "coverage": {
                "capture_kind": "partial",
                "backfill_start": None,
                "observed_start": None,
                "observed_end": None,
                "permissions": "unknown",
                "completeness": "unknown",
            },
            "observations": observations,
            "tombstones": tombstones,
            "losses": [
                json.loads(item)
                for item in sorted({canonical_json(loss) for loss in losses})
            ],
        }
        snapshot["snapshot_sha256"] = digest("mse.snapshot/0.2", snapshot)
        self.validators["snapshot"].validate(snapshot)
        return snapshot

    def verify_membership(self, archive_id, scope, member):
        if archive_id != self.archive_id or scope != self.scope.fields():
            return False
        try:
            cutoff = member["commit_sequence"]
            if type(cutoff) is not int or not 1 <= cutoff <= SAFE_INTEGER:
                return False
            with self._v02_write() as db:
                return any(
                    member in members
                    for _, _, _, members in self._accepted(
                        db, cutoff, only_sequence=True
                    )
                )
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            sqlite3.DatabaseError,
            RecoveryError,
            ValidationError,
        ):
            return False

    def verify_snapshot(self, snapshot):
        try:
            self.validators["snapshot"].validate(snapshot)
            expected = self.build_snapshot(
                measurement_start=snapshot["measurement_start"],
                measurement_end=snapshot["measurement_end"],
                knowledge_cutoff_sequence=snapshot["knowledge_cutoff_sequence"],
                normalizer_version=snapshot["normalizer_version"],
            )
            return expected == snapshot
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            sqlite3.DatabaseError,
            RecoveryError,
            ValidationError,
        ):
            return False
