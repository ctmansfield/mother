"""Explicit initialization and bounded, scoped read views."""

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from contextlib import closing

from integrations.healthbridge.ingest import ingest_capture
from integrations.healthbridge.capture import CaptureLimits
from integrations.mse_ingest.connected import (
    ConnectedIngest,
    NORMALIZER_VERSION,
    _record,
)
from integrations.mse_ingest.receipt import _timestamp
from mother.physiology.archive import Archive
from mother.physiology.contracts import canonical_json

SCHEMA_SHA256 = "12b93fbebf37a15d91c4ad56288dac7a62b91910fc98baaf8d2184b5c602688a"
SCHEMA_PATH = "docs/mse/integration/contracts/offline-integration.schema.json"
MAX_ROWS = 1024
MAX_SEQUENCE = 256
MAX_BATCHES = 64
CAPTURE_LIMITS = CaptureLimits(
    byte_length=128 * 1024, records=128, depth=16, numeric_token_length=80
)


class UnknownBatch(LookupError):
    pass


class CapacityExceeded(ValueError):
    pass


def schema():
    data = (Path(__file__).resolve().parents[2] / SCHEMA_PATH).read_bytes()
    if sha256(data).hexdigest() != SCHEMA_SHA256:
        raise ValueError("frozen schema digest mismatch")
    return json.loads(data)


def catalog(path):
    if not path.is_file():
        raise ValueError("expected initialized archive pair")
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=3)
    ) as db:
        rows = db.execute(
            "SELECT type,name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name"
        ).fetchall()
    return sha256(canonical_json(rows).encode()).hexdigest()


