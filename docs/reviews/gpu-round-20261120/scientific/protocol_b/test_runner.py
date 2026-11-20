import json
import unittest
from unittest.mock import Mock
from runner import revised_prompt, guarded_proposal, CANDIDATES, MARKER


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


class EligibilityGuardTests(unittest.TestCase):
    def test_only_disqualified_bound_candidates_are_replaced(self):
        task = dict(
            id="case",
            role="SOURCE",
            edge_id="edge",
            source_id="source",
            objective="candidate-text",
            retraction_status="flag",
            expected_decision="ABSTAIN",
        )
        raw = "saved response"
        grader = Mock()
        grader.check_input.return_value = ("edge", "record")
        for allowed, reason in (
            (False, "possible_retraction"),
            (False, "specialist_role_mismatch"),
            (True, "text_anchor_only"),
            (False, "edge_unbound_source"),
        ):
            with self.subTest(reason=reason):
                grader.parse_response.return_value = {
                    key: task[key] for key in ("role", "edge_id", "source_id")
                } | {"decision": "CANDIDATE"}
                grader.edge_claim_permission.return_value = (allowed, reason)
                output, intervention = guarded_proposal(grader, raw, {}, {}, task)
                if reason in {"possible_retraction", "specialist_role_mismatch"}:
                    self.assertEqual(intervention, reason)
                    self.assertEqual(json.loads(output)["decision"], "ABSTAIN")
                else:
                    self.assertEqual((output, intervention), (raw, None))
                self.assertNotIn(
                    "expected_decision", grader.check_input.call_args.args[2]
                )
        grader.parse_response.side_effect = ValueError("invalid schema")
        self.assertEqual(guarded_proposal(grader, raw, {}, {}, task), (raw, None))


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
