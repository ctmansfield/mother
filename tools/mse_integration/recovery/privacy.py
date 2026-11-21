"""Rehearse synthetic privacy recovery without cryptographic or OS role claims."""

from dataclasses import dataclass, replace
from hashlib import sha256
import json
import math
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import unittest
import uuid

ROLES = {
    "vault": "vault-custodian",
    "evidence": "evidence-custodian",
    "projection": "projection-custodian",
}
PURPOSE = "synthetic-summary"
MAX_BYTES = 65_536


class RecoveryDenied(ValueError):
    """An input or authorization was unavailable. No privileged fallback."""


@dataclass(frozen=True)
class RecoveryRef:
    domain: str
    key_ref: str
    digest: str


@dataclass(frozen=True)
class Control:
    # A real system must obtain this live policy independently of every backup.
    generation: int
    available_refs: frozenset
    revoked: frozenset


def encode(data):
    return json.dumps(data, sort_keys=True, allow_nan=False).encode()


def seal(root, domain, payload):
    folder = root / domain
    folder.mkdir(mode=0o700, parents=True)
    path = folder / "generation.json"
    data = encode(payload)
    with path.open("xb") as file:
        file.write(data)
    path.chmod(0o600)
    return RecoveryRef(
        domain, "synthetic-availability-ref:" + domain, sha256(data).hexdigest()
    )


def open_generation(root, ref, expected_domain, role, control):
    if (
        not isinstance(ref, RecoveryRef)
        or not isinstance(control, Control)
        or ref.domain != expected_domain
        or ROLES.get(ref.domain) != role
        or ref.key_ref != "synthetic-availability-ref:" + ref.domain
        or ref.key_ref not in control.available_refs
    ):
        raise RecoveryDenied("recovery input or authority unavailable")
    try:
        folder = root / ref.domain
        path = folder / "generation.json"
        parent, info = folder.lstat(), path.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size > MAX_BYTES
        ):
            raise RecoveryDenied("recovery input unavailable")
        data = path.read_bytes()
        if sha256(data).hexdigest() != ref.digest:
            raise RecoveryDenied("recovery input unavailable")
        return json.loads(data)
    except (OSError, ValueError, TypeError):
        raise RecoveryDenied("recovery input unavailable") from None


def restore_vault(root, ref, role, control):
    records = open_generation(root, ref, "vault", role, control)
    return {
        token: binding
        for token, binding in records.items()
        if token not in control.revoked and binding["generation"] == control.generation
    }


def restore_evidence(root, ref, role, control):
    return open_generation(root, ref, "evidence", role, control)


def approved_summary(payload):
    if set(payload) != {"purpose", "generation", "summary"}:
        raise RecoveryDenied("projection unavailable")
    if payload["purpose"] != PURPOSE or type(payload["generation"]) is not int:
        raise RecoveryDenied("projection unavailable")
    summary = payload["summary"]
    if set(summary) != {"channel", "unit", "count", "mean"}:
        raise RecoveryDenied("projection unavailable")
    if (
        (summary["channel"], summary["unit"])
        not in {("heart_rate", "bpm"), ("hrv_sdnn", "ms")}
        or type(summary["count"]) is not int
        or not 1 <= summary["count"] <= 100_000
        or type(summary["mean"]) not in (int, float)
        or not 0 < summary["mean"] <= 10_000
        or not math.isfinite(summary["mean"])
    ):
        raise RecoveryDenied("projection unavailable")
    return summary


def restore_projection(root, ref, vault_ref, control, *, role, purpose, token):
    if role != "analytics-reader" or purpose != PURPOSE:
        raise RecoveryDenied("projection unavailable")
    try:
        # The lower-privilege access path receives an approved projection and
        # control result only. It has no reference to an evidence generation.
        vault = restore_vault(root, vault_ref, "vault-custodian", control)
        binding = vault.get(token)
        if binding is None or binding["purpose"] != purpose:
            raise RecoveryDenied("projection unavailable")
        projection = open_generation(
            root, ref, "projection", "projection-custodian", control
        )
        if (
            projection["generation"] != control.generation
            or projection["purpose"] != purpose
            or ref.digest != binding["projection_digest"]
        ):
            raise RecoveryDenied("projection unavailable")
        return approved_summary(projection)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise RecoveryDenied("projection unavailable") from None


class PrivacyRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="mse-privacy-restore-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.token = uuid.uuid4().hex
        self.original = {
            "source_id": "synthetic-source-only-secret",
            "original": "synthetic-raw-only-marker",
            "original_timestamp": "2026-11-21T01:02:03Z",
        }
        self.summary = {"channel": "hrv_sdnn", "unit": "ms", "count": 5, "mean": 42}
        self.envelope = {"purpose": PURPOSE, "generation": 4, "summary": self.summary}
        self.projection = seal(self.root, "projection", self.envelope)
        self.evidence = seal(self.root, "evidence", self.original)
        self.vault = seal(
            self.root,
            "vault",
            {
                self.token: {
                    "purpose": PURPOSE,
                    "generation": 4,
                    "projection_digest": self.projection.digest,
                    "subject": "synthetic-vault-only-subject",
                }
            },
        )
        self.control = Control(
            4,
            frozenset(
                ref.key_ref for ref in (self.vault, self.evidence, self.projection)
            ),
            frozenset(),
        )

    def read(
        self,
        *,
        control=None,
        vault=True,
        role="analytics-reader",
        purpose=PURPOSE,
        token=None,
        projection=None,
    ):
        return restore_projection(
            self.root,
            projection or self.projection,
            self.vault if vault else None,
            control or self.control,
            role=role,
            purpose=purpose,
            token=token or self.token,
        )

    def test_analytics_restore_exposes_only_summary(self):
        self.assertEqual(
            restore_evidence(
                self.root, self.evidence, "evidence-custodian", self.control
            ),
            self.original,
        )
        with self.assertRaises(RecoveryDenied):
            restore_evidence(self.root, self.evidence, "analytics-reader", self.control)
        # Removing the evidence fixture shows there is no raw fallback dependency.
        (self.root / "evidence/generation.json").unlink()
        output = self.read()
        self.assertEqual(output, self.summary)
        for forbidden in (
            *self.original.values(),
            self.token,
            "synthetic-vault-only-subject",
            self.projection.digest,
        ):
            self.assertNotIn(forbidden, encode(output).decode())

    def test_revoked_mapping_stays_revoked_after_vault_restore(self):
        updated = replace(self.control, revoked=frozenset({self.token}))
        self.assertEqual(
            restore_vault(self.root, self.vault, "vault-custodian", updated), {}
        )
        with self.assertRaisesRegex(RecoveryDenied, "^projection unavailable$"):
            self.read(control=updated)

    def test_missing_vault_path_or_reference_fails_closed(self):
        for missing_vault in (False, True):
            if missing_vault:
                (self.root / "vault/generation.json").unlink()
            with self.assertRaisesRegex(RecoveryDenied, "^projection unavailable$"):
                self.read(vault=missing_vault)

    def test_missing_key_reference_denies_each_recovery_domain(self):
        for missing in (self.vault, self.projection):
            with (
                self.subTest(missing=missing.domain),
                self.assertRaises(RecoveryDenied),
            ):
                self.read(
                    control=replace(
                        self.control,
                        available_refs=self.control.available_refs - {missing.key_ref},
                    )
                )
        without_evidence_ref = replace(
            self.control,
            available_refs=self.control.available_refs - {self.evidence.key_ref},
        )
        with self.assertRaises(RecoveryDenied):
            restore_evidence(
                self.root, self.evidence, "evidence-custodian", without_evidence_ref
            )

    def test_purpose_role_token_and_generation_do_not_cross(self):
        for changed in (
            {"purpose": "different"},
            {"role": "evidence-custodian"},
            {"token": uuid.uuid4().hex},
            {"control": replace(self.control, generation=5)},
        ):
            with self.subTest(changed=list(changed)), self.assertRaises(RecoveryDenied):
                self.read(**changed)

    def test_extraneous_raw_fields_rejected_even_after_reseal(self):
        bad = dict(self.envelope, original=self.original)
        with self.assertRaisesRegex(RecoveryDenied, "^projection unavailable$"):
            approved_summary(bad)
        with self.assertRaisesRegex(RecoveryDenied, "^projection unavailable$"):
            approved_summary(
                dict(self.envelope, summary=dict(self.summary, source_id="raw"))
            )

    def test_domain_recovery_cannot_substitute_other_generations(self):
        with self.assertRaises(RecoveryDenied):
            restore_evidence(self.root, self.vault, "vault-custodian", self.control)
        with self.assertRaises(RecoveryDenied):
            restore_vault(self.root, self.evidence, "evidence-custodian", self.control)
        with self.assertRaises(RecoveryDenied):
            self.read(projection=self.vault)

    def test_resealed_projection_cannot_reuse_vault_link(self):
        path = self.root / "projection/generation.json"
        new = encode(dict(self.envelope, summary=dict(self.summary, mean=43)))
        path.write_bytes(new)
        with self.assertRaises(RecoveryDenied):
            self.read(
                projection=replace(self.projection, digest=sha256(new).hexdigest())
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
