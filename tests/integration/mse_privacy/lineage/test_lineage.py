"""Synthetic local evidence and role-boundary tests for the private resolver."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from integrations.healthbridge.ingest import ingest_capture
from integrations.mse_ingest import Scope
from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
from integrations.mse_privacy.lineage import LineageDenied, LineageResolver
from integrations.mse_snapshot.ledger import replay_ledger_snapshot
from mse.contracts import canonical


class ScopedAuthority:
    """Independent test authority with exact role/view binding, denials and lifecycle."""

    def __init__(self, binding):
        self.binding = binding
        self.view_id = "av_" + "1" * 32
        self.credentials = {"worker": "bind", "audit": "resolve"}
        self.active = True

    def authorize_lineage(self, credential, view_id, *, operation):
        if not (
            self.active and view_id == self.view_id
            and self.credentials.get(credential) == operation
        ):
            raise PermissionError("/synthetic/private/key and sensitive internal context")
        return deepcopy(self.binding)


class LineageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private_root = self.root / "private-lineage"
        self.fixture_dir = Path("docs/mse/integration/contracts")
        vectors = json.loads((self.fixture_dir / "golden-vectors.json").read_bytes())
        schema = json.loads((self.fixture_dir / "offline-integration.schema.json").read_bytes())
        scope = vectors["snapshot"]["scope"]
        archive_id = self.archive_id = vectors["snapshot"]["archive_id"]

        self.ledger = ConnectedIngest(
            self.root / "evidence", archive_id=archive_id, scope=Scope(**scope), schema=schema,
        )
        receipt = ingest_capture(
            self.ledger, vectors["source_utf8"].encode(),
            batch_id="privacy-trial", capture_id="privacy-trial", capture_kind="full_file",
        ).receipt
        snapshot = self.ledger.build_snapshot(
            measurement_start=vectors["snapshot"]["measurement_start"],
            measurement_end=vectors["snapshot"]["measurement_end"],
            knowledge_cutoff_sequence=receipt["commit_sequence"],
            normalizer_version=NORMALIZER_VERSION,
        )
        self.raw = canonical(snapshot).encode()
        self.authority = ScopedAuthority({
            "scope": scope,
            "purpose": "aggregate_hr_sdnn", "policy_version": "synthetic-aggregate-hr-sdnn/0.1",
            "generation": 1, "recipient": "synthetic-recipient", "expires_at": "2099-01-01T00:00:00Z",
        })
        self.handle = self.authority.view_id
        self.resolver = LineageResolver(self.private_root, custody=self.authority, archive_id=self.archive_id)
        self.projection = {
            "schema_version": "mse.analytics-view/0.1", "view_id": self.handle,
            "purpose": "aggregate_hr_sdnn", "policy_version": "synthetic-aggregate-hr-sdnn/0.1",
            "projection_version": "relative-hour-mean/0.1",
            "time_basis": "relative_60_minute_bucket", "rows": [],
            "loss_codes": ["insufficient_coverage"],
        }
        self.bounds = {"max_bytes": 64_000, "max_members": 128}
        self.result = replay_ledger_snapshot(
            self.raw, ledger=self.ledger, expected_scope=scope,
            expected_archive_id=archive_id, **self.bounds,
        )

    def bind(self, credential="worker"):
        return self.resolver.bind(
            credential, self.handle, ledger=self.ledger,
            snapshot_bytes=self.raw, projection_bytes=canonical(self.projection).encode(),
            max_snapshot_bytes=64_000, max_projection_bytes=8192,
        )

    def verify(self, result=None):
        return self.resolver.verify_replay(
            "audit", self.handle, ledger=self.ledger, snapshot_bytes=self.raw,
            result_bytes=canonical(self.result if result is None else result).encode(),
            projection_bytes=canonical(self.projection).encode(),
            max_manifest_bytes=128_000, max_projection_bytes=8192, **self.bounds,
        )

    def test_verified_private_replay_and_cross_role_errors(self):
        self.assertIsNone(self.bind())
        self.assertIsNone(self.bind())
        self.assertEqual(self.verify(), self.result)
        for credential in ("analyst", "worker", "missing"):
            with self.subTest(role=credential), self.assertRaises(LineageDenied) as denied:
                self.resolver.resolve(credential, self.handle)
            self.assertEqual(str(denied.exception), "Lineage unavailable for this authorization")
            self.assertIsNone(denied.exception.__cause__)
        with self.assertRaises(LineageDenied):
            self.bind("audit")
        changed = deepcopy(self.result)
        changed["status"] = "unavailable"
        with self.assertRaises(LineageDenied):
            self.verify(changed)

    def test_new_generation_or_purpose_denies_even_restored_mapping(self):
        self.bind()
        path = self.private_root / "lineage.sqlite3"
        backup = self.root / "old.sqlite3"
        shutil.copyfile(path, backup)
        for field, update in (
            ("generation", 2), ("purpose", "other-purpose"),
            ("recipient", "other-recipient"), ("expires_at", "2100-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                original = self.authority.binding[field]
                self.authority.binding[field] = update
                shutil.copyfile(backup, path)
                reopened = LineageResolver(self.private_root, custody=self.authority, archive_id=self.archive_id)
                with self.assertRaises(LineageDenied):
                    reopened.resolve("audit", self.handle)
                self.authority.binding[field] = original
        self.authority.active = False
        with self.assertRaises(LineageDenied):
            self.resolver.resolve("audit", self.handle)

    def test_missing_vault_and_unapproved_scope_deny(self):
        with self.assertRaises(LineageDenied):
            self.resolver.resolve("audit", self.handle)
        self.authority.binding["scope"]["subject_id"] = "other"
        with self.assertRaises(LineageDenied):
            self.bind()


if __name__ == "__main__":
    unittest.main()
