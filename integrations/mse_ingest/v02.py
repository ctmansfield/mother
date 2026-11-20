"""Provisional ATLAS 0.2 boundary over the local PF-001 recovery seam."""

from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker

from mother.physiology.archive import Archive
from mother.physiology.contracts import canonical_json

from . import BatchConflict, LocalIngest, RecoveryError
from .receipt import _timestamp

SAFE_INTEGER = (1 << 53) - 1


def digest(domain, *members):
    def check(value):
        if type(value) is int and abs(value) > SAFE_INTEGER:
            raise ValueError("Integer exceeds the shared safe range")
        if isinstance(value, dict):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("Shared object keys must be strings")
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)
        elif value is not None and type(value) not in (str, int, bool):
            raise ValueError("Unsupported shared JSON value")

    body = [domain, *members]
    check(body)
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def _decimal(lexeme):
    try:
        value = Decimal(lexeme)
    except InvalidOperation as error:
        raise ValueError("Invalid source decimal") from error
    if (
        not value.is_finite()
        or abs(value.adjusted()) > 1024
        or abs(value.as_tuple().exponent) > 1024
    ):
        raise ValueError("Source decimal exceeds local trial bounds")
    fixed = format(value, "f")
    return (
        "0" if not value else fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
    )


def source_digest(scope, revision):
    operation = revision["operation"]
    if operation == "delete":
        values = {_decimal(item) for item in revision["original_deleted_at"]}
        if len(values) != 1:
            raise ValueError("One delete fact must have one exact source timestamp")
        payload = values.pop()
    else:
        observation = revision["observation"]
        payload = {
            "channel": observation["channel"],
            "value": _decimal(observation["original_value"]),
            "unit": observation["original_unit"],
            "start": _decimal(observation["original_start"]),
            "end": _decimal(observation["original_end"]),
            "source_name": observation["source_name"],
            "bundle_id": observation["bundle_id"],
        }
    return digest(
        "mse.source-revision/0.2", scope, revision["native_id"], operation, payload
    )


def requires_pf001_observation(observation):
    return (
        observation["epistemic_type"] != "unknown" and Decimal(observation["value"]) > 0
    )


