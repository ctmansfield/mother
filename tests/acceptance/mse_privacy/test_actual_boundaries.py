"""Acceptance probes for the pinned local privacy custody and resolver seam."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_privacy_vectors import CANARIES, FIXTURE, disclosure_hits


class ActualBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from integrations.mse_privacy.custody import AccessDenied, Grant, StoreUnavailable, open_custody
            from integrations.mse_privacy.custody.projection import HEADER, POLICY, PURPOSE
            from integrations.mse_privacy.lineage import LineageDenied, LineageResolver
        except ModuleNotFoundError as error:
            if error.name not in {"integrations", "integrations.mse_privacy",
                                  "integrations.mse_privacy.custody", "integrations.mse_privacy.lineage"}:
                raise
            raise unittest.SkipTest("assemble the pinned custody and resolver sources")
        cls.denied, cls.unavailable, cls.lineage_denied = AccessDenied, StoreUnavailable, LineageDenied
        cls.Grant, cls.header, cls.purpose, cls.policy = Grant, HEADER, PURPOSE, POLICY
        cls.resolver_class, cls.bootstrap = LineageResolver, staticmethod(open_custody)

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.roots = {f"{name}_root": self.root / name for name in ("evidence", "vault", "projection", "authority", "fence")}
        for path in self.roots.values():
            path.mkdir(mode=0o700)
        self.now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        scope = dict(subject_id=CANARIES[0], source_instance=CANARIES[1],
                     source_system="healthkit", collection="healtharchive")
        writer = self.Grant("projection_writer", scope, self.purpose, self.policy, 1, "team-a",
                            self.now + timedelta(hours=1))
        reader = replace(writer, role="analyst")
        self.grants = {
            "writer": writer, "reader": reader,
            "other_subject": replace(reader, scope=dict(scope, subject_id="synthetic-other")),
            "other_recipient": replace(reader, recipient="synthetic-other"),
            "revoke": replace(writer, role="retention_recovery"),
            "audit": replace(writer, role="lineage_auditor"),
        }
        self.service, self.tokens = self.open(initialize=True)

    def open(self, *, initialize=False, roots=None):
        return self.bootstrap(**(self.roots if roots is None else roots),
                              **({"grants": self.grants} if initialize else {}),
                              initialize=initialize, clock=lambda: self.now)

    def prepare(self):
        from integrations.healthbridge.ingest import ingest_capture
        from integrations.mse_ingest import Scope
        from integrations.mse_ingest.connected import ConnectedIngest, NORMALIZER_VERSION
        from integrations.mse_privacy.export import AnalyticalExporter, ProjectionBinding

        scope = dict(self.grants["writer"].scope)
        schema = json.loads(Path("docs/mse/integration/contracts/offline-integration.schema.json").read_bytes())

        def ledger():
            return ConnectedIngest(self.root / "ledger", scope=Scope(**scope),
                                   archive_id="synthetic-archive", schema=schema)

        archive = json.loads(FIXTURE.read_bytes())
        sdnn = archive["readings"][1]
        for index in (21, 22):
            archive["readings"].append(dict(sdnn, id=f"c0de0000-0000-4000-8000-{index:012d}"))
        delivery = ingest_capture(ledger(), json.dumps(archive).encode(),
                                  batch_id="privacy-batch", capture_id="privacy-capture",
                                  capture_kind="full_file")
        snapshot = ledger().build_snapshot(
            measurement_start="2025-11-16T00:00:00Z",
            measurement_end="2025-11-17T00:00:00Z",
            knowledge_cutoff_sequence=delivery.receipt["commit_sequence"],
            normalizer_version=NORMALIZER_VERSION,
        )
        binding = ProjectionBinding(tuple(scope.items()), "synthetic-archive",
                                    snapshot["snapshot_sha256"], "team-a", 1)
        self.opens = []

        def open_ledger():
            self.opens.append("ledger")
            return ledger()

        def load():
            self.opens.append("snapshot")
            return snapshot

        return AnalyticalExporter(self.service, open_ledger, binding), open_ledger, load, snapshot

    def publish(self):
        exporter, ledger, load, snapshot = self.prepare()
        view = exporter.export(self.tokens["writer"], load)["view_id"]
        payload = self.service.read_projection(self.tokens["reader"], view)
        return view, payload, ledger, snapshot

    def test_forbidden_role_never_opens_raw_or_vault_or_lineage(self):
        view, *_ = self.publish()
        resolver = self.resolver_class(self.root / "lineage", custody=self.service,
                                       archive_id="synthetic-archive")
        with patch.object(self.service._evidence, "open", wraps=self.service._evidence.open) as raw, \
             patch.object(self.service._vault, "open", wraps=self.service._vault.open) as vault, \
             patch.object(resolver, "_connect", wraps=resolver._connect) as lineage:
            for action in (
                lambda: self.service.read_evidence(self.tokens["reader"], "synthetic-protected"),
                lambda: self.service.resolve_pseudonym(self.tokens["reader"], "synthetic-protected"),
                lambda: self.service.issue_view("projection_writer"),
                lambda: resolver.resolve(self.tokens["reader"], view),
            ):
                with self.assertRaises((self.denied, self.lineage_denied)) as rejection:
                    action()
                self.assertFalse(disclosure_hits(str(rejection.exception)))
            raw.assert_not_called()
            vault.assert_not_called()
            lineage.assert_not_called()

    def test_persisted_projection_denies_foreign_context_and_never_opens_raw(self):
        view, payload, ledger, snapshot = self.publish()
        reopened, _ = self.open()
        with patch.object(reopened._evidence, "open", wraps=reopened._evidence.open) as raw:
            result = reopened.read_projection(self.tokens["reader"], view)
            self.assertEqual(result, payload)
            self.assertFalse(disclosure_hits(result))
            for key in ("other_subject", "other_recipient"):
                with self.assertRaises(self.denied):
                    reopened.read_projection(self.tokens[key], view)
            raw.assert_not_called()

    def test_revoke_survives_reopen(self):
        view, *_ = self.publish()
        generation = self.service.revoke(self.tokens["revoke"])
        with self.assertRaises(self.denied):
            self.service.read_projection(self.tokens["reader"], view)
        reopened, _ = self.open()
        with self.assertRaises(self.denied):
            reopened.read_projection(self.tokens["reader"], view)

    def test_actual_publication_and_restricted_binding(self):
        view, payload, ledger, snapshot = self.publish()
        self.assertEqual(payload["rows"], [
            {"bucket_index": 15, "channel": "hrv_sdnn", "unit": "ms", "mean_value": "41.5"}
        ])
        self.assertFalse(disclosure_hits(payload))
        resolver = self.resolver_class(self.root / "lineage", custody=self.service,
                                       archive_id="synthetic-archive")
        resolver.bind(self.tokens["writer"], view, open_ledger=ledger,
                      snapshot_bytes=json.dumps(snapshot).encode(),
                      projection_bytes=json.dumps(payload).encode(),
                      max_snapshot_bytes=100_000, max_projection_bytes=10_000)
        self.assertEqual(resolver.resolve(self.tokens["audit"], view).archive_id, "synthetic-archive")
        with self.assertRaises(self.lineage_denied):
            resolver.resolve(self.tokens["reader"], view)
        aggregate_roots = {key: value for key, value in self.roots.items()
                           if key not in ("evidence_root", "vault_root")}
        aggregate, _ = self.open(roots=aggregate_roots)
        self.assertEqual(aggregate.read_projection(self.tokens["reader"], view), payload)

    def test_wrong_role_and_expiry_stop_before_snapshot_or_ledger(self):
        from integrations.mse_privacy.export import ExportDenied

        exporter, _, load, _ = self.prepare()
        with self.assertRaises(ExportDenied):
            exporter.export(self.tokens["reader"], load)
        self.now += timedelta(hours=2)
        with self.assertRaises(ExportDenied):
            exporter.export(self.tokens["writer"], load)
        self.assertEqual(self.opens, [])

    def test_stale_authority_and_missing_fence_fail_closed(self):
        import shutil

        self.publish()
        authority = self.roots["authority_root"] / "store.sqlite3"
        backup = self.root / "old-authority.sqlite3"
        shutil.copyfile(authority, backup)
        self.service.revoke(self.tokens["revoke"])
        shutil.copyfile(backup, authority)
        with self.assertRaises((self.denied, self.unavailable)):
            self.open()
        fence = self.roots["fence_root"] / "store.sqlite3"
        fence.rename(fence.with_suffix(".withheld"))
        with self.assertRaises((self.denied, self.unavailable)):
            self.open()

    def test_read_already_admitted_and_later_revoke_are_ordered(self):
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import contextmanager
        from threading import Event

        view, payload, *_ = self.publish()
        entered, proceed, revoking = Event(), Event(), Event()
        original_open = self.service._projection.open

        @contextmanager
        def delayed_open(*args, **kwargs):
            entered.set()
            if not proceed.wait(timeout=4):
                raise AssertionError("Timed out waiting to release the admitted read")
            with original_open(*args, **kwargs) as store:
                yield store

        def revoke():
            revoking.set()
            return self.service.revoke(self.tokens["revoke"])

        with patch.object(self.service._projection, "open", side_effect=delayed_open):
            with ThreadPoolExecutor(max_workers=2) as pool:
                read = pool.submit(self.service.read_projection, self.tokens["reader"], view)
                try:
                    self.assertTrue(entered.wait(timeout=4))
                    revocation = pool.submit(revoke)
                    self.assertTrue(revoking.wait(timeout=4))
                    self.assertFalse(revocation.done())
                finally:
                    proceed.set()
                self.assertEqual(read.result(timeout=5), payload)
                self.assertEqual(revocation.result(timeout=5), 2)
        with self.assertRaises(self.denied):
            self.service.read_projection(self.tokens["reader"], view)