class PrivateArchive(ConnectedIngest):
    def __init__(self, root, *, archive_id, scope):
        super().__init__(root, archive_id=archive_id, scope=scope, schema=schema())
        self.marker = root / "initialization.json"

    def identity(self):
        return {
            "layout": "mse-private-archive-sqlite/1",
            "archive_id": self.archive_id,
            "scope": self.scope.fields(),
            "schema_sha256": SCHEMA_SHA256,
            "custody_catalog_sha256": catalog(self.journal),
            "archive_catalog_sha256": catalog(self.archive),
        }

    def initialize(self):
        if any(self.marker.parent.iterdir()):
            raise ValueError("initialization requires a fresh private archive root")
        with self._v02_write():
            with Archive(self.archive):
                pass
        descriptor = os.open(
            self.marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(canonical_json(self.identity()))
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(self.marker.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def check_startup(self):
        self._validate_paths()
        if self.marker.is_symlink() or not self.marker.is_file():
            raise ValueError("archive initialization marker is absent")
        if (
            self.marker.stat().st_uid != os.geteuid()
            or self.marker.stat().st_mode & 0o077
        ):
            raise ValueError("archive initialization marker permissions mismatch")
        if json.loads(self.marker.read_bytes()) != self.identity():
            raise ValueError("archive initialization identity or catalog mismatch")
        with closing(
            sqlite3.connect(self.journal.as_uri() + "?mode=ro", uri=True)
        ) as db:
            row = db.execute(
                "SELECT identity FROM trial_identity WHERE singleton=1"
            ).fetchone()
        if not row or json.loads(row[0]) != {
            "archive_id": self.archive_id,
            "scope": self.scope.fields(),
        }:
            raise ValueError("archive journal identity mismatch")
        with closing(
            sqlite3.connect(self.archive.as_uri() + "?mode=ro", uri=True)
        ) as db:
            versions = db.execute(
                "SELECT version,contract_version FROM schema_versions"
            ).fetchall()
        if versions != [(1, "1.0.0")]:
            raise ValueError("PF-001 schema version mismatch")

    def submit(self, batch, original):
        with self._v02_write() as db:
            row = self._delivery(db, (canonical_json(self.scope.fields()), batch))
            count = db.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
            if row is None and count >= MAX_BATCHES:
                raise CapacityExceeded("synthetic archive capacity reached")
        return ingest_capture(
            self,
            original,
            batch_id=batch,
            capture_id=batch,
            capture_kind="partial",
            limits=CAPTURE_LIMITS,
        ).receipt

    def receipt(self, batch):
        with self._v02_write() as db:
            if self._delivery(db, (canonical_json(self.scope.fields()), batch)) is None:
                raise UnknownBatch()
        return self.verify_receipt(self.read_receipt(batch))

    def read_view(
        self,
        view,
        start,
        through,
        *,
        metric=None,
        mode="history",
        measurement_start=None,
        measurement_end=None,
        batch_id=None,
        receipt_id=None,
    ):
        if not 1 <= start <= through <= MAX_SEQUENCE or through - start >= 64:
            raise ValueError("invalid commit range")
        if metric not in (None, "heart_rate", "hrv_sdnn") or mode not in (
            "history",
            "current",
        ):
            raise ValueError("invalid view selector")
        start_time = _timestamp(measurement_start) if measurement_start else None
        end_time = _timestamp(measurement_end) if measurement_end else None
        if (start_time is None) != (end_time is None) or (
            start_time is not None and start_time >= end_time
        ):
            raise ValueError("invalid measurement interval")
        receipts_only = view == "archive_receipts_v1"
        if receipts_only and (mode != "history" or metric or start_time):
            raise ValueError("invalid receipt selector")
        if not receipts_only and (batch_id or receipt_id):
            raise ValueError("invalid revision selector")
        selected = None
        if mode == "current":
            if view != "archive_revisions_v1" or start != 1 or not start_time:
                raise ValueError("current view requires a complete cutoff and interval")
            snapshot = self.build_snapshot(
                measurement_start=start_time,
                measurement_end=end_time,
                knowledge_cutoff_sequence=through,
                normalizer_version=NORMALIZER_VERSION,
            )
            selected = {
                (item["receipt_id"], item["pf001_revision_id"])
                for item in snapshot["observations"] + snapshot["tombstones"]
            }

        rows = []
        with self._v02_write() as db:
            latest = db.execute(
                "SELECT COALESCE(MAX(sequence),0) FROM commits"
            ).fetchone()[0]
            if through > latest:
                raise ValueError("cutoff exceeds current archive sequence")
            if receipts_only:
                stages = db.execute(
                    "SELECT body FROM stage_receipts WHERE sequence BETWEEN ? AND ? ORDER BY sequence",
                    (start, through),
                ).fetchall()
            else:
                stages = []
                for export, version, receipt, members in self._accepted(db, through):
                    if receipt["commit_sequence"] < start:
                        continue
                    for member in members:
                        key = (member["receipt_id"], member["pf001_revision_id"])
                        if selected is not None and key not in selected:
                            continue
                        revision = member["source_revision"]
                        observation = revision.get("observation")
                        if observation is not None and (
                            (metric and observation["channel"] != metric)
                            or (
                                start_time
                                and not (
                                    start_time <= observation["event_start"] < end_time
                                    and observation["event_end"] <= end_time
                                )
                            )
                        ):
                            continue
                        rows.append(self._relation(export, version, member))
                        if len(rows) > MAX_ROWS:
                            raise CapacityExceeded("narrow the view range")
        for (body,) in stages:
            receipt = json.loads(body)
            if (batch_id is None or receipt["batch_id"] == batch_id) and (
                receipt_id is None or receipt["receipt_id"] == receipt_id
            ):
                rows.append(self.verify_receipt(receipt))
        return {
            "view": view,
            "archive_id": self.archive_id,
            "scope": self.scope.fields(),
            "query": {
                "from": start,
                "through": through,
                "metric": metric,
                "mode": mode,
                "measurement_start": start_time,
                "measurement_end": end_time,
                "batch_id": batch_id,
                "receipt_id": receipt_id,
            },
            "coverage": "unknown",
            "rows": rows,
        }

    def _relation(self, export, version, member):
        revision = member["source_revision"]
        observation = revision.get("observation")
        display = {
            "operation": revision["operation"],
            "revision_sha256": revision["revision_sha256"],
        }
        if observation is not None:
            display["observation"] = {
                name: observation[name]
                for name in (
                    "channel",
                    "value",
                    "unit",
                    "event_start",
                    "event_end",
                    "source_available_at",
                    "collector_received_at",
                    "epistemic_type",
                )
            }
        else:
            display["deleted_at"] = revision["deleted_at"]
        record = _record(self.scope, revision, version, member["mother_received_at"])
        reasons = {
            (loss["field"], loss["reason"])
            for loss in export["losses"]
            if loss["locator"] is None
            or any(
                loss["locator"] == pointer or loss["locator"].startswith(pointer + "/")
                for pointer in revision["locators"]
            )
        }
        if observation is not None and record is None:
            reasons.add(("value", "source_only"))
        return {
            **{
                name: member[name]
                for name in (
                    "artifact_sha256",
                    "receipt_id",
                    "mother_received_at",
                    "committed_at",
                    "commit_sequence",
                )
            },
            "source_revision_id": member["pf001_revision_id"],
            "processing_revision_id": record["id"] if record else None,
            "processing_revision_sha256": (
                member["processing_revision_sha256"] if record else None
            ),
            "normalizer_version": version,
            "source_revision": display,
            "quality_losses": [
                dict(field=field, reason=reason) for field, reason in sorted(reasons)
            ],
        }

    def original(self, digest):
        with self._v02_write() as db:
            row = db.execute(
                "SELECT batch_id,artifact FROM deliveries WHERE scope=? AND artifact_sha256=? "
                "ORDER BY batch_id LIMIT 1",
                (canonical_json(self.scope.fields()), digest),
            ).fetchone()
            if row is None:
                raise UnknownBatch()
            batch, original = row
        receipt = self.receipt(batch)
        if (
            sha256(original).hexdigest() != digest
            or receipt["artifact_sha256"] != digest
        ):
            raise ValueError("original integrity mismatch")
        return original
