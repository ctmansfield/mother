import unittest
from replay import role_normalization, load_unique


class RoleShadowTests(unittest.TestCase):
    def test_exact_role_remains(self):
        self.assertEqual(role_normalization("ECOLOGY", "ECOLOGY"), "UNCHANGED")

    def test_generic_echo(self):
        self.assertEqual(
            role_normalization("RESEARCH-SCREENING", "ECOLOGY"),
            "GENERIC_ROLE_LABEL_ECHO",
        )

    def test_full_intro_echo(self):
        self.assertEqual(
            role_normalization("RESEARCH-SCREENING candidate for HOST", "HOST"),
            "FULL_INTRODUCTORY_PHRASE_ECHO",
        )

    def test_wrong_role_refused(self):
        self.assertIsNone(role_normalization("SOURCE", "HOST"))

    def test_entity_edge_kind_refused(self):
        for item in (
            "reaction",
            "ecology",
            "receptor",
            "host-link",
            "premise-e1",
            "receptor-a",
        ):
            self.assertIsNone(role_normalization(item, "ECOLOGY"))

    def test_wrong_phrase_refused(self):
        self.assertIsNone(
            role_normalization("RESEARCH-SCREENING candidate for SOURCE", "HOST")
        )

    def test_case_never_normalized(self):
        self.assertIsNone(role_normalization("research-screening", "SOURCE"))

    def test_duplicate_json_rejected(self):
        with self.assertRaises(ValueError):
            load_unique('{"role":"HOST","role":"SOURCE"}')


if __name__ == "__main__":
    unittest.main()
