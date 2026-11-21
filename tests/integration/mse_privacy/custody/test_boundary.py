from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from integrations.mse_privacy.custody import (
    AccessDenied,
    Grant,
    StoreUnavailable,
    open_custody,
)
from integrations.mse_privacy.custody.projection import HEADER, POLICY, PURPOSE

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
SCOPE = {
    "subject_id": "synthetic-protected-subject",
    "source_system": "healthkit",
    "source_instance": "synthetic-protected-store",
    "collection": "healtharchive",
}
ORIGINAL = b'{"source":"synthetic-original-marker","unit":"bpm","value":64.25}\n'


def view_payload(view_id):
    return {
        **HEADER,
        "view_id": view_id,
        "rows": [
            {
                "bucket_index": 0,
                "channel": "heart_rate",
                "unit": "bpm",
                "mean_value": "64.2",
            },
            {
                "bucket_index": 0,
                "channel": "hrv_sdnn",
                "unit": "ms",
                "mean_value": "42.1",
            },
        ],
        "projection_loss": ["relative_time_binning", "value_aggregation_and_rounding"],
    }


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.parent = Path(temp.name).resolve()
        self.roots = {
            f"{name}_root": self.parent / name
            for name in ("evidence", "vault", "projection")
        }
        for root in self.roots.values():
            root.mkdir(mode=0o700)
        self.now = NOW
        expires = NOW + timedelta(hours=1)
        approved = Grant(
            "projection_writer", SCOPE, PURPOSE, POLICY, 1, "team-a", expires
        )
        self.grants = {
            "writer": approved,
            "reader": replace(approved, role="analyst"),
            "other_subject": replace(
                approved,
                role="analyst",
                scope=dict(SCOPE, subject_id="other-synthetic"),
            ),
            "other_recipient": replace(approved, role="analyst", recipient="team-b"),
            "audit": replace(approved, role="lineage_auditor"),
            "revoke": replace(approved, role="retention_recovery"),
            "exact": replace(approved, role="restricted_mse", purpose="exact_mse"),
            "evidence": replace(
                approved, role="evidence_writer", purpose="evidence_ingest"
            ),
            "vault": replace(
                approved, role="linkage_custodian", purpose="audit-purpose-a"
            ),
            "vault_other": replace(
                approved, role="linkage_custodian", purpose="audit-purpose-b"
            ),
        }
        self.service, self.tokens = self.boot(initialize=True)

    def boot(self, *, initialize=False, grants=None):
        return open_custody(
            **self.roots,
            grants=grants or self.grants,
            initialize=initialize,
            clock=lambda: self.now,
        )

    def publish(self):
        view_id = self.service.issue_view(self.tokens["writer"])
        result = view_payload(view_id)
        self.service.put_projection(self.tokens["writer"], view_id, result)
        return view_id, result

    def test_roles_and_subject_recipient_isolation(self):
        handle = self.service.put_evidence(self.tokens["evidence"], ORIGINAL)
        view_id, expected = self.publish()
        self.assertEqual(
            self.service.read_evidence(self.tokens["evidence"], handle), ORIGINAL
        )
        self.assertEqual(
            self.service.read_projection(self.tokens["reader"], view_id), expected
        )
        for role in ("reader", "exact", "writer", "audit", "vault"):
            with (
                self.subTest(role=role),
                self.assertRaisesRegex(AccessDenied, "^Access denied$"),
            ):
                self.service.read_evidence(self.tokens[role], handle)
        for role in (
            "other_subject",
            "other_recipient",
            "evidence",
            "writer",
            "audit",
            "vault",
        ):
            with (
                self.subTest(role=role),
                self.assertRaisesRegex(AccessDenied, "^Access denied$"),
            ):
                self.service.read_projection(self.tokens[role], view_id)
        for operation in (
            lambda: self.service.issue_view(self.tokens["reader"]),
            lambda: self.service.pseudonym(self.tokens["reader"]),
            lambda: self.service.put_projection(
                self.tokens["reader"], view_id, expected
            ),
            lambda: self.service.read_projection(view_id, view_id),
        ):
            with self.assertRaisesRegex(AccessDenied, "^Access denied$"):
                operation()

    def test_purpose_scoped_random_pseudonyms_reopen_and_do_not_join(self):
        one = self.service.pseudonym(self.tokens["vault"])
        two = self.service.pseudonym(self.tokens["vault_other"])
        self.assertRegex(one, r"^[A-Za-z0-9_-]{43}$")
        self.assertNotEqual(one, two)
        self.assertEqual(
            self.service.resolve_pseudonym(self.tokens["vault"], one), SCOPE
        )
        with self.assertRaises(AccessDenied):
            self.service.resolve_pseudonym(self.tokens["vault_other"], one)
        reopened, grants = self.boot()
        self.assertEqual(reopened.pseudonym(grants["vault"]), one)
        with self.assertRaises(AccessDenied):
            reopened.pseudonym(self.tokens["vault"])

    def test_projection_storage_has_no_private_linkage_and_no_fallback(self):
        raw = self.service.put_evidence(self.tokens["evidence"], ORIGINAL)
        pseudonym = self.service.pseudonym(self.tokens["vault"])
        view_id, expected = self.publish()
        projection = self.roots["projection_root"] / "store.sqlite3"
        with sqlite3.connect(projection) as db:
            self.assertEqual(
                db.execute(
                    "SELECT name FROM sqlite_schema WHERE type='table'"
                ).fetchall(),
                [("projections",)],
            )
            dump = "\n".join(db.iterdump())
        for removed in (
            SCOPE["subject_id"],
            SCOPE["source_instance"],
            raw,
            pseudonym,
            ORIGINAL.decode().strip(),
            "team-a",
            "expires_at",
        ):
            self.assertNotIn(removed, dump)
        (self.roots["vault_root"] / "store.sqlite3").unlink()
        with self.assertRaises(StoreUnavailable):
            self.service.read_projection(self.tokens["reader"], view_id)
        self.assertEqual(
            self.service.read_evidence(self.tokens["evidence"], raw), ORIGINAL
        )
        self.assertTrue(projection.exists())

    def test_lineage_roles_bind_only_exact_reserved_view(self):
        view_id = self.service.issue_view(self.tokens["writer"])
        allowed = self.service.authorize_lineage(
            self.tokens["writer"], view_id, operation="bind"
        )
        self.assertEqual(allowed["scope"], SCOPE)
        self.assertEqual(allowed["recipient"], "team-a")
        self.assertEqual(allowed["generation"], 1)
        self.assertEqual(
            self.service.authorize_lineage(
                self.tokens["audit"], view_id, operation="resolve"
            ),
            allowed,
        )
        for role, operation in (
            ("reader", "resolve"),
            ("writer", "resolve"),
            ("audit", "bind"),
        ):
            with self.assertRaises(AccessDenied):
                self.service.authorize_lineage(
                    self.tokens[role], view_id, operation=operation
                )

    def test_revocation_and_new_bootstrap_refuse_old_view_and_token(self):
        view_id, old = self.publish()
        self.service.revoke(self.tokens["revoke"])
        with self.assertRaises(AccessDenied):
            self.service.read_projection(self.tokens["reader"], view_id)
        with self.assertRaises(AccessDenied):
            self.service.authorize_lineage(
                self.tokens["audit"], view_id, operation="resolve"
            )
        updated = {
            name: replace(grant, generation=2) for name, grant in self.grants.items()
        }
        reopened, tokens = self.boot(grants=updated)
        with self.assertRaises(AccessDenied):
            reopened.read_projection(tokens["reader"], view_id)
        with self.assertRaises(AccessDenied):
            reopened.read_projection(self.tokens["reader"], view_id)
        next_id = reopened.issue_view(tokens["writer"])
        self.assertNotEqual(next_id, view_id)
        reopened.put_projection(tokens["writer"], next_id, view_payload(next_id))
        self.assertEqual(
            reopened.read_projection(tokens["reader"], next_id)["view_id"], next_id
        )

    def test_projection_only_restore_needs_current_vault_and_generation(self):
        view_id, _ = self.publish()
        restore = self.parent / "projection-restore"
        restore.mkdir(mode=0o700)
        path = restore / "store.sqlite3"
        path.touch(mode=0o600)
        with sqlite3.connect(self.roots["projection_root"] / "store.sqlite3") as source:
            with sqlite3.connect(path) as backup:
                source.backup(backup)
        updated = {
            name: replace(grant, generation=2) for name, grant in self.grants.items()
        }
        roots = dict(self.roots, projection_root=restore)
        restored, grants = open_custody(**roots, grants=updated, clock=lambda: self.now)
        with self.assertRaises(AccessDenied):
            restored.read_projection(grants["reader"], view_id)
        empty = self.parent / "empty-vault"
        empty.mkdir(mode=0o700)
        roots["vault_root"] = empty
        with self.assertRaises(StoreUnavailable):
            open_custody(**roots, grants=updated, clock=lambda: self.now)
        self.assertFalse((empty / "store.sqlite3").exists())

    def test_fifo_and_aliased_store_refuse_without_opening(self):
        fifo = self.roots["vault_root"] / "store.sqlite3-wal"
        os.mkfifo(fifo, 0o600)
        script = """
from pathlib import Path
import sys
from integrations.mse_privacy.custody.storage import PrivateDatabase, StoreUnavailable
try:
    with PrivateDatabase(Path(sys.argv[1]), 0x4D534502).open():
        raise AssertionError("unsafe store was opened")
except StoreUnavailable:
    pass
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(self.roots["vault_root"])],
            timeout=5,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        fifo.unlink()
        with self.assertRaises(StoreUnavailable):
            open_custody(
                **dict(
                    self.roots,
                    vault_root=self.roots["projection_root"],
                    projection_root=self.roots["vault_root"],
                ),
                grants=self.grants,
            )

    def test_expired_view_is_denied_under_a_longer_reader_grant(self):
        view_id, expected = self.publish()
        longer = dict(
            self.grants,
            reader=replace(self.grants["reader"], expires_at=NOW + timedelta(days=1)),
        )
        reopened, tokens = self.boot(grants=longer)
        self.now = NOW + timedelta(hours=1)
        with self.assertRaises(AccessDenied):
            reopened.read_projection(tokens["reader"], view_id)

    def test_payload_allowlist_and_immutable_write(self):
        view_id, approved = self.publish()
        self.service.put_projection(self.tokens["writer"], view_id, approved)
        unsafe = [
            dict(approved, raw="secret-from-request"),
            deepcopy(approved),
            deepcopy(approved),
        ]
        unsafe[1]["rows"][0]["source_id"] = "secret-from-request"
        unsafe[2]["rows"][0]["bucket_index"] = True
        for item in unsafe:
            with self.assertRaisesRegex(ValueError, "^Invalid analytical projection$"):
                self.service.put_projection(self.tokens["writer"], view_id, item)
        changed = deepcopy(approved)
        changed["rows"][0]["mean_value"] = "65.0"
        with self.assertRaises(AccessDenied):
            self.service.put_projection(self.tokens["writer"], view_id, changed)
        self.assertEqual(
            self.service.read_projection(self.tokens["reader"], view_id), approved
        )

    def test_roots_must_be_distinct_and_private(self):
        nested = self.roots["evidence_root"] / "nested"
        nested.mkdir(mode=0o700)
        for other in (self.roots["evidence_root"], nested):
            roots = dict(self.roots, projection_root=other)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                open_custody(**roots, grants=self.grants)
        self.roots["vault_root"].chmod(0o755)
        with self.assertRaises(StoreUnavailable):
            self.boot()
