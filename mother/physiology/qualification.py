"""Conservative, read-only assessment of an exported physiology replay.

The output is a *local diagnostic*, not a device capability verification or a
personal-response score. It intentionally excludes subject IDs, raw source
records, individual values and event payloads.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
from typing import Any

VERSION = "r02-qualification/0.1.0"
MAX_INPUT_BYTES = 64 * 1024 * 1024


def _instant(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("A required offset-aware timestamp is missing")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Malformed timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Naive timestamp is unsupported")
    return result.astimezone(timezone.utc)


def _is_number(value: Any) -> bool:
    return type(value) in (int, float) and not isinstance(value, bool)


def assess_replay(bundle: dict) -> dict:
    """Summarize declared evidence without modifying or authenticating it.

    Input must already be a canonical PF-001 replay. This checks structural
    dependencies, but is not a replacement for the versioned JSON schema.
    """
    if not isinstance(bundle, dict) or bundle.get("schema_version") != "1.0.0":
        raise ValueError("A contract 1.0.0 replay bundle is required")
    for field in ("observations", "events", "source_revisions", "sessions", "coverage"):
        if not isinstance(bundle.get(field), list):
            raise ValueError(f"{field} must be a list")
    start, end = _instant(bundle.get("start")), _instant(bundle.get("end"))
    if start >= end:
        raise ValueError("Replay interval must have positive duration")
    metadata = bundle.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    revs: dict[str, str] = {}
    for rev in bundle["source_revisions"]:
        if not isinstance(rev, dict):
            raise ValueError("Invalid source revision")
        ident, source = rev.get("id"), rev.get("source_instance")
        if (
            not isinstance(ident, str)
            or not ident
            or not isinstance(source, str)
            or not source
        ):
            raise ValueError("Source revision identity is missing")
        if ident in revs:
            raise ValueError("Duplicate source revision identity")
        revs[ident] = source

    groups: dict[tuple[str, str], dict] = {}
    candidates = defaultdict(set)
    status_counts = Counter()
    epistemic_counts = Counter()
    checks = Counter()
    obs_by_source = Counter()
    for obs in bundle["observations"]:
        if not isinstance(obs, dict) or obs.get("record_type") != "observation":
            raise ValueError("Invalid observation")
        revision = obs.get("source_revision_id")
        if revision not in revs:
            raise ValueError("Observation has unresolved source lineage")
        source = revs[revision]
        channel = obs.get("channel")
        if not isinstance(channel, str) or not channel:
            raise ValueError("Observation channel missing")
        measurement = _instant(obs.get("measurement_start"))
        state = obs.get("value_status")
        epistemic = obs.get("epistemic_type")
        if state not in {"valid", "missing", "invalid", "unobserved"}:
            raise ValueError("Invalid value status")
        if not isinstance(epistemic, str) or not epistemic:
            raise ValueError("Missing epistemic type")
        status_counts[state] += 1
        epistemic_counts[epistemic] += 1
        obs_by_source[source] += 1
        key = (channel, source)
        item = groups.setdefault(
            key,
            {
                "channel": channel,
                "source_instance": source,
                "observations": 0,
                "statuses": Counter(),
                "epistemic_types": Counter(),
                "units": set(),
                "unknown_source_availability": 0,
                "original_clock_offsets_checked": 0,
                "quality_flags": set(),
            },
        )
        item["observations"] += 1
        item["statuses"][state] += 1
        item["epistemic_types"][epistemic] += 1
        if obs.get("unit") is not None:
            item["units"].add(obs["unit"])
        item["quality_flags"].update(obs.get("quality_flags", []))
        available = obs.get("source_available_at")
        if available is None:
            item["unknown_source_availability"] += 1
        elif _instant(available) < measurement:
            checks["availability_before_measurement"] += 1
        seen, ingested = obs.get("first_seen_at"), obs.get("ingested_at")
        if (
            seen is not None
            and ingested is not None
            and _instant(ingested) < _instant(seen)
        ):
            checks["ingested_before_first_seen"] += 1
        original_clock = obs.get("clock") or {}
        if not isinstance(original_clock, dict):
            raise ValueError("Observation clock must be an object")
        original_time = original_clock.get("original_timestamp")
        if original_time is not None:
            item["original_clock_offsets_checked"] += 1
            if _instant(original_time) != measurement:
                checks["original_clock_utc_mismatch"] += 1
        # Equal normalized samples are *candidates* for investigation, never
        # proof of duplicate identity or independent evidence.
        if (
            state == "valid"
            and epistemic in {"measured", "vendor_derived", "reported"}
            and (_is_number(obs.get("value")) or isinstance(obs.get("value"), str))
        ):
            signature = (channel, measurement, str(obs.get("value")), obs.get("unit"))
            candidates[signature].add(source)

    cov = []
    for item in bundle["coverage"]:
        if not isinstance(item, dict) or not isinstance(item.get("channel"), str):
            raise ValueError("Invalid coverage row")
        if not isinstance(item.get("gaps"), list):
            raise ValueError("Coverage gaps must be a list")
        cov.append(
            {
                "channel": item["channel"],
                "source_instance": item.get("source_instance"),
                "declared_status": item.get("status"),
                "declared_count": item.get("count"),
                "declared_valid_count": item.get("valid_count"),
                "gap_count": len(item["gaps"]),
                "cadence_seconds": item.get("expected_cadence_seconds"),
            }
        )
    imported = metadata.get("import_summaries", [])
    if not isinstance(imported, list):
        raise ValueError("Import summaries must be an array")
    incomplete_imports = sum(1 for run in imported if run.get("status") != "complete")
    if incomplete_imports:
        checks["incomplete_import_runs"] = incomplete_imports
    if any(c["declared_status"] in {"partial", "absent", "unknown"} for c in cov):
        checks["incomplete_or_unknown_coverage_rows"] = sum(
            c["declared_status"] in {"partial", "absent", "unknown"} for c in cov
        )
    if any(c["cadence_seconds"] is None for c in cov):
        checks["unknown_cadence_rows"] = sum(c["cadence_seconds"] is None for c in cov)
    source_channels = []
    for key in sorted(groups):
        row = groups[key]
        source_channels.append(
            {
                "channel": row["channel"],
                "source_instance": row["source_instance"],
                "observations": row["observations"],
                "value_statuses": dict(sorted(row["statuses"].items())),
                "epistemic_types": dict(sorted(row["epistemic_types"].items())),
                "units": sorted(row["units"]),
                "unknown_source_availability": row["unknown_source_availability"],
                "original_clock_offsets_checked": row["original_clock_offsets_checked"],
                "quality_flags": sorted(row["quality_flags"]),
            }
        )
    relayed = [v for v in candidates.values() if len(v) > 1]
    return {
        "report_version": VERSION,
        "evidence_level": "offline_replay_inspection_only",
        "source_evidence_level": metadata.get("evidence_level", "unknown"),
        "timing_policy": metadata.get("timing_policy", "unknown"),
        "read_only": True,
        "no_personal_performance_claim": True,
        "real_data_reconciled": False,
        "live_device_qualified": False,
        "summary": {
            "observations": len(bundle["observations"]),
            "events": len(bundle["events"]),
            "sessions": len(bundle["sessions"]),
            "source_revisions": len(revs),
            "source_instances": len(obs_by_source),
            "value_statuses": dict(sorted(status_counts.items())),
            "epistemic_types": dict(sorted(epistemic_counts.items())),
            "possible_cross_source_equal_sample_groups": len(relayed),
            "incomplete_import_runs": incomplete_imports,
        },
        "source_channels": source_channels,
        "declared_coverage": sorted(
            cov, key=lambda x: (x["channel"], str(x["source_instance"]))
        ),
        "review_flags": dict(sorted(checks.items())),
        "limitations": [
            "This report checks declared replay content, not original device files or server responses.",
            "Equal channel/time/value/unit across sources is a candidate for relay review, not a deduplication decision.",
            "Missing cadence or source availability cannot be inferred from observations.",
            "No source-native counts, exercise-end, principal sleep, or clinical outcomes have been authenticated.",
        ],
    }


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON constant {value} is unsupported")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Existing local replay JSON"
    )
    parser.add_argument(
        "--output", required=True, type=Path, help="New local report JSON"
    )
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Input and output paths must differ")
    if args.input.stat().st_size > MAX_INPUT_BYTES:
        parser.error("Replay exceeds 64 MiB local qualification limit")
    with args.input.open("r", encoding="utf-8") as handle:
        report = assess_replay(json.load(handle, parse_constant=_reject_constant))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Source names and quality flags may still be sensitive: create privately.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "report": str(args.output),
                "evidence_level": report["evidence_level"],
                "real_data_reconciled": False,
            }
        )
    )


if __name__ == "__main__":
    main()
