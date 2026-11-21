from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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
            for name in ("evidence", "vault", "projection", "authority", "fence")
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
            grants=(grants or self.grants) if initialize else None,
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
        self.assertEqual(grants, {})
        self.assertEqual(reopened.pseudonym(self.tokens["vault"]), one)

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
        self.assertEqual(
            self.service.read_projection(self.tokens["reader"], view_id), expected
        )
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
        reopened, credentials = self.boot()
        self.assertEqual(credentials, {})
        with self.assertRaises(AccessDenied):
            reopened.read_projection(self.tokens["reader"], view_id)

    def test_projection_restore_without_vault_or_originals_and_stale_authority(self):
        view_id, expected = self.publish()
        restored_roots = {}
        for name in ("projection", "authority"):
            restore = self.parent / (name + "-restore")
            restore.mkdir(mode=0o700)
            path = restore / "store.sqlite3"
            path.touch(mode=0o600)
            with sqlite3.connect(
                self.roots[name + "_root"] / "store.sqlite3"
            ) as source:
                with sqlite3.connect(path) as backup:
                    source.backup(backup)
            restored_roots[name + "_root"] = restore
        serving = dict(
            authority_root=self.roots["authority_root"],
            fence_root=self.roots["fence_root"],
            projection_root=restored_roots["projection_root"],
        )
        restored, _ = open_custody(**serving, clock=lambda: self.now)
        self.assertEqual(
            restored.read_projection(self.tokens["reader"], view_id), expected
        )
        self.service.revoke(self.tokens["revoke"])
        with self.assertRaises(AccessDenied):
            restored.read_projection(self.tokens["reader"], view_id)
        serving["authority_root"] = restored_roots["authority_root"]
        with self.assertRaises(StoreUnavailable):
            open_custody(**serving, clock=lambda: self.now)
        (self.roots["fence_root"] / "store.sqlite3").unlink()
        with self.assertRaises(StoreUnavailable):
            self.boot()

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
        swapped, _ = open_custody(
            **dict(
                self.roots, projection_root=self.roots["vault_root"], vault_root=None
            ),
            clock=lambda: self.now,
        )
        view_id = self.service.issue_view(self.tokens["writer"])
        with self.assertRaises(StoreUnavailable):
            swapped.read_projection(self.tokens["reader"], view_id)

    def test_expired_view_is_denied_under_a_longer_reader_grant(self):
        view_id, expected = self.publish()
        self.now = NOW + timedelta(hours=1)
        with self.assertRaises(AccessDenied):
            self.service.read_projection(self.tokens["reader"], view_id)

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

    def test_denied_public_operations_open_no_private_content_store(self):
        view, _ = self.publish()
        with (
            patch.object(self.service._evidence, "open") as evidence,
            patch.object(self.service._vault, "open") as vault,
            patch.object(self.service._projection, "open") as projection,
        ):
            for operation in (
                lambda: self.service.read_evidence(self.tokens["reader"], view),
                lambda: self.service.read_projection(
                    self.tokens["other_subject"], view
                ),
                lambda: self.service.authorize_projection(self.tokens["reader"]),
                lambda: self.service.authorize_lineage(
                    self.tokens["reader"], view, operation="resolve"
                ),
            ):
                with self.assertRaises(AccessDenied):
                    operation()
            for opened in (evidence, vault, projection):
                opened.assert_not_called()

    def test_read_admitted_before_revoke_finishes_then_stale_reads_deny(self):
        view, expected = self.publish()
        other, _ = self.boot()
        inside, release, revoking, revoked = Event(), Event(), Event(), Event()
        original = self.service._projection.open

        @contextmanager
        def slow_projection():
            inside.set()
            if not release.wait(1):
                raise AssertionError("test did not release the read")
            with original() as db:
                yield db

        def revoke():
            revoking.set()
            version = other.revoke(self.tokens["revoke"])
            revoked.set()
            return version

        with patch.object(self.service._projection, "open", slow_projection):
            with ThreadPoolExecutor(max_workers=2) as pool:
                read = pool.submit(
                    self.service.read_projection, self.tokens["reader"], view
                )
                try:
                    self.assertTrue(inside.wait(1))
                    change = pool.submit(revoke)
                    self.assertTrue(revoking.wait(1))
                    self.assertFalse(revoked.wait(0.05))
                finally:
                    release.set()
                self.assertEqual(read.result(timeout=2), expected)
                self.assertEqual(change.result(timeout=2), 2)
        with self.assertRaises(AccessDenied):
            other.read_projection(self.tokens["reader"], view)

    def test_lineage_digest_requires_actual_publication_and_current_grant(self):
        view = self.service.issue_view(self.tokens["writer"])
        digest = self.service.published_projection_digest
        with self.assertRaises(AccessDenied):
            digest(self.tokens["writer"], view)
        payload = view_payload(view)
        self.service.put_projection(self.tokens["writer"], view, payload)
        expected = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(digest(self.tokens["writer"], view), expected)
        self.assertEqual(digest(self.tokens["audit"], view), expected)
        with self.assertRaises(AccessDenied):
            digest(self.tokens["reader"], view)
        self.service.revoke(self.tokens["revoke"])
        with self.assertRaises(AccessDenied):
            digest(self.tokens["audit"], view)

    def test_bootstrap_refuses_grants_for_existing_stores(self):
        view, expected = self.publish()
        unapproved = dict(self.grants, claimed_role=self.grants["writer"])
        for initialize in (False, True):
            with (
                self.subTest(initialize=initialize),
                self.assertRaises((ValueError, StoreUnavailable)),
            ):
                open_custody(**self.roots, grants=unapproved, initialize=initialize)
        self.assertEqual(
            self.service.read_projection(self.tokens["reader"], view), expected
        )
        with self.assertRaises(AccessDenied):
            self.service.issue_view("projection_writer")
        with self.assertRaises(AccessDenied):
            self.service.revoke(self.tokens["reader"])

    def test_invalid_fence_denies_existing_and_reopened_read_before_projection(self):
        view, expected = self.publish()
        fence = self.roots["fence_root"] / "store.sqlite3"
        current = fence.read_bytes()
        self.assertEqual(
            self.service.read_projection(self.tokens["reader"], view), expected
        )
        for case in ("missing_epoch", "wrong_pair", "unreadable_database"):
            with self.subTest(case=case):
                fence.write_bytes(current)
                if case == "unreadable_database":
                    fence.write_bytes(b"synthetic damaged database")
                else:
                    with sqlite3.connect(fence) as db:
                        if case == "missing_epoch":
                            db.execute("DELETE FROM epoch")
                        else:
                            db.execute("UPDATE epoch SET pair=?", ("other-synthetic",))
                with patch.object(self.service._projection, "open") as projection:
                    with self.assertRaises(StoreUnavailable):
                        self.service.read_projection(self.tokens["reader"], view)
                    projection.assert_not_called()
                with self.assertRaises(StoreUnavailable):
                    self.boot()

    def test_roots_must_be_distinct_and_private(self):
        nested = self.roots["evidence_root"] / "nested"
        nested.mkdir(mode=0o700)
        for other in (self.roots["evidence_root"], nested):
            roots = dict(self.roots, projection_root=other)
            with self.assertRaisesRegex(ValueError, "disjoint"):
                open_custody(**roots)
        self.roots["vault_root"].chmod(0o755)
        with self.assertRaises(StoreUnavailable):
            self.boot()
