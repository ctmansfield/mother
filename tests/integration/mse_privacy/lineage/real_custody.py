"""Opt-in tests using the actual FORGE authority and a reopened evidence ledger."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from contextlib import closing
from hashlib import sha256

from integrations.mse_privacy.custody import Grant, StoreUnavailable, open_custody
from integrations.mse_privacy.export import AnalyticalExporter, ProjectionBinding
from integrations.mse_privacy.lineage import LineageDenied, LineageResolver
from mse.contracts import canonical

from test_lineage import ReplayFixture


class RealCustodyTests(ReplayFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.opens = 0
        self.scope = self.ledger.scope.fields()
        self.expiry = self.now + timedelta(minutes=10)
        self.paths = {kind + "_root": self.root / kind
                      for kind in ("evidence", "vault", "projection", "authority", "fence")}
        self.paths["evidence_root"] = self.root / "privacy-evidence"
        for path in self.paths.values():
            path.mkdir(mode=0o700)
        self.service, self.credentials = self.custody(initialize=True)
        self.resolver = LineageResolver(self.private_root, custody=self.service, archive_id=self.archive_id)
        self.handle, self.projection = self.publish()

    def publish(self):
        snapshot = json.loads(self.raw)
        binding = ProjectionBinding(
            tuple(self.scope.items()), self.archive_id, snapshot["snapshot_sha256"],
            "audience", 1,
        )
        result = AnalyticalExporter(self.service, self.open_ledger, binding).export(
            self.credentials["writer"], lambda: snapshot
        )
        self.assertEqual(set(result), {"view_id"})
        handle = result["view_id"]
        return handle, self.service.read_projection(self.credentials["analyst"], handle)

    def custody(self, *, initialize=False):
        if not initialize:
            return open_custody(**self.paths, clock=lambda: self.now)
        grants = {}
        for name, role, scope, purpose, recipient in (
            ("writer", "projection_writer", self.scope, "aggregate_hr_sdnn", "audience"),
            ("auditor", "lineage_auditor", self.scope, "aggregate_hr_sdnn", "audience"),
            ("analyst", "analyst", self.scope, "aggregate_hr_sdnn", "audience"),
            ("retain", "retention_recovery", self.scope, "aggregate_hr_sdnn", "audience"),
            ("other-subject", "lineage_auditor", dict(self.scope, subject_id="different"), "aggregate_hr_sdnn", "audience"),
            ("other-recipient", "lineage_auditor", self.scope, "aggregate_hr_sdnn", "different"),
            ("other-purpose", "linkage_custodian", self.scope, "separate-purpose", "audience"),
        ):
            grants[name] = Grant(
                role, scope, purpose, "synthetic-aggregate-hr-sdnn/0.1",
                1, recipient, self.expiry,
            )
        return open_custody(
            **self.paths, grants=grants, initialize=initialize, clock=lambda: self.now
        )

    def open_ledger(self):
        self.opens += 1
        return type(self.ledger)(
            self.ledger.journal.parent, archive_id=self.archive_id,
            scope=self.ledger.scope, schema=self.schema,
        )

    def register(self, role="writer", *, handle=None, projection=None):
        self.resolver.bind(
            self.credentials[role], handle or self.handle, open_ledger=self.open_ledger,
            snapshot_bytes=self.raw, projection_bytes=canonical(projection or self.projection).encode(),
            max_snapshot_bytes=64_000, max_projection_bytes=8192,
        )

    def audit(self, role="auditor", *, handle=None, projection=None, resolver=None):
        return (resolver or self.resolver).verify_replay(
            self.credentials.get(role, role),
            self.handle if handle is None else handle,
            open_ledger=self.open_ledger, snapshot_bytes=self.raw,
            result_bytes=canonical(self.result).encode(), projection_bytes=canonical(projection or self.projection).encode(),
            max_manifest_bytes=128_000, max_projection_bytes=8192, **self.bounds,
        )

    def assert_denied(self, action):
        before = self.opens
        with self.assertRaisesRegex(LineageDenied, "^Lineage unavailable for this authorization$"):
            action()
        self.assertEqual(self.opens, before)

    def test_actual_custody_replay_and_role_scope_recipient_denials(self):
        self.assert_denied(lambda: self.register("analyst"))
        self.register()
        self.assertEqual(self.service.read_projection(self.credentials["analyst"], self.handle), self.projection)
        self.assertEqual(self.audit(), self.result)
        for role in ("analyst", "writer", "other-subject", "other-recipient", "other-purpose", "forged"):
            with self.subTest(role=role):
                self.assert_denied(lambda: self.audit(role))

    def test_swapped_and_rehashed_handles_denied_before_open(self):
        self.register()
        another, payload = self.publish()
        self.register(handle=another, projection=payload)
        self.assertEqual(self.audit(handle=another, projection=payload), self.result)
        self.assert_denied(lambda: self.audit(handle=another))
        made_up = "av_" + sha256(self.handle.encode()).hexdigest()[:32]
        self.assert_denied(lambda: self.audit(handle=made_up))

        # A swapped private database entry cannot masquerade as the other handle,
        # even when both views share the same exact grant binding.
        path = self.private_root / "lineage.sqlite3"
        with closing(sqlite3.connect(path)) as db, db:
            row, = db.execute("SELECT lineage FROM handles WHERE view_id=?", (another,)).fetchone()
            db.execute("UPDATE handles SET lineage=? WHERE view_id=?", (row, self.handle))
        self.assert_denied(self.audit)

    def test_expired_and_unbound_reservations_deny_before_open(self):
        self.register()
        unbound = self.service.issue_view(self.credentials["writer"])
        self.assert_denied(lambda: self.audit(handle=unbound))
        self.now = self.expiry
        self.assert_denied(self.audit)

    def test_restarted_replay_and_stale_restore_respect_durable_fence(self):
        self.register()
        authority = self.paths["authority_root"] / "store.sqlite3"
        registry = self.private_root / "lineage.sqlite3"
        backups = {path: path.read_bytes() for path in (authority, registry)}
        registry.unlink()
        registry.touch(mode=0o600, exist_ok=False)
        registry.write_bytes(backups[registry])
        current, credentials = self.custody()
        self.assertEqual(credentials, {})
        reopened = LineageResolver(self.private_root, custody=current, archive_id=self.archive_id)
        self.assertEqual(self.audit(resolver=reopened), self.result)

        self.assertEqual(self.service.revoke(self.credentials["retain"]), 2)
        self.assert_denied(self.audit)

        registry.write_bytes(backups[registry])
        current, _ = self.custody()
        reopened = LineageResolver(self.private_root, custody=current, archive_id=self.archive_id)
        self.assert_denied(lambda: self.audit(resolver=reopened))

        fence = self.paths["fence_root"] / "store.sqlite3"
        current_fence = fence.read_bytes()
        authority.write_bytes(backups[authority])
        with self.assertRaises(StoreUnavailable):
            self.custody()
        self.assert_denied(lambda: self.audit(resolver=reopened))
        self.assertEqual(fence.read_bytes(), current_fence)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealCustodyTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not (result.testsRun and result.wasSuccessful() and not result.skipped))
