"""Opt-in tests using the actual FORGE authority and a reopened evidence ledger."""
from datetime import datetime, timedelta, timezone
import unittest

from integrations.mse_privacy.custody import Grant, open_custody
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
                      for kind in ("evidence", "vault", "projection")}
        self.paths["evidence_root"] = self.root / "privacy-evidence"
        for path in self.paths.values():
            path.mkdir(mode=0o700)
        self.service, self.credentials = self.custody(1, initialize=True)
        self.handle = self.service.issue_view(self.credentials["writer"])
        self.resolver = LineageResolver(self.private_root, custody=self.service, archive_id=self.archive_id)
        self.projection = {
            "schema_version": "mse.analytics-view/0.1", "view_id": self.handle,
            "purpose": "aggregate_hr_sdnn", "policy_version": "synthetic-aggregate-hr-sdnn/0.1",
            "projection_version": "relative-hour-mean/0.1",
            "time_basis": "relative_60_minute_bucket", "rows": [],
            "projection_loss": ["coverage_unknown"],
        }

    def custody(self, generation, *, initialize=False):
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
                generation, recipient, self.expiry,
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

    def register(self, role="writer"):
        self.resolver.bind(
            self.credentials[role], self.handle, open_ledger=self.open_ledger,
            snapshot_bytes=self.raw, projection_bytes=canonical(self.projection).encode(),
            max_snapshot_bytes=64_000, max_projection_bytes=8192,
        )
        self.service.put_projection(self.credentials["writer"], self.handle, self.projection)

    def audit(self, role="auditor", *, handle=None, resolver=None, credentials=None):
        return (resolver or self.resolver).verify_replay(
            (credentials or self.credentials).get(role, role),
            self.handle if handle is None else handle,
            open_ledger=self.open_ledger, snapshot_bytes=self.raw,
            result_bytes=canonical(self.result).encode(), projection_bytes=canonical(self.projection).encode(),
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

    def test_actual_custody_substitute_and_expired_handle_denied_before_open(self):
        self.register()
        substitute = self.service.issue_view(self.credentials["writer"])
        self.assert_denied(lambda: self.audit(handle=substitute))
        self.assert_denied(lambda: self.audit(handle="av_" + "0" * 32))
        self.now = self.expiry
        self.assert_denied(self.audit)

    def test_revoke_and_current_generation_restart_reject_old_lineage_before_open(self):
        self.register()
        self.assertEqual(self.service.revoke(self.credentials["retain"]), 2)
        self.assert_denied(self.audit)
        current, credentials = self.custody(2)
        reopened = LineageResolver(self.private_root, custody=current, archive_id=self.archive_id)
        self.assert_denied(lambda: self.audit(resolver=reopened, credentials=credentials))


if __name__ == "__main__":
    unittest.main()
