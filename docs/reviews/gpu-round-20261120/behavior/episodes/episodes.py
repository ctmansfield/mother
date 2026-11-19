#!/usr/bin/env python3
"""Deterministic synthetic behavioral episode ledger and continuity gates.

CPU-only source module. No model inference, clinician recommendation, clinical
interpretation, network access, external action, or automatic evidence promotion.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re

SCHEMA = "mother.behavioral-episode.v1"
RECORD = "mother.behavioral-ledger-record.v1"
KINDS = frozenset(("RECOMMENDATION", "ACKNOWLEDGMENT", "ACTION",
    "BEHAVIOR_MEASURE", "PHYSIOLOGY_MEASURE", "PREDICTION",
    "PREDICTION_EVALUATION", "LESSON", "MODEL_REPLACEMENT"))
ID = re.compile(r"^[a-z][a-z0-9_.-]{1,90}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
ZERO = "0" * 64
FIELDS = frozenset(("event_id", "episode_id", "kind", "observed_at",
    "available_at", "recorded_at", "actor_version", "references", "data"))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pairs_unique(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_event(event):
    require(isinstance(event, dict) and set(event) == FIELDS, "event fields")
    for name in ("event_id", "episode_id", "actor_version"):
        require(isinstance(event[name], str) and ID.fullmatch(event[name]), "invalid " + name)
    require(event["kind"] in KINDS, "unknown event kind")
    for name in ("observed_at", "available_at", "recorded_at"):
        require(type(event[name]) is int and 0 <= event[name] <= 10**12, "invalid " + name)
    require(event["observed_at"] <= event["available_at"] <= event["recorded_at"],
            "observation/availability/record time ordering")
    refs = event["references"]
    require(isinstance(refs, list) and len(refs) <= 8 and len(refs) == len(set(refs))
            and all(isinstance(x, str) and ID.fullmatch(x) for x in refs),
            "invalid evidence references")
    data = event["data"]
    require(isinstance(data, dict), "event data must be object")
    kind = event["kind"]
    keys = set(data)
    expected = {
        "RECOMMENDATION": {"offer"},
        "ACKNOWLEDGMENT": {"acknowledged"},
        "ACTION": {"completed"},
        "BEHAVIOR_MEASURE": {"metric", "value", "phase"},
        "PHYSIOLOGY_MEASURE": {"metric", "value", "phase"},
        "PREDICTION": {"target_kind", "metric", "predicted_value", "cutoff"},
        "PREDICTION_EVALUATION": {"prediction_id", "actual_measure_id", "error"},
        "LESSON": {"text", "status"},
        "MODEL_REPLACEMENT": {"predecessor_version", "successor_version"},
    }
    require(keys == expected[kind], "data shape differs for " + kind)
    if kind == "RECOMMENDATION":
        require(isinstance(data["offer"], str) and 1 <= len(data["offer"]) <= 300, "offer bounds")
    if kind in ("ACKNOWLEDGMENT", "ACTION"):
        require(data["acknowledged" if kind == "ACKNOWLEDGMENT" else "completed"] is True,
                "positive event required; missingness is not a negative action")
    if kind in ("BEHAVIOR_MEASURE", "PHYSIOLOGY_MEASURE"):
        require(isinstance(data["metric"], str) and ID.fullmatch(data["metric"]), "metric ID")
        require(type(data["value"]) in (int, float) and math.isfinite(data["value"]), "finite measure")
        require(data["phase"] in ("before", "after"), "measure phase")
    if kind == "PREDICTION":
        require(data["target_kind"] in ("BEHAVIOR_MEASURE", "PHYSIOLOGY_MEASURE"), "prediction channel")
        require(isinstance(data["metric"], str) and ID.fullmatch(data["metric"]), "prediction metric")
        require(type(data["predicted_value"]) in (int, float) and math.isfinite(data["predicted_value"]), "prediction value")
        require(type(data["cutoff"]) is int and data["cutoff"] <= event["observed_at"], "prediction cutoff")
    if kind == "PREDICTION_EVALUATION":
        require(all(isinstance(data[k], str) and ID.fullmatch(data[k]) for k in ("prediction_id", "actual_measure_id")),
                "evaluation binding")
        require(type(data["error"]) in (int, float) and math.isfinite(data["error"]), "evaluation error")
    if kind == "LESSON":
        require(isinstance(data["text"], str) and 1 <= len(data["text"]) <= 500, "lesson text")
        require(data["status"] == "UNVERIFIED_EXPERIENCE", "lessons cannot become verified facts")
    if kind == "MODEL_REPLACEMENT":
        require(all(isinstance(data[k], str) and ID.fullmatch(data[k])
                    for k in ("predecessor_version", "successor_version")), "model version identifiers")
        require(data["predecessor_version"] != data["successor_version"], "replacement must change version")
    require(len(canonical(event)) <= 4096, "event byte budget")
    return event


def adjudicate_event(event, prior):
    """Validate new event against history, never inference from absent records."""
    validate_event(event)
    existing = {row["event"]["event_id"]: row["event"] for row in prior}
    require(event["event_id"] not in existing, "event ID already exists")
    require(all(ref in existing and existing[ref]["episode_id"] == event["episode_id"]
                for ref in event["references"]), "missing/cross-episode reference")
    latest = max((row["event"]["recorded_at"] for row in prior), default=-1)
    require(event["recorded_at"] >= latest, "append order must preserve record availability")
    kind, data = event["kind"], event["data"]
    # Active specialist identity survives model replacement; predecessors cannot
    # silently resume writing under a retired version.
    versions = [row["event"]["data"]["successor_version"] for row in prior
                if row["event"]["kind"] == "MODEL_REPLACEMENT"]
    active = versions[-1] if versions else "v1"
    if kind != "MODEL_REPLACEMENT":
        require(event["actor_version"] == active, "event actor is not current specialist version")
    refs = [existing[ref] for ref in event["references"]]
    if kind == "ACKNOWLEDGMENT":
        require(any(ref["kind"] == "RECOMMENDATION" for ref in refs), "ack must refer to offer")
    if kind == "ACTION":
        require(any(ref["kind"] == "RECOMMENDATION" for ref in refs), "action must refer to offer")
    if kind == "PREDICTION":
        require(all(ref["available_at"] <= data["cutoff"] for ref in refs),
                "forecast cannot use future/late-available information")
    if kind == "PREDICTION_EVALUATION":
        p = existing.get(data["prediction_id"])
        actual = existing.get(data["actual_measure_id"])
        require(p is not None and actual is not None and p["episode_id"] == event["episode_id"]
                and actual["episode_id"] == event["episode_id"], "evaluation targets missing")
        require(p["kind"] == "PREDICTION" and
                actual["kind"] == p["data"]["target_kind"] and
                actual["data"]["metric"] == p["data"]["metric"] and
                actual["data"]["phase"] == "after", "evaluation target/channel mismatch")
        require(p["event_id"] in event["references"] and actual["event_id"] in event["references"],
                "evaluation must cite both prediction and actual observation")
        require(actual["observed_at"] > p["observed_at"], "prediction must precede outcome")
        error = actual["data"]["value"] - p["data"]["predicted_value"]
        require(math.isclose(error, data["error"], rel_tol=0, abs_tol=1e-9), "prediction error inconsistent")
    if kind == "LESSON":
        require(refs and any(ref["kind"] == "PREDICTION_EVALUATION" for ref in refs),
                "lesson needs an observed prediction-evaluation receipt")
    if kind == "MODEL_REPLACEMENT":
        require(event["actor_version"] == data["successor_version"], "successor actor binding")
        versions = [row["event"]["data"]["successor_version"] for row in prior
                    if row["event"]["kind"] == "MODEL_REPLACEMENT"]
        require(data["predecessor_version"] == (versions[-1] if versions else "v1"),
                "predecessor version must match active lineage")
    return True


def verify_records(raw):
    rows = []
    previous = ZERO
    for position, line in enumerate(raw.splitlines()):
        require(len(line) <= 8192, "ledger line over byte budget")
        row = json.loads(line, object_pairs_hook=pairs_unique, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        require(isinstance(row, dict) and set(row) == {"schema", "index", "previous", "event", "sha256"}, "ledger record fields")
        require(row["schema"] == RECORD and type(row["index"]) is int and row["index"] == position,
                "ledger index not append-only")
        require(row["previous"] == previous and DIGEST.fullmatch(row["sha256"]), "ledger hash chain mismatch")
        signed = {k: row[k] for k in ("schema", "index", "previous", "event")}
        require(digest(canonical(signed)) == row["sha256"], "ledger entry altered")
        adjudicate_event(row["event"], rows)
        rows.append(row)
        previous = row["sha256"]
    return rows


def append(path, event):
    """Newline-only append with exclusive local flock. No deletion/overwrite."""
    import fcntl
    path = Path(path)
    require(path.parent.exists() and path.parent.is_dir(), "ledger parent must exist")
    if path.is_symlink():
        raise ValueError("symlink ledger refused")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        data = stream.read()
        rows = verify_records(data)
        adjudicate_event(event, rows)
        rec = {"schema": RECORD, "index": len(rows),
               "previous": rows[-1]["sha256"] if rows else ZERO,
               "event": event}
        rec["sha256"] = digest(canonical(rec))
        stream.seek(0, os.SEEK_END)
        stream.write(canonical(rec) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
        return rec["sha256"]


def episode_view(rows, episode_id):
    """Only observed channels; never equate offer, ack, action or host effect."""
    events = [row["event"] for row in rows if row["event"]["episode_id"] == episode_id]
    by_kind = {kind: [e for e in events if e["kind"] == kind] for kind in KINDS}
    changes = {}
    for kind in ("BEHAVIOR_MEASURE", "PHYSIOLOGY_MEASURE"):
        metrics = {e["data"]["metric"] for e in by_kind[kind]}
        changes[kind] = {}
        for metric in metrics:
            before = [e for e in by_kind[kind] if e["data"]["metric"] == metric and e["data"]["phase"] == "before"]
            after = [e for e in by_kind[kind] if e["data"]["metric"] == metric and e["data"]["phase"] == "after"]
            changes[kind][metric] = (
                after[-1]["data"]["value"] - before[-1]["data"]["value"]
                if before and after else None)
    return {
        "episode_id": episode_id,
        "offered": bool(by_kind["RECOMMENDATION"]),
        "acknowledged": bool(by_kind["ACKNOWLEDGMENT"]),
        "acted": bool(by_kind["ACTION"]),
        "changes": changes,
        "prediction_evaluations": len(by_kind["PREDICTION_EVALUATION"]),
        "unverified_lessons": [e["event_id"] for e in by_kind["LESSON"]],
        "model_replacements": [e["data"] for e in by_kind["MODEL_REPLACEMENT"]],
        "causality": "NOT_ESTABLISHED",
        "clinical_or_scientific_promotion": "NOT_APPROVED"
    }
