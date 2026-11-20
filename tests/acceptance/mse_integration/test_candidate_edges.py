"""Independent probes for ATLAS 0.1 candidate rules before the contract freeze."""

import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_EVEN

from test_fixture_contract import EXPECTED, FIXTURES


EDGES = EXPECTED["provisional_edges"]
EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)


def strict_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def source_time(lexeme):
    exact = Decimal(lexeme) * 1_000_000
    rounded = exact.to_integral_value(rounding=ROUND_HALF_EVEN)
    time = EPOCH + timedelta(microseconds=int(rounded))
    return time.isoformat(timespec="microseconds").replace("+00:00", "Z"), exact != rounded


class CandidateEdges(unittest.TestCase):
    def test_edge_artifacts_match_pins(self):
        for name, edge in EDGES.items():
            with self.subTest(name=name):
                data = (FIXTURES / edge["file"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), edge["sha256"])

    def test_distinct_delete_facts_include_unknown_uuid(self):
        edge = EDGES["repeated-delete"]
        artifact = json.loads((FIXTURES / edge["file"]).read_bytes())
        row, = artifact["readings"]
        facts = {key: [time] for key, time in artifact["tombstones"].items()}
        facts[row["id"]].append(row["deletedAt"])
        self.assertEqual({key: sorted(times) for key, times in facts.items()}, edge["delete_facts"])
        unknown, = facts.keys() - {row["id"]}
        self.assertEqual(len(facts[unknown]), 1)

    def test_numeric_lexeme_and_half_even_rounding_vector(self):
        edge = EDGES["numeric-time"]
        raw = (FIXTURES / edge["file"]).read_bytes()
        row, = json.loads(raw, parse_float=str)["readings"]
        self.assertEqual(row["value"], edge["value_lexeme"])
        self.assertEqual(Decimal(row["value"]), Decimal(edge["decimal_value"]))
        self.assertEqual(source_time(row["start"]), (edge["start_utc"], True))
        self.assertEqual(source_time(row["end"]), (edge["end_utc"], True))

    def test_invalid_vectors_are_unambiguous(self):
        duplicate = (FIXTURES / EDGES["duplicate-json-key"]["file"]).read_bytes()
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            json.loads(duplicate, object_pairs_hook=strict_keys)
        row, = json.loads((FIXTURES / EDGES["reversed-interval"]["file"]).read_bytes())["readings"]
        self.assertGreater(row["start"], row["end"])

    def test_provisional_canonical_json_digest_vector(self):
        value = {"label": "Café", "count": 1, "unit": None}
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        self.assertEqual(data, b'{"count":1,"label":"Caf\xc3\xa9","unit":null}')
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            'c1cd15b180317ec830c9641918fa1cb59412acdd3eb1b65dd0701861acac9010',
        )
