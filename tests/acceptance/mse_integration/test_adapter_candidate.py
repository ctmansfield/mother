"""Independent fixture acceptance against the assembled HealthBridge adapter."""

import hashlib
import unittest

from test_fixture_contract import CASES, FIXTURES


class AdapterAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from integrations.healthbridge.capture import CaptureError
            from integrations.healthbridge.export import normalize_capture
        except ModuleNotFoundError as error:
            if error.name not in {"integrations", "integrations.healthbridge"}:
                raise
            raise unittest.SkipTest("assemble the pinned HealthBridge adapter candidate")
        cls.normalize = staticmethod(normalize_capture)
        cls.error = CaptureError

    def normalize_case(self, name):
        case = CASES[name]
        path = FIXTURES / case["file"]
        raw = path.read_bytes()
        export = self.normalize(
            raw, subject_id="synthetic-acceptance", source_instance="synthetic-store",
            batch_id=case["batch_id"], capture_id=f"capture-{name}",
            capture_kind="partial" if case["coverage"] == "partial" else "full_file",
        )
        self.assertEqual(export["artifact"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(path.read_bytes(), raw)
        return export

    def test_accepted_fixture_membership(self):
        for name in ("baseline", "partial", "empty", "late"):
            with self.subTest(name=name):
                case = CASES[name]
                rows = self.normalize_case(name)["revisions"]
                upserts = {row["native_id"] for row in rows if row["operation"] == "upsert"}
                deletes = {row["native_id"] for row in rows if row["operation"] == "delete"}
                self.assertEqual(upserts, {key.lower() for key, _ in case["observed_revisions"]})
                self.assertEqual(deletes, {key.lower() for key in case["tombstone_ids"]})
                self.assertEqual(upserts - deletes, {key.lower() for key in case["live_ids"]})

    def test_bad_capture_is_rejected(self):
        for name in ("conflicting-uuid", "malformed"):
            with self.subTest(name=name), self.assertRaises(self.error):
                self.normalize_case(name)
