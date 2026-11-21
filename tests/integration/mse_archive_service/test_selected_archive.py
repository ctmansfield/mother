"""Round-trip ATLAS synthetic shapes through the isolated selected archive."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
import unittest

from integrations.mse_archive_service.selected import SelectedArchive
from integrations.mse_archive_service.store import PrivateArchive
from integrations.mse_ingest import BatchConflict, Scope
from mother.physiology.contracts import canonical_json

VECTORS = json.loads(
    Path("docs/mse/integration/selected-healthkit/synthetic-vectors.json").read_bytes()
)


def encode(value):
    return canonical_json(value).encode()


def digest(value):
    return sha256(value).hexdigest()


class SelectedArchiveTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.batch = deepcopy(VECTORS["batch"])
        self.scope = self.batch["scope"]
        self.batch_id = self.batch["batch_id"]
        self.original = encode(self.batch)
        self.assertEqual(digest(self.original), VECTORS["canonical_body_sha256"])

    def archive(self, *extra, scope=None):
        return SelectedArchive(
            self.root,
            archive_id=VECTORS["receipt"]["archive_id"],
            scope=self.scope if scope is None else scope,
            allowed_artifact_sha256=[digest(body) for body in (self.original, *extra)],
        )

    def batch_bytes(self, batch, records):
        return encode(dict(self.batch, batch_id=batch, records=records))

    def exported(self, archive, start, through, **kwargs):
        envelope = json.loads(archive.export(start, through, **kwargs))
        self.assertEqual(envelope["view_sha256"], digest(encode(envelope["view"])))
        return envelope["view"]["rows"]

    def test_exact_all_shape_roundtrip_and_reopen(self):
        sleep = next(row for row in self.batch["records"] if row.get("kind") == "sleep")
        workout = next(
            row for row in self.batch["records"] if row.get("kind") == "workout"
        )
        oxygen = next(
            row for row in self.batch["records"] if row["metric"] == "oxygen_saturation"
        )
        extras = [
            dict(
                sleep,
                category=category,
                unknown_category_code=99 if category == "unknown" else None,
                native_id=f"11111111-1111-1111-1111-{index:012d}",
            )
            for index, category in enumerate(
                ("awake", "asleep_unspecified", "asleep_core", "asleep_deep", "unknown")
            )
        ]
        extras += [
            dict(
                workout,
                native_id="22222222-2222-2222-2222-222222222222",
                distance_m="502.78",
                energy_kcal=None,
            ),
            dict(
                oxygen,
                native_id="33333333-3333-3333-3333-333333333333",
                value="1.4",
                event_start=oxygen["event_end"],
            ),
        ]
        extra_body = self.batch_bytes("extra-shapes", extras)
        archive = self.archive(extra_body)
        archive.initialize()
        path = f"/v2/archive/batches/{self.batch_id}"
        raw_receipt = archive.batch_request(
            "PUT", path, content_type="application/json", original=self.original
        )
        receipt = json.loads(raw_receipt)
        self.assertEqual(archive.batch_request("GET", path), raw_receipt)
        with self.assertRaisesRegex(ValueError, "invalid selected batch request"):
            archive.batch_request("GET", path, original=self.original)
        with self.assertRaisesRegex(ValueError, "invalid selected batch path"):
            archive.batch_request("GET", f"/v1/archive/batches/{self.batch_id}")
        for field in (
            "archive_id",
            "scope",
            "batch_id",
            "artifact_sha256",
            "byte_length",
            "receipt_id",
            "schema_version",
            "status",
        ):
            self.assertEqual(receipt[field], VECTORS["receipt"][field])
        self.assertTrue(receipt["archive_commit_id"])
        archive.put("extra-shapes", extra_body)
        reopened = self.archive(extra_body)
        reopened.check_startup()
        self.assertEqual(reopened.put(self.batch_id, self.original), receipt)
        self.assertEqual(reopened.original(self.batch_id), self.original)
        rows = self.exported(reopened, 1, 1)
        self.assertEqual([row["record"] for row in rows], self.batch["records"])
        self.assertTrue(all(row["receipt"] == receipt for row in rows))
        self.assertEqual(len({row["record"]["metric"] for row in rows}), 14)
        extra_rows = self.exported(reopened, 2, 2)
        self.assertEqual([row["record"] for row in extra_rows], extras)
        self.assertEqual(
            extra_rows[-1]["processing_finding"], "oxygen_fraction_out_of_domain"
        )
        self.assertEqual(
            {
                row["record"]["category"]
                for row in rows + extra_rows
                if row["record"].get("kind") == "sleep"
            },
            {
                "in_bed",
                "awake",
                "asleep_unspecified",
                "asleep_core",
                "asleep_deep",
                "asleep_rem",
                "unknown",
            },
        )
        around_point = self.exported(
            reopened,
            2,
            2,
            event_window=("2026-11-21T00:30:00.000000Z", "2026-11-21T00:31:00.000000Z"),
        )
        self.assertEqual([row["record"] for row in around_point], [extras[-1]])

    def test_history_tombstones_and_conflict_quarantine(self):
        initial = next(
            row for row in self.batch["records"] if row.get("kind") == "quantity"
        )
        deletion = {
            key: initial[key]
            for key in ("metric", "native_id", "collector_received_at")
        }
        deletion["operation"] = "delete"
        unknown = dict(deletion, native_id="ffffffff-ffff-ffff-ffff-ffffffffffff")
        deleted = self.batch_bytes("deleted", [deletion, unknown])
        observed_again = dict(
            initial, collector_received_at="2026-11-22T00:00:00.000000Z"
        )
        retry = self.batch_bytes("observed-again", [observed_again])
        changed = self.batch_bytes("changed", [dict(initial, value="12")])
        changed_same_batch = self.batch_bytes(
            self.batch_id, [dict(initial, value="12")]
        )
        archive = self.archive(deleted, retry, changed, changed_same_batch)
        archive.initialize()
        archive.put(self.batch_id, self.original)
        archive.put("deleted", deleted)
        archive.put("observed-again", retry)
        quarantine = archive.put("changed", changed)
        self.assertEqual(quarantine["status"], "quarantined")
        self.assertIsNone(quarantine["archive_commit_id"])
        self.assertEqual(archive.original("changed"), changed)
        self.assertEqual(archive.get("changed"), quarantine)
        with self.assertRaises(BatchConflict):
            archive.put(self.batch_id, changed_same_batch)
        history = self.exported(archive, 1, 4)
        related = [
            row for row in history if row["record"]["native_id"] == initial["native_id"]
        ]
        self.assertEqual(
            [row["record"]["operation"] for row in related],
            ["upsert", "delete", "upsert"],
        )
        self.assertEqual(
            related[0]["source_fact_sha256"], related[2]["source_fact_sha256"]
        )
        self.assertTrue(any(row["record"] == unknown for row in history))
        self.assertFalse(
            any(row["receipt"]["batch_id"] == "changed" for row in history)
        )
        before = self.exported(archive, 1, 1, current=True)
        after = self.exported(archive, 1, 4, current=True)
        self.assertTrue(any(row["record"] == initial for row in before))
        self.assertFalse(
            any(row["record"]["native_id"] == initial["native_id"] for row in after)
        )

    def test_refusals_preserve_prior_layout_and_reject_invalid_input(self):
        bad = {case["name"]: encode(case["document"]) for case in VECTORS["invalid"]}
        bad["duplicate"] = self.original.replace(b'"scope":', b'"scope":{},"scope":', 1)
        reversed_row = dict(
            self.batch["records"][0], event_start="2026-11-22T00:00:00.000000Z"
        )
        bad["reversed"] = self.batch_bytes(self.batch_id, [reversed_row])
        archive = self.archive(*bad.values())
        with TemporaryDirectory() as old_path:
            old_root = Path(old_path).resolve()
            legacy = PrivateArchive(
                old_root,
                archive_id="legacy-archive",
                scope=Scope(
                    "synthetic-legacy", "healthkit", "legacy-store", "healtharchive"
                ),
            )
            legacy.initialize()
            before = {
                path.name: digest(path.read_bytes()) for path in old_root.iterdir()
            }
            incompatible = SelectedArchive(
                old_root,
                archive_id=archive.archive_id,
                scope=self.scope,
                allowed_artifact_sha256=[digest(self.original)],
            )
            with self.assertRaisesRegex(ValueError, "empty root"):
                incompatible.initialize()
            self.assertEqual(
                {path.name: digest(path.read_bytes()) for path in old_root.iterdir()},
                before,
            )
            legacy.check_startup()
        archive.initialize()
        with self.assertRaisesRegex(ValueError, "empty root"):
            archive.initialize()
        for case, payload in bad.items():
            with self.subTest(case=case), self.assertRaises(ValueError):
                archive.put(self.batch_id, payload)
        with self.assertRaisesRegex(ValueError, "not admitted"):
            archive.put(self.batch_id, b"{}")
        with self.assertRaisesRegex(ValueError, "scope or batch mismatch"):
            archive.put("different", self.original)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.archive(
                scope=dict(self.scope, source_instance="different")
            ).check_startup()
        with self.assertRaisesRegex(ValueError, "synthetic-only"):
            self.archive(scope=dict(self.scope, subject_id="protected-subject"))
        with self.assertRaises(KeyError):
            archive.get(self.batch_id)

    def test_corrupt_sighting_refuses_receipt(self):
        archive = self.archive()
        archive.initialize()
        archive.put(self.batch_id, self.original)
        db = sqlite3.connect(archive.path)
        try:
            with db:
                db.execute("DELETE FROM sightings WHERE ordinal=0")
        finally:
            db.close()
        with self.assertRaisesRegex(ValueError, "sighting integrity"):
            self.archive().get(self.batch_id)

    def test_concurrent_retry_has_one_commit(self):
        archive = self.archive()
        archive.initialize()
        barrier = Barrier(2)
        receipts = []

        def submit():
            barrier.wait(timeout=3)
            receipts.append(archive.put(self.batch_id, self.original))

        threads = [Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(receipts[0]["commit_sequence"], 1)