class IngestV02(LocalIngest):
    """One trusted archive identity and source scope per private trial directory."""

    def __init__(self, root, *, archive_id, scope, schema, **kwargs):
        super().__init__(root, **kwargs)
        self.archive_id = archive_id
        self.scope = scope
        self.validators = {}
        for name in ("receipt", "export", "snapshot"):
            document = {
                "$schema": schema["$schema"],
                "$defs": deepcopy(schema["$defs"]),
                "$ref": f"#/$defs/{name}",
            }
            Draft202012Validator.check_schema(document)
            self.validators[name] = Draft202012Validator(
                document, format_checker=FormatChecker()
            )

    @contextmanager
    def _v02_write(self):
        with self._write() as db:
            identity = canonical_json(
                {"archive_id": self.archive_id, "scope": self.scope.fields()}
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS trial_identity
                          (singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                           identity TEXT NOT NULL)"""
            )
            pinned = db.execute("SELECT identity FROM trial_identity").fetchone()
            if pinned is None:
                if db.execute("SELECT 1 FROM deliveries LIMIT 1").fetchone():
                    raise RecoveryError("Use a fresh directory for the 0.2 trial")
                db.execute("INSERT INTO trial_identity VALUES (1, ?)", (identity,))
            elif pinned["identity"] != identity:
                raise RecoveryError(
                    "Configured archive identity or scope differs from custody"
                )
            db.execute(
                """CREATE TABLE IF NOT EXISTS trial_exports
                          (batch_id TEXT PRIMARY KEY, export_json TEXT NOT NULL)"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS stage_receipts
                          (batch_id TEXT NOT NULL, status TEXT NOT NULL, sequence INTEGER UNIQUE,
                           body TEXT NOT NULL, PRIMARY KEY(batch_id, status))"""
            )
            yield db

    def ingest(self, *args, **kwargs):
        raise TypeError("Use ConnectedIngest.ingest_export for authoritative intake")

    def _ingest(self, original, export, *, adapter_version, normalize):
        """Commit an adapter-verified export with the internal PF-001 mapper."""
        export = deepcopy(export)
        self.validators["export"].validate(export)
        if export["scope"] != self.scope.fields():
            raise ValueError("Export scope differs from local expected scope")
        if not isinstance(original, bytes) or not original:
            raise ValueError("Artifact must contain original bytes")
        if not isinstance(adapter_version, str) or not adapter_version.strip():
            raise ValueError("Adapter version is required")
        artifact = export["artifact"]
        actual = hashlib.sha256(original).hexdigest()
        if (artifact["sha256"], artifact["byte_length"]) != (actual, len(original)):
            raise ValueError("Export artifact digest or length mismatch")
        export_hash = digest("mse.export/0.2", export)
        export_json = canonical_json(export)
        self._upserts(export)
        if any(
            source_digest(export["scope"], revision) != revision["revision_sha256"]
            for revision in export["revisions"]
        ):
            raise ValueError("Export source revision digest mismatch")

        batch = export["batch_id"]
        key = (canonical_json(self.scope.fields()), batch)
        with self._v02_write() as db:
            row = self._delivery(db, key)
            if row is None:
                db.execute(
                    "INSERT INTO deliveries (scope,batch_id,artifact,artifact_sha256,"
                    "export_sha256,source_schema,adapter_version,receipt_id,received_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        *key,
                        original,
                        actual,
                        export_hash,
                        artifact["source_schema"],
                        adapter_version,
                        "local:" + uuid4().hex,
                        _timestamp(self.clock()),
                    ),
                )
                row = self._delivery(db, key)
                db.execute(
                    "INSERT INTO trial_exports VALUES (?,?)", (batch, export_json)
                )
                self._publish(db, row, "durably_received")
            else:
                self._verify_custody(db, row)
                if (row["artifact"], row["export_sha256"], row["adapter_version"]) != (
                    original,
                    export_hash,
                    adapter_version,
                ):
                    raise BatchConflict("Scoped batch already binds different inputs")
        self._checkpoint("custody")

        with self._v02_write() as db:
            row = self._delivery(db, key)
            self._verify_custody(db, row)
            receipt = self._terminal(db, row)
            if receipt is None:
                with Archive(self.archive) as archive:
                    if self._conflicts(db, archive, export):
                        receipt = self._publish(
                            db, row, "quarantined", reason="upsert_conflict"
                        )
                    else:

                        def mapped(original, context):
                            revisions, records = normalize(original, context)
                            revisions, records = self._check_mapping(
                                export, list(revisions), list(records)
                            )
                            return revisions, self._preserve_first_receipt(
                                archive, records
                            )

                        run = self._archive_run(archive, self.scope, row, mapped)
                        receipt = self._publish(db, row, "normalized", run["run_id"])
                        db.execute(
                            "UPDATE deliveries SET run_id=?,committed_at=?,commit_sequence=?"
                            " WHERE scope=? AND batch_id=?",
                            (
                                run["run_id"],
                                run["completed_at"],
                                receipt["commit_sequence"],
                                *key,
                            ),
                        )
        self._checkpoint("receipt")
        return receipt

    @staticmethod
    def _preserve_first_receipt(archive, records):
        result = []
        for record in records:
            existing = archive.connection.execute(
                "SELECT record_json FROM normalized_records WHERE record_id=?",
                (record["id"],),
            ).fetchone()
            if existing is not None:
                immutable = json.loads(existing[0])
                # Repeated sightings have their own run and receipt. The
                # immutable processing row retains its original local clocks.
                record = dict(
                    record,
                    first_seen_at=immutable["first_seen_at"],
                    ingested_at=immutable["ingested_at"],
                )
            result.append(record)
        return result

    @staticmethod
    def _requires_record(observation):
        return requires_pf001_observation(observation)

    def _check_mapping(self, export, revisions, records):
        facts = export["revisions"]
        expected = Counter(
            (
                fact["native_id"],
                "deleted" if fact["operation"] == "delete" else "accepted",
                fact["revision_sha256"],
            )
            for fact in facts
        )
        actual = Counter(
            (
                item.get("native_id"),
                item.get("disposition"),
                json.loads(item["raw_json"]).get("mse_source_revision_sha256"),
            )
            for item in revisions
        )
        if actual != expected:
            raise ValueError(
                "PF-001 mapping does not cover exactly the exported source facts"
            )
        by_id = {item["revision_id"]: item for item in revisions}
        if len(by_id) != len(revisions):
            raise ValueError("PF-001 mapping repeats a revision identity")
        observations = {
            fact["native_id"]: fact["observation"]
            for fact in facts
            if fact["operation"] == "upsert"
        }
        normalized = Counter()
        for record in records:
            revision = by_id.get(record.get("source_revision_id"))
            if revision is None or revision["disposition"] != "accepted":
                raise ValueError("PF-001 observation has no mapped upsert")
            native = revision["native_id"]
            if record.get("epistemic_type") != observations[native]["epistemic_type"]:
                raise ValueError("PF-001 observation changes epistemic class")
            normalized[native] += 1
        if normalized != Counter(
            {
                native: 1
                for native, observation in observations.items()
                if self._requires_record(observation)
            }
        ):
            raise ValueError(
                "PF-001 observation roster does not match qualified upserts"
            )
        return revisions, records

    @staticmethod
    def _upserts(export):
        facts = {}
        seen = set()
        for revision in export["revisions"]:
            native, operation, revision_hash = (
                revision["native_id"],
                revision["operation"],
                revision["revision_sha256"],
            )
            key = (native, operation, revision_hash)
            if key in seen:
                raise ValueError("Duplicate source fact")
            seen.add(key)
            if operation == "upsert":
                if native in facts:
                    raise ValueError("Multiple unequal source upserts in one export")
                facts[native] = revision_hash
        return facts

    def _conflicts(self, db, archive, export):
        current = self._upserts(export)
        completed = {
            run["request"].get("mse_receipt_id")
            for run in archive.import_runs(
                self.scope.archive_source, self.scope.collection
            )
            if run["status"] == "complete"
        }
        for row in db.execute(
            """SELECT e.export_json, d.receipt_id FROM trial_exports e
               JOIN deliveries d ON d.batch_id=e.batch_id
               WHERE e.batch_id<>?""",
            (export["batch_id"],),
        ):
            if row["receipt_id"] in completed:
                previous = self._upserts(json.loads(row["export_json"]))
                if any(
                    key in previous and previous[key] != value
                    for key, value in current.items()
                ):
                    return True
        return False

    def _publish(self, db, row, status, run_id=None, reason=None):
        sequence = db.execute("INSERT INTO commits DEFAULT VALUES").lastrowid
        committed = _timestamp(self.clock())
        prior = db.execute(
            "SELECT body FROM stage_receipts WHERE batch_id=? ORDER BY sequence DESC LIMIT 1",
            (row["batch_id"],),
        ).fetchone()
        lower = (
            json.loads(prior["body"])["committed_at"] if prior else row["received_at"]
        )
        if committed < lower:
            raise RecoveryError("Receipt stage clock moved backwards")
        result = self._receipt(row, status, sequence, committed, run_id, reason)
        db.execute(
            "INSERT INTO stage_receipts VALUES (?,?,?,?)",
            (row["batch_id"], status, sequence, canonical_json(result)),
        )
        return result

    def _receipt(self, row, status, sequence, committed, run_id, reason):
        result = {
            "schema_version": "mse.ingest-receipt/0.2",
            "archive_id": self.archive_id,
            "scope": self.scope.fields(),
            "batch_id": row["batch_id"],
            "artifact_sha256": row["artifact_sha256"],
            "byte_length": len(row["artifact"]),
            "source_schema": row["source_schema"],
            "export_sha256": row["export_sha256"],
            "receipt_id": digest(
                "mse.receipt-id/0.2",
                self.archive_id,
                self.scope.fields(),
                row["batch_id"],
            ),
            "status": status,
            "mother_received_at": row["received_at"],
            "committed_at": committed,
            "commit_sequence": sequence,
            "pf001_run_id": run_id,
            "reason_code": reason,
        }
        self.validators["receipt"].validate(result)
        return result

    def _verify_custody(self, db, row):
        if (
            not row
            or hashlib.sha256(row["artifact"]).hexdigest() != row["artifact_sha256"]
        ):
            raise RecoveryError("Retained artifact digest mismatch")
        saved = db.execute(
            "SELECT export_json FROM trial_exports WHERE batch_id=?", (row["batch_id"],)
        ).fetchone()
        if (
            not saved
            or digest("mse.export/0.2", json.loads(saved["export_json"]))
            != row["export_sha256"]
        ):
            raise RecoveryError("Stored export digest mismatch")
        artifact = json.loads(saved["export_json"])["artifact"]
        if (artifact["sha256"], artifact["byte_length"], artifact["source_schema"]) != (
            row["artifact_sha256"],
            len(row["artifact"]),
            row["source_schema"],
        ):
            raise RecoveryError(
                "Stored export does not match the original custody record"
            )

    def _terminal(self, db, row):
        stage = db.execute(
            "SELECT * FROM stage_receipts WHERE batch_id=? ORDER BY sequence DESC LIMIT 1",
            (row["batch_id"],),
        ).fetchone()
        if stage is None:
            raise RecoveryError("Missing custody stage")
        status = stage["status"]
        saved = json.loads(stage["body"])
        expected = self._receipt(
            row,
            status,
            stage["sequence"],
            saved["committed_at"],
            row["run_id"] if status == "normalized" else None,
            "upsert_conflict" if status == "quarantined" else None,
        )
        if saved != expected:
            raise RecoveryError("Stored receipt metadata mismatch")
        if status == "normalized":
            if (
                row["commit_sequence"] != stage["sequence"]
                or not self.archive.is_file()
            ):
                raise RecoveryError("Missing normalized stage or PF-001 archive")
            with Archive(self.archive) as archive:
                run = self._archive_run(archive, self.scope, row, None)
            if row["committed_at"] != run["completed_at"]:
                raise RecoveryError("PF-001 completion timestamp mismatch")
        return saved if status != "durably_received" else None

    def verify_receipt(self, candidate):
        """Compare to a reopened authoritative stage under local archive/scope."""
        self.validators["receipt"].validate(candidate)
        if (
            candidate["archive_id"] != self.archive_id
            or candidate["scope"] != self.scope.fields()
        ):
            raise ValueError(
                "Receipt archive identity or scope differs from local expectation"
            )
        expected = self.read_receipt(candidate["batch_id"], status=candidate["status"])
        if expected != candidate:
            raise RecoveryError("Receipt differs from reopened durable stage")
        return candidate

    def read_receipt(self, batch_id, *, status=None):
        """Read a durable stage, or the latest stage, from authoritative custody."""
        key = (canonical_json(self.scope.fields()), batch_id)
        with self._v02_write() as db:
            row = self._delivery(db, key)
            self._verify_custody(db, row)
            self._terminal(db, row)
            stage = db.execute(
                "SELECT * FROM stage_receipts WHERE batch_id=? "
                "AND (? IS NULL OR status=?) ORDER BY sequence DESC LIMIT 1",
                (batch_id, status, status),
            ).fetchone()
            if stage is None:
                raise RecoveryError("No matching durable receipt stage")
            saved = json.loads(stage["body"])
            self.validators["receipt"].validate(saved)
            return saved

    def facts_at(self, cutoff):
        """Return local accepted source facts, with deletions dominant at cutoff."""
        if type(cutoff) is not int or not 0 <= cutoff <= SAFE_INTEGER:
            raise ValueError("Invalid local commit cutoff")
        upserts, deletes = {}, {}
        with self._v02_write() as db:
            latest = db.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM stage_receipts"
            ).fetchone()[0]
            if cutoff > latest:
                raise ValueError("Cutoff exceeds local durable sequence")
            rows = db.execute(
                """SELECT e.export_json, s.body FROM stage_receipts s
                   JOIN trial_exports e USING(batch_id)
                   WHERE s.status='normalized' AND s.sequence<=? ORDER BY s.sequence""",
                (cutoff,),
            )
            for row in rows:
                receipt = json.loads(row["body"])
                delivery = self._delivery(
                    db, (canonical_json(self.scope.fields()), receipt["batch_id"])
                )
                self._verify_custody(db, delivery)
                self._terminal(db, delivery)
                for fact in json.loads(row["export_json"])["revisions"]:
                    native = fact["native_id"]
                    if fact["operation"] == "delete":
                        deletes.setdefault(
                            (native, fact["revision_sha256"]), (fact, receipt)
                        )
                    else:
                        upserts.setdefault(native, (fact, receipt))
        deleted = {native for native, _ in deletes}
        return {
            "observations": [upserts[key] for key in sorted(set(upserts) - deleted)],
            "tombstones": [deletes[key] for key in sorted(deletes)],
        }
