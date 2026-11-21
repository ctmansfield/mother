"""Run receipt-bound handoff qualification offline against explicit files."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .receipt_bound_handoff import (
    Directive,
    HandoffRule,
    ReceiptPin,
    Result,
    _unique_object,
    check_candidate,
    derive_handoff,
)

DIRECTIVE_STRINGS = {"task_id", "revision", "artifact_sha256"}
DIRECTIVE_FIELDS = DIRECTIVE_STRINGS | {
    "valid_from",
    "expires_at",
    "pins",
    "state_rules",
}
PIN_FIELDS = {"issuer", "receipt_id", "sha256"}
RULE_FIELDS = {"status", "next_owner", "next_action_code"}


def _string_fields(value, fields):
    return all(isinstance(value.get(key), str) and value[key].strip() for key in fields)


def _directive(raw: bytes) -> Directive:
    obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if (
        not isinstance(obj, dict)
        or obj.keys() != DIRECTIVE_FIELDS
        or not _string_fields(obj, DIRECTIVE_STRINGS)
        or type(obj["valid_from"]) is not int
        or type(obj["expires_at"]) is not int
        or not isinstance(obj["pins"], list)
        or not isinstance(obj["state_rules"], dict)
    ):
        raise ValueError("invalid directive structure")

    pins = []
    for pin in obj["pins"]:
        if (
            not isinstance(pin, dict)
            or pin.keys() != PIN_FIELDS
            or not _string_fields(pin, PIN_FIELDS)
        ):
            raise ValueError("invalid pin structure")
        pins.append(ReceiptPin(**pin))

    rules = {}
    for state, rule in obj["state_rules"].items():
        if (
            not state.strip()
            or not isinstance(rule, dict)
            or rule.keys() != RULE_FIELDS
            or not _string_fields(rule, RULE_FIELDS)
        ):
            raise ValueError("invalid state rule structure")
        rules[state] = HandoffRule(**rule)

    return Directive(**{**obj, "pins": tuple(pins), "state_rules": rules})


def _qualify(directive_path: Path, receipt_paths: list[Path], as_of: int) -> Result:
    try:
        directive_bytes = directive_path.read_bytes()
    except OSError:
        return Result("HOLD", "unreadable_input")
    try:
        directive = _directive(directive_bytes)
    except (ValueError, RecursionError):
        return Result("HOLD", "invalid_directive_document")
    try:
        receipts = [path.read_bytes() for path in receipt_paths]
    except OSError:
        return Result("HOLD", "unreadable_input")
    return derive_handoff(directive, receipts, as_of=as_of)


def _candidate_output(result: Result, reason: str, defects: list[str]) -> dict:
    handoff = asdict(result.handoff) if result.handoff is not None else None
    return {
        "disposition": "HOLD",
        "reason": reason,
        "handoff": handoff,
        "defects": defects,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directive", required=True, type=Path)
    parser.add_argument("--as-of", required=True, type=int)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("receipts", nargs="*", type=Path)
    args = parser.parse_args()

    result = _qualify(args.directive, args.receipts, args.as_of)

    if args.candidate is None:
        print(json.dumps(asdict(result), sort_keys=True))
        return 0 if result.disposition == "ELIGIBLE_FOR_REVIEW" else 2

    # Candidate mode: receipt qualification must succeed first
    if result.disposition != "ELIGIBLE_FOR_REVIEW" or result.handoff is None:
        out = {
            "disposition": "HOLD",
            "reason": result.reason,
            "handoff": None,
            "defects": ["unverified_receipts"],
        }
        print(json.dumps(out, sort_keys=True))
        return 2

    # Read candidate bytes
    try:
        candidate_bytes = args.candidate.read_bytes()
    except OSError:
        out = _candidate_output(
            result, "unreadable_candidate", ["unreadable_candidate"]
        )
        print(json.dumps(out, sort_keys=True))
        return 2

    # Parse candidate JSON
    try:
        candidate = json.loads(
            candidate_bytes.decode("utf-8"), object_pairs_hook=_unique_object
        )
    except (ValueError, RecursionError, UnicodeDecodeError):
        out = _candidate_output(
            result, "invalid_candidate_document", ["malformed_candidate"]
        )
        print(json.dumps(out, sort_keys=True))
        return 2

    if not isinstance(candidate, dict):
        out = _candidate_output(
            result, "invalid_candidate_document", ["malformed_candidate"]
        )
        print(json.dumps(out, sort_keys=True))
        return 2

    # Check candidate against authoritative handoff
    review = check_candidate(result, candidate)

    if review.disposition == "ELIGIBLE_FOR_REVIEW":
        out = {
            "disposition": "ELIGIBLE_FOR_REVIEW",
            "reason": None,
            "handoff": asdict(result.handoff),
            "defects": [],
        }
        print(json.dumps(out, sort_keys=True))
        return 0
    else:
        out = _candidate_output(result, "candidate_mismatch", list(review.defects))
        print(json.dumps(out, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
