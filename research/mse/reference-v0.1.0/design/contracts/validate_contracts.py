#!/usr/bin/env python3
"""Offline reference validation for proposed MSE contracts v0.1.0.

Requires jsonschema >= 4.18 and referencing. No network operations, ingestion,
clinical actions, or execution of extension/condition strings are implemented.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent
KINDS = ("mechanism-claim", "intervention-hypothesis", "causal-analysis", "measurement-request")


def reject_nonfinite(value):
    raise ValueError(f"Non-finite JSON number is invalid: {value}")


def load(path):
    return json.loads(path.read_text(), parse_constant=reject_nonfinite)


def typed_equal(left, right):
    # Python's True == 1 is not permitted as a typed contract comparison.
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return type(left) is type(right) and left == right or (
        isinstance(left, (int, float)) and not isinstance(left, bool)
        and isinstance(right, (int, float)) and not isinstance(right, bool)
        and left == right
    )


def evaluate_predicate(node, context):
    """Strong Kleene semantics; unknown input is never coerced to false.

    Context is a mapping from literal variable IDs to scalars or
    {"value": scalar, "unit": string|null}. No eval(), implicit unit conversion,
    inferred variable existence, or interpretation of arbitrary expressions.
    """
    op = node["op"]
    if op == "constant":
        return node["value"]
    if op in ("all_of", "any_of"):
        vals = [evaluate_predicate(item, context) for item in node["terms"]]
        if op == "all_of":
            return "false" if "false" in vals else "unknown" if "unknown" in vals else "true"
        return "true" if "true" in vals else "unknown" if "unknown" in vals else "false"
    if op == "not":
        return {"true": "false", "false": "true", "unknown": "unknown"}[evaluate_predicate(node["term"], context)]
    if op != "compare":
        return "unknown"
    value = context.get(node["variable"])
    unit = None
    if isinstance(value, dict):
        unit, value = value.get("unit"), value.get("value")
    if value is None or node["unit"] != unit:
        return "unknown"
    comparator, expected = node["comparator"], node["expected"]
    if comparator == "eq":
        answer = typed_equal(value, expected)
    elif comparator == "ne":
        answer = not typed_equal(value, expected)
    elif comparator == "in":
        answer = any(typed_equal(value, item) for item in expected)
    else:
        if not all(isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item)
                   for item in (value, expected)):
            return "unknown"
        answer = {"lt": value < expected, "le": value <= expected,
                  "gt": value > expected, "ge": value >= expected}.get(comparator)
        if answer is None:
            return "unknown"
    return "true" if answer else "false"


def eligible_for_review(record, context):
    """Review gate only; this function never grants execution authority."""
    return (evaluate_predicate(record["preconditions"], context) == "true"
            and evaluate_predicate(record["exclusions"], context) == "false")


def semantic_errors(value, location="$"):
    errors = []
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{location}: non-finite number")
    elif isinstance(value, dict):
        if "lower" in value and "upper" in value and value["lower"] > value["upper"]:
            errors.append(f"{location}: interval lower exceeds upper")
        if "earliest_seconds" in value and "latest_seconds" in value:
            lo, hi = value["earliest_seconds"], value["latest_seconds"]
            if lo is not None and hi is not None and lo > hi:
                errors.append(f"{location}: delay earliest exceeds latest")
        for key, item in value.items():
            errors.extend(semantic_errors(item, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(semantic_errors(item, f"{location}[{index}]"))
    return errors


def main():
    schemas = [load(path) for path in sorted(ROOT.glob("*.schema.json"))]
    for item in schemas:
        Draft202012Validator.check_schema(item)
    registry = Registry().with_resources((item["$id"], Resource.from_contents(item)) for item in schemas)
    validators = {
        kind: Draft202012Validator(load(ROOT / f"{kind}.schema.json"),
                                   registry=registry, format_checker=FormatChecker())
        for kind in KINDS
    }
    examples = {kind: load(ROOT / "examples" / f"{kind}.json") for kind in KINDS}
    results = []
    for kind, value in examples.items():
        errors = [item.message for item in validators[kind].iter_errors(value)] + semantic_errors(value)
        results.append({"check": f"schema_and_semantics:{kind}", "passed": not errors, "errors": errors})

    snapshot_digest = hashlib.sha256((ROOT / "examples/mechanism-snapshot.json").read_bytes()).hexdigest()
    for kind in ("mechanism-claim", "intervention-hypothesis", "measurement-request"):
        snapshot = examples[kind]["snapshot" if kind == "mechanism-claim" else "mechanism_snapshot"]
        results.append({"check": f"snapshot_digest:{kind}", "passed": snapshot["sha256"] == snapshot_digest})

    def rejected(name, kind, mutate):
        value = copy.deepcopy(examples[kind])
        mutate(value)
        errors = list(validators[kind].iter_errors(value)) + semantic_errors(value)
        results.append({"check": name, "passed": bool(errors)})

    rejected("reject_autonomous_mode", "intervention-hypothesis", lambda x: x.update(mode="autonomous_dosing"))
    rejected("reject_executable_dose_field", "intervention-hypothesis", lambda x: x.update(dose_mg=10))
    rejected("reject_unreviewed_execution_authority", "measurement-request", lambda x: x.update(execution_authority="execute"))
    rejected("reject_unbacked_established_claim", "mechanism-claim", lambda x: x.update(assertion_status="established_in_scope"))
    rejected("reject_false_default_for_missing", "intervention-hypothesis",
             lambda x: x["preconditions"]["terms"][0].update(missing_result="false"))
    rejected("reject_unestimated_individual_effect", "causal-analysis", lambda x: x.update(validity_status="individual_effect_supported"))
    rejected("reject_simulation_as_observed_association", "causal-analysis", lambda x: x["design"].update(type="simulation"))
    rejected("reject_unverified_numeric_eig", "measurement-request",
             lambda x: x.update(selection_score={"kind": "calibrated_expected_information_gain", "value_bits": 1.0}))
    rejected("reject_reversed_delay", "measurement-request",
             lambda x: x["proposed_observation"]["timing"].update(earliest_seconds=500, latest_seconds=100))

    def const(value):
        return {"op": "constant", "value": value}

    truth_tests = [
        ({"op": "all_of", "terms": [const("true"), const("unknown")]}, "unknown"),
        ({"op": "all_of", "terms": [const("false"), const("unknown")]}, "false"),
        ({"op": "any_of", "terms": [const("false"), const("unknown")]}, "unknown"),
        ({"op": "any_of", "terms": [const("true"), const("unknown")]}, "true"),
        ({"op": "not", "term": const("unknown")}, "unknown"),
    ]
    for index, (node, expected) in enumerate(truth_tests):
        results.append({"check": f"kleene_truth_table:{index}", "passed": evaluate_predicate(node, {}) == expected})
    comparison = {"op": "compare", "variable": "x", "comparator": "eq", "expected": True,
                  "unit": None, "missing_result": "unknown"}
    results.extend([
        {"check": "missing_leaf_is_unknown", "passed": evaluate_predicate(comparison, {}) == "unknown"},
        {"check": "no_bool_numeric_coercion", "passed": evaluate_predicate(comparison, {"x": 1}) == "false"},
        {"check": "no_implicit_unit_conversion", "passed": evaluate_predicate({**comparison, "expected": 1, "unit": "s"},
                                                                            {"x": {"value": 1, "unit": "ms"}}) == "unknown"},
        {"check": "unknown_conditions_withhold_review", "passed": not eligible_for_review(examples["intervention-hypothesis"], {})},
    ])
    passed = sum(item["passed"] for item in results)
    report = {"contract_version": "0.1.0", "status": "passed" if passed == len(results) else "failed",
              "checks_passed": passed, "checks_total": len(results), "checks": results,
              "scope": "Schema/fixture/logic software verification only; not biological, causal, clinical or device validation."}
    (ROOT / "validation-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "checks"}, indent=2))
    for item in results:
        if not item["passed"]:
            print(json.dumps(item, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
