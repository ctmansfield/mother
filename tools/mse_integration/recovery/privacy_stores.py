"""Rehearse selected pinned privacy-store recovery boundaries with synthetic data."""

import argparse
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
import uuid

BASE = "b7aae4f2216d27f0544eab9fe9698286fe49d716"
CUSTODY = "26895ab4cf090c75f5540dbab1f16d1f7d91db02"
EXPORT = "ef8dded78ffdce643db394fa3f6ef91e3fa36854"
LINEAGE = "05b571ad8610d21d99bd2dacc070d063c3ff1f1c"
CONNECTED_PINS = (
    "7623616a97c0ab0213b6a9b4ebcf9affdac1e80a",
    "58f78b1ed077fc0938b3540a517429500a40c663",
    "c509515b6ae4508d6f94e619ed557cc6789ebda7",
)
REFERENCE = "research/mse/reference-v0.1.0/prototype"
CONTRACT = "docs/mse/integration/contracts/offline-integration.schema.json"


def git(checkout, *args):
    return subprocess.check_output(["git", "-C", str(checkout), *args])


def verify_aligned_candidate(checkout, commit, tree):
    """Bind a reviewer-supplied immutable candidate to the approved component bytes."""
    if (
        git(checkout, "rev-parse", "HEAD").decode().strip() != commit
        or git(checkout, "rev-parse", "HEAD^{tree}").decode().strip() != tree
        or git(checkout, "status", "--porcelain", "--untracked-files=all").strip()
    ):
        raise ValueError("Candidate is not the exact clean commit and tree")
    for base, *paths in (
        (
            BASE,
            "integrations/healthbridge",
            "integrations/mse_ingest",
            "integrations/mse_snapshot",
            "mother/physiology",
            "mother/__init__.py",
            REFERENCE,
            CONTRACT,
        ),
        ("1d608b50f3dfa95fe344bf190eda6b9c8f3ab69d", "docs/mse/privacy"),
        (CONNECTED_PINS[0], "integrations/mse_privacy/custody"),
        (CONNECTED_PINS[1], "integrations/mse_privacy/export"),
        (CONNECTED_PINS[2], "integrations/mse_privacy/lineage"),
    ):
        if git(checkout, "diff", "--name-only", base, commit, "--", *paths).strip():
            raise ValueError("Candidate component bytes differ from approved pins")


def load_sources(checkout, root, *, connected):
    custody, export, lineage = (
        CONNECTED_PINS if connected else (CUSTODY, EXPORT, LINEAGE)
    )
    for pin, *paths in (
        (
            BASE,
            "integrations/healthbridge",
            "integrations/mse_ingest",
            "integrations/mse_snapshot",
            "mother",
            REFERENCE,
            CONTRACT,
        ),
        (custody, "integrations/mse_privacy/custody"),
        (export, "integrations/mse_privacy/export"),
        (lineage, "integrations/mse_privacy/lineage"),
    ):
        with tarfile.open(
            fileobj=BytesIO(git(checkout, "archive", pin, *paths))
        ) as bundle:
            bundle.extractall(root, filter="data")
    sys.path[:0] = [str(root), str(root / REFERENCE)]


def sqlite_copy(source, destination):
    """Copy a quiesced, fixture-owned member to an exclusive local pathname."""
    if source.is_symlink() or not source.is_file():
        raise ValueError("Expected a regular synthetic database")
    destination.touch(mode=0o600, exist_ok=False)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as reader:
        with closing(sqlite3.connect(destination)) as target:
            reader.backup(target)
            if target.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
                raise ValueError("Expected a standalone backup member")
            if target.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise ValueError("Invalid backup member")


