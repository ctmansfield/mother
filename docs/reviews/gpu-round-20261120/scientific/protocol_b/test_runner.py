import json
import unittest
from runner import revised_prompt, CANDIDATES, MARKER


def original(g, s, task):
    role = task["role"]
    prefix = (
        "You are a RESEARCH-SCREENING candidate for " + role + ". "
        "Only unverified source text may be proposed. Always abstain when evidence lacks proof.\n"
    )
    return (
        prefix
        + MARKER
        + json.dumps(
            {
                "edge": {"id": "edge-a", "kind": "reaction"},
                "source": {
                    "source_id": "source-a",
                    "abstract_text": "Some fictional experiment.",
                },
                "question": "Find only supported text.",
            },
            sort_keys=True,
        )
    )


class ProtocolBTests(unittest.TestCase):
    def test_three_frozen_candidates(self):
        self.assertEqual(
            CANDIDATES, ("deepseek-r1:14b", "medgemma:27b", "medgemma1.5:4b")
        )

    def test_role_is_explicit_in_model_visible_json(self):
        for role in ("SOURCE", "ECOLOGY", "METABOLIC", "RECEPTOR", "HOST"):
            output = revised_prompt(original, {}, {}, {"role": role})
            payload = json.loads(output.split(MARKER, 1)[1])
            self.assertEqual(payload["assigned_specialist_role"], role)
            self.assertNotIn("You are a RESEARCH-SCREENING candidate", output)
            self.assertIn("only unverified source text", output.lower())

    def test_source_and_question_unchanged(self):
        task = {"role": "RECEPTOR"}
        old = json.loads(original({}, {}, task).split(MARKER)[1])
        new = json.loads(revised_prompt(original, {}, {}, task).split(MARKER)[1])
        new.pop("assigned_specialist_role")
        self.assertEqual(old, new)

    def test_no_expected_labels_in_prompt(self):
        response = revised_prompt(original, {}, {}, {"role": "SOURCE"})
        for marker in (
            '"expected_decision"',
            '"expected_quote"',
            '"expected_polarity"',
        ):
            self.assertNotIn(marker, response)

    def test_modified_original_template_refused(self):
        def changed(g, s, t):
            return original(g, s, t).replace("RESEARCH-SCREENING candidate", "OTHER")

        with self.assertRaisesRegex(ValueError, "template changed"):
            revised_prompt(changed, {}, {}, {"role": "SOURCE"})

    def test_multiple_markers_refused(self):
        def changed(g, s, t):
            return original(g, s, t) + MARKER + "{}"

        with self.assertRaisesRegex(ValueError, "template changed"):
            revised_prompt(changed, {}, {}, {"role": "SOURCE"})

    def test_changed_source_envelope_refused(self):
        def changed(g, s, t):
            return (
                "You are a RESEARCH-SCREENING candidate for SOURCE. "
                + MARKER
                + '{"edge":{},"source":{},"question":"x","answer":"leak"}'
            )

        with self.assertRaisesRegex(ValueError, "envelope changed"):
            revised_prompt(changed, {}, {}, {"role": "SOURCE"})

    def test_protected_answer_cannot_be_inserted(self):
        def bad(g, s, t):
            return (
                "You are a RESEARCH-SCREENING candidate for SOURCE. "
                + MARKER
                + '{"edge":{},"source":{},"question":"expected_decision","expected_quote":"x"}'
            )

        with self.assertRaises(ValueError):
            revised_prompt(bad, {}, {}, {"role": "SOURCE"})


if __name__ == "__main__":
    unittest.main()
