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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directive", required=True, type=Path)
    parser.add_argument("--as-of", required=True, type=int)
    parser.add_argument("receipts", nargs="*", type=Path)
    args = parser.parse_args()
    result = _qualify(args.directive, args.receipts, args.as_of)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.disposition == "ELIGIBLE_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