def rehearse(checkout, source_root, *, connected, candidate=None, coupled=False):
    if candidate:
        verify_aligned_candidate(checkout, *candidate)
        source_root = checkout
        sys.path[:0] = [str(checkout), str(checkout / REFERENCE)]
    else:
        load_sources(checkout, source_root, connected=connected)
    from integrations.healthbridge.ingest import ingest_capture
    from integrations.mse_ingest import Scope
    from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
    from integrations.mse_privacy.custody import (
        AccessDenied,
        Grant,
        StoreUnavailable,
        open_custody,
    )
    from integrations.mse_privacy.custody.projection import POLICY, PURPOSE
    from integrations.mse_privacy.export import AnalyticalExporter

    if connected:
        from integrations.mse_privacy.export import ProjectionBinding
    else:
        from integrations.mse_privacy.export import ProjectionGrant
    from integrations.mse_privacy.lineage import LineageDenied, LineageResolver
    from mse.contracts import canonical

    class PublishedComponentRecovery(unittest.TestCase):
        def setUp(self):
            temporary = TemporaryDirectory(prefix="mse-privacy-real-stores-")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name).resolve()
            self.roots = {
                name + "_root": self.directory(name)
                for name in ("evidence", "vault", "projection")
            }
            if connected:
                self.roots.update(
                    authority_root=self.directory("authority"),
                    fence_root=self.directory("fence"),
                )
            self.registry = self.directory("registry")
            self.backup_root = self.directory("backup")
            self.now = datetime(2026, 11, 21, 3, tzinfo=timezone.utc)
            self.scope = Scope(
                "privacy-subject-marker",
                "healthkit",
                "privacy-source-marker",
                "healtharchive",
            )
            self.archive_id = "privacy-archive-marker"
            grant = Grant(
                "projection_writer",
                self.scope.fields(),
                PURPOSE,
                POLICY,
                1,
                "privacy-recipient-marker",
                self.now + timedelta(hours=1),
            )
            self.grants = {
                "writer": grant,
                "reader": replace(grant, role="analyst"),
                "audit": replace(grant, role="lineage_auditor"),
                "revoke": replace(grant, role="retention_recovery"),
                "evidence": replace(
                    grant, role="evidence_writer", purpose="evidence_ingest"
                ),
            }
            self.service, self.creds = self.boot(initialize=True)
            rows = [
                dict(
                    id=str(uuid.uuid4()),
                    kind="HRV (SDNN)",
                    value=value,
                    unit="ms",
                    start=index + 1,
                    end=index + 2,
                    receivedAt=9,
                    source="private-capture-marker",
                    bundleID="example.synthetic",
                )
                for index, value in enumerate((41.5, 42.5, 43.5))
            ]
            self.original = json.dumps(
                dict(readings=rows, anchors={}, tombstones={}, backfillStart=0)
            ).encode()
            self.service.put_evidence(self.creds["evidence"], self.original)
            self.ledger_root = self.directory("ledger")
            self.ledger = ConnectedIngest(
                self.ledger_root,
                archive_id=self.archive_id,
                scope=self.scope,
                schema=json.loads((source_root / CONTRACT).read_text()),
            )
            batch = "restore-" + uuid.uuid4().hex
            delivery = ingest_capture(
                self.ledger,
                self.original,
                batch_id=batch,
                capture_id=batch,
                capture_kind="full_file",
            )
            snapshot = self.ledger.build_snapshot(
                measurement_start="2001-01-01T00:00:00.000000Z",
                measurement_end="2001-01-02T00:00:00.000000Z",
                knowledge_cutoff_sequence=delivery.receipt["commit_sequence"],
                normalizer_version=NORMALIZER_VERSION,
            )
            if connected:
                binding = ProjectionBinding(
                    tuple(self.scope.fields().items()),
                    self.archive_id,
                    snapshot["snapshot_sha256"],
                    self.grants["writer"].recipient,
                    1,
                )
                exported = AnalyticalExporter(
                    self.service,
                    lambda: self.ledger,
                    binding,
                ).export(self.creds["writer"], lambda: snapshot)
                self.view = exported["view_id"]
                self.payload = self.service.read_projection(
                    self.creds["reader"], self.view
                )
            else:
                self.view = self.service.issue_view(self.creds["writer"])
                # Historical components expose a preview grant and a distinct storage
                # reservation. Persist the real aggregate under the reserved view.
                preview = ProjectionGrant(
                    tuple(self.scope.fields().items()),
                    self.archive_id,
                    snapshot["snapshot_sha256"],
                )
                analytical = AnalyticalExporter(self.ledger, preview).export(snapshot)
                self.payload = dict(analytical, view_id=self.view)
                self.service.put_projection(
                    self.creds["writer"], self.view, self.payload
                )
            self.assertEqual(
                self.payload["rows"],
                [
                    dict(
                        bucket_index=0, channel="hrv_sdnn", unit="ms", mean_value="42.5"
                    )
                ],
            )
            ledger_input = (
                {"open_ledger": lambda: self.ledger}
                if connected
                else {"ledger": self.ledger}
            )
            self.resolver(self.service).bind(
                self.creds["writer"],
                self.view,
                **ledger_input,
                snapshot_bytes=canonical(snapshot).encode(),
                projection_bytes=canonical(self.payload).encode(),
                max_snapshot_bytes=64_000,
                max_projection_bytes=16_000,
            )
            for name, store in self.stores().items():
                if name != "fence_root":
                    sqlite_copy(store, self.backup_root / name)

        def directory(self, name):
            path = self.root / name
            path.mkdir(mode=0o700)
            return path

        def stores(self):
            return {
                name: root / "store.sqlite3" for name, root in self.roots.items()
            } | {"registry": self.registry / "lineage.sqlite3"}

        def boot(self, *, initialize=False, grants=None, aggregate_only=False):
            roots = dict(self.roots)
            if aggregate_only:
                del roots["evidence_root"]
                del roots["vault_root"]
            if connected:
                if initialize:
                    grants = self.grants
            elif grants is None:
                grants = self.grants
            return open_custody(
                **roots, initialize=initialize, grants=grants, clock=lambda: self.now
            )

        def resolver(self, service):
            return LineageResolver(
                self.registry, custody=service, archive_id=self.archive_id
            )

        def recover(self, *names):
            for name in names:
                destination = self.stores()[name]
                destination.unlink()
                sqlite_copy(self.backup_root / name, destination)

        def test_real_projection_restore_does_not_expose_raw_or_privileged_lineage(
            self,
        ):
            self.recover("projection_root")
            service, creds = self.boot()
            aggregate = service.read_projection(creds["reader"], self.view)
            self.assertEqual(aggregate, self.payload)
            text = canonical(aggregate)
            for marker in (
                self.scope.subject_id,
                self.scope.source_instance,
                "private-capture-marker",
                "2001-01-01",
                self.archive_id,
            ):
                self.assertNotIn(marker, text)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(creds["reader"], self.view)
            self.assertEqual(
                self.resolver(service).resolve(creds["audit"], self.view).archive_id,
                self.archive_id,
            )

        def test_current_generation_supplied_after_restore_denies_older_view(self):
            generation = self.service.revoke(self.creds["revoke"])
            self.recover("vault_root", "projection_root", "registry")
            current = {
                name: replace(grant, generation=generation)
                for name, grant in self.grants.items()
            }
            service, creds = self.boot(grants=current)
            with self.assertRaises(AccessDenied):
                service.read_projection(creds["reader"], self.view)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(creds["audit"], self.view)

        def test_baseline_reopens_old_grants_if_bootstrap_supplies_stale_state(self):
            self.service.revoke(self.creds["revoke"])
            self.recover("vault_root", "projection_root", "registry")
            service, creds = self.boot()
            # This is the historical defect, not an acceptable recovery path.
            self.assertEqual(
                service.read_projection(creds["reader"], self.view), self.payload
            )

        def test_absent_trusted_grants_deny_reopened_projection(self):
            self.recover("vault_root", "projection_root", "registry")
            service, creds = self.boot(grants={})
            self.assertEqual(creds, {})
            with self.assertRaises(AccessDenied):
                service.read_projection(self.creds["reader"], self.view)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(self.creds["audit"], self.view)

        def test_baseline_aggregate_with_identity_vault_missing_is_unavailable(self):
            self.recover("projection_root")
            service, creds = self.boot()
            self.stores()["evidence_root"].unlink()
            self.assertEqual(
                service.read_projection(creds["reader"], self.view),
                self.payload,
            )
            self.stores()["vault_root"].unlink()
            with self.assertRaises(StoreUnavailable):
                service.read_projection(creds["reader"], self.view)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(creds["audit"], self.view)
            with self.assertRaises(StoreUnavailable):
                self.boot()

        def test_connected_aggregate_only_restore_without_raw_or_identity(self):
            self.recover("projection_root")
            self.stores()["evidence_root"].unlink()
            self.stores()["vault_root"].unlink()
            self.ledger_root.rename(self.root / "ledger-unavailable")
            service, new_creds = self.boot(aggregate_only=True)
            self.assertEqual(new_creds, {})
            aggregate = service.read_projection(self.creds["reader"], self.view)
            self.assertEqual(aggregate, self.payload)
            encoded = canonical(aggregate)
            for marker in (
                self.scope.subject_id,
                self.scope.source_instance,
                "private-capture-marker",
                "2001-01-01",
                self.archive_id,
            ):
                self.assertNotIn(marker, encoded)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(self.creds["reader"], self.view)
            self.stores()["registry"].unlink()
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(self.creds["audit"], self.view)

        def test_connected_revocation_survives_stale_data_restore(self):
            self.assertEqual(self.service.revoke(self.creds["revoke"]), 2)
            fence = self.stores()["fence_root"].read_bytes()
            self.assertFalse((self.backup_root / "fence_root").exists())
            self.recover("vault_root", "projection_root", "registry")
            service, reopened_credentials = self.boot()
            self.assertEqual(reopened_credentials, {})
            with self.assertRaises(AccessDenied):
                service.read_projection(self.creds["reader"], self.view)
            with self.assertRaises(LineageDenied):
                self.resolver(service).resolve(self.creds["audit"], self.view)
            self.assertEqual(self.stores()["fence_root"].read_bytes(), fence)

        def test_connected_stale_authority_backup_cannot_override_live_fence(self):
            self.assertEqual(self.service.revoke(self.creds["revoke"]), 2)
            fence = self.stores()["fence_root"].read_bytes()
            self.assertFalse((self.backup_root / "fence_root").exists())
            self.recover("authority_root", "vault_root", "projection_root", "registry")
            with self.assertRaises((AccessDenied, StoreUnavailable)):
                self.boot(aggregate_only=True)
            self.assertEqual(self.stores()["fence_root"].read_bytes(), fence)

        def test_connected_missing_authority_or_fence_denies_reopen(self):
            member = self.stores()["authority_root"]
            member.rename(member.with_suffix(".unavailable"))
            with self.assertRaises((AccessDenied, StoreUnavailable)):
                self.boot(aggregate_only=True)
            member.with_suffix(".unavailable").rename(member)
            self.stores()["fence_root"].unlink()
            with self.assertRaises((AccessDenied, StoreUnavailable)):
                self.boot(aggregate_only=True)

        def test_limit_coupled_rollback_reopens_old_grant(self):
            fence_backup = self.backup_root / "fence-limitation-only"
            sqlite_copy(self.stores()["fence_root"], fence_backup)
            self.assertEqual(self.service.revoke(self.creds["revoke"]), 2)
            self.recover("authority_root", "projection_root", "registry")
            with self.assertRaises((AccessDenied, StoreUnavailable)):
                self.boot(aggregate_only=True)
            # Deliberately violate the documented trust boundary in this fixture.
            fence = self.stores()["fence_root"]
            fence.unlink()
            sqlite_copy(fence_backup, fence)
            reopened, reissued = self.boot(aggregate_only=True)
            self.assertEqual(reissued, {})
            self.assertEqual(
                reopened.read_projection(self.creds["reader"], self.view), self.payload
            )

    tests = unittest.defaultTestLoader.getTestCaseNames(PublishedComponentRecovery)
    if coupled:
        tests = [name for name in tests if name.startswith("test_limit_")]
    elif connected:
        tests = [name for name in tests if name.startswith("test_connected_")]
    else:
        tests = [
            name
            for name in tests
            if not name.startswith(("test_connected_", "test_limit_"))
        ]
    suite = unittest.TestSuite(PublishedComponentRecovery(name) for name in tests)
    return int(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--object-store", required=True, type=Path)
    parser.add_argument("--connected", action="store_true")
    parser.add_argument("--candidate-commit")
    parser.add_argument("--candidate-tree")
    parser.add_argument("--coupled-rollback-limit", action="store_true")
    args = parser.parse_args()
    if bool(args.candidate_commit) != bool(args.candidate_tree):
        parser.error("Supply both exact candidate commit and tree")
    if (args.candidate_commit or args.coupled_rollback_limit) and not args.connected:
        parser.error("Candidate and coupled rollback modes require --connected")
    with TemporaryDirectory(prefix="mse-privacy-pinned-source-") as source:
        sys.exit(
            rehearse(
                args.object_store.resolve(),
                Path(source),
                connected=args.connected,
                candidate=(
                    (args.candidate_commit, args.candidate_tree)
                    if args.candidate_commit
                    else None
                ),
                coupled=args.coupled_rollback_limit,
            )
        )
