"""Executable synthetic vectors against the pinned, real custody component.

Run with the component checkout on PYTHONPATH and private canonical TMPDIR.
These vectors cover the public custody seam, not integrated privacy acceptance.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from integrations.mse_privacy.custody import AccessDenied, Grant, open_custody


class CustodyVectors(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 21, 3, tzinfo=timezone.utc)
        expiry = self.now + timedelta(minutes=30)
        self.expiry = expiry
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name).resolve()
        roots = {f"{name}_root": root / name for name in ("authority", "fence", "projection", "evidence", "vault")}
        for path in roots.values():
            path.mkdir(mode=0o700)
        example_path = Path(__file__).with_name("analytical-view-examples.json")
        self.payload = json.loads(example_path.read_text())["valid"][0]
        scope = dict(subject_id="vector-subject", source_system="healthkit",
                     source_instance="vector-store", collection="healtharchive")
        writer = Grant("projection_writer", scope, self.payload["purpose"],
                       self.payload["policy_version"], 1, "vector-recipient", expiry)
        reader = replace(writer, role="analyst")
        self.serving_roots = {key: roots[key] for key in ("authority_root", "fence_root", "projection_root")}
        self.custody, self.credentials = open_custody(
            **roots, initialize=True, clock=lambda: self.now,
            grants=dict(writer=writer, reader=reader,
                        other_subject=replace(reader, scope=dict(scope, subject_id="other-subject")),
                        other_recipient=replace(reader, recipient="other-recipient"),
                        auditor=replace(writer, role="lineage_auditor"),
                        recovery=replace(writer, role="retention_recovery")),
        )
        self.view = self.custody.issue_view(self.credentials["writer"])
        self.payload["view_id"] = self.view

    def test_reservation_and_immutable_publish(self):
        with self.assertRaises(AccessDenied):
            self.custody.read_projection(self.credentials["reader"], self.view)
        for _ in range(2):
            self.custody.put_projection(self.credentials["writer"], self.view, self.payload)
        changed = dict(self.payload, rows=[])
        with self.assertRaises(AccessDenied):
            self.custody.put_projection(self.credentials["writer"], self.view, changed)
        self.assertEqual(
            self.custody.read_projection(self.credentials["reader"], self.view), self.payload
        )

    def test_scope_role_recipient_and_handle_are_not_authority(self):
        self.custody.put_projection(self.credentials["writer"], self.view, self.payload)
        for name in ("other_subject", "other_recipient", "writer", "auditor"):
            with self.subTest(name=name), self.assertRaises(AccessDenied):
                self.custody.read_projection(self.credentials[name], self.view)
        with self.assertRaises(AccessDenied):
            self.custody.read_projection(self.view, self.view)
        with self.assertRaises(AccessDenied):
            self.custody.authorize_lineage(self.credentials["reader"], self.view, operation="resolve")
        decision = self.custody.authorize_lineage(
            self.credentials["auditor"], self.view, operation="resolve"
        )
        self.assertEqual((decision["recipient"], decision["generation"]), ("vector-recipient", 1))

    def test_aggregate_only_reopen_and_durable_revocation(self):
        self.custody.put_projection(self.credentials["writer"], self.view, self.payload)
        service, credentials = open_custody(**self.serving_roots, clock=lambda: self.now)
        self.assertEqual(credentials, {})
        self.assertEqual(service.read_projection(self.credentials["reader"], self.view), self.payload)
        self.custody.revoke(self.credentials["recovery"])
        service, _ = open_custody(**self.serving_roots, clock=lambda: self.now)
        with self.assertRaises(AccessDenied):
            service.read_projection(self.credentials["reader"], self.view)

    def test_expiry_boundary_and_live_revocation(self):
        self.custody.put_projection(self.credentials["writer"], self.view, self.payload)
        now = self.now
        self.now = self.expiry
        with self.assertRaises(AccessDenied):
            self.custody.read_projection(self.credentials["reader"], self.view)
        self.now = now
        self.assertEqual(self.custody.revoke(self.credentials["recovery"]), 2)
        with self.assertRaises(AccessDenied):
            self.custody.read_projection(self.credentials["reader"], self.view)


if __name__ == "__main__":
    unittest.main()
