"""Acceptance probes for the pinned local privacy custody and resolver seam."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from test_privacy_vectors import CANARIES, disclosure_hits


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
        self.roots = {f"{name}_root": self.root / name for name in ("evidence", "vault", "projection")}
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
        }
        self.service, self.tokens = self.open(initialize=True)

    def open(self, *, initialize=False, grants=None):
        return self.bootstrap(**self.roots, grants=self.grants if grants is None else grants,
                              initialize=initialize, clock=lambda: self.now)

    def store_control(self):
        """Publish an allowlisted control to isolate storage from the preview API."""
        view = self.service.issue_view(self.tokens["writer"])
        payload = {**self.header, "view_id": view, "rows": [],
                   "projection_loss": ["coverage_unknown"]}
        self.service.put_projection(self.tokens["writer"], view, payload)
        return view, payload

    def test_forbidden_role_never_opens_raw_or_vault_or_lineage(self):
        view, _ = self.store_control()
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
        view, payload = self.store_control()
        reopened, credentials = self.open()
        with patch.object(reopened._evidence, "open", wraps=reopened._evidence.open) as raw:
            result = reopened.read_projection(credentials["reader"], view)
            self.assertEqual(result, payload)
            self.assertFalse(disclosure_hits(result))
            for key in ("other_subject", "other_recipient"):
                with self.assertRaises(self.denied):
                    reopened.read_projection(credentials[key], view)
            raw.assert_not_called()

    def test_revoke_and_reopen_with_updated_bootstrap_generation(self):
        view, _ = self.store_control()
        generation = self.service.revoke(self.tokens["revoke"])
        with self.assertRaises(self.denied):
            self.service.read_projection(self.tokens["reader"], view)
        current = {key: replace(grant, generation=generation) for key, grant in self.grants.items()}
        reopened, credentials = self.open(grants=current)
        with self.assertRaises(self.denied):
            reopened.read_projection(credentials["reader"], view)
        unconfigured, credentials = self.open(grants={})
        self.assertEqual(credentials, {})
        with self.assertRaises(self.denied):
            unconfigured.read_projection(self.tokens["reader"], view)
