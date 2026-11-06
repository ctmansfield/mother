#!/usr/bin/env python3
"""Auditable CSV normalization for explicitly identified HRV metrics.

Legacy wide columns rmssd/sdnn are milliseconds unless a unit is supplied.
Long records require metric,value,unit. Raw input bytes and all source fields
are retained. Normalization does not reconstruct HRV from heart-rate averages.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import uuid

import pandas as pd

from mother.physiology.time import epoch_ms

ADAPTER_VERSION = "hrv-csv/1.0.0"
METRICS = {
    "rmssd": "rmssd",
    "sdnn": "sdnn",
    "hkquantitytypeidentifierheartratevariabilitysdnn": "sdnn",
    "hkquantitytypeidentifierheartratevariabilityrmssd": "rmssd",
}


def _metric(value: str) -> str | None:
    return METRICS.get(str(value).strip().lower())


def _retain_original(source: Path, out: Path) -> tuple[str, Path]:
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    directory = out.parent / "source_artifacts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{digest}.csv"
    try:
        with target.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("Existing source artifact does not match its content hash")
    return digest, target


def ingest_hrv_csv(
    source: str,
    out: str = "storage/analytics/hrv.parquet",
    timestamp_unit: str | None = None,
    naive_timezone: str | None = None,
) -> dict:
    """Write a regenerable metric-specific view plus an immutable run manifest.

    Per-row timestamp parsing accepts mixed epoch seconds/milliseconds and
    offset-bearing ISO8601. Naive timestamps require a declared source timezone.
    Invalid/unsupported records remain in the source artifact and manifest.
    """
    source_path, out_path = Path(source), Path(out)
    if not source_path.is_file():
        raise FileNotFoundError(source)
    if source_path.resolve() == out_path.resolve():
        raise ValueError("Output must not replace the source CSV")
    if timestamp_unit not in (None, "s", "ms"):
        raise ValueError("timestamp_unit must be s, ms, or omitted")
    digest, original_path = _retain_original(source_path, out_path)
    # Strings preserve per-row numeric magnitude, original offsets, and blanks.
    frame = pd.read_csv(source_path, dtype=str, keep_default_na=False)
    if "ts" not in frame:
        raise ValueError("CSV must contain a ts timestamp column")
    long_format = {"metric", "value"}.issubset(frame.columns)
    wide_metrics = [metric for metric in ("rmssd", "sdnn") if metric in frame]
    if not long_format and not wide_metrics:
        raise ValueError("CSV must identify rmssd/sdnn or provide metric,value,unit")
    records, rejections = [], []
    accepted_rows = set()
    assumed_unit_records = 0
    for i, row in frame.iterrows():
        source_row = int(i) + 2
        raw = row.to_dict()

        def reject(reason, metric=None):
            rejections.append(
                {
                    "source_row": source_row,
                    "metric": metric,
                    "reason": reason,
                    "original": raw,
                }
            )

        try:
            timestamp = epoch_ms(
                row["ts"], numeric_unit=timestamp_unit, naive_timezone=naive_timezone
            )
        except (ValueError, TypeError, OverflowError):
            reject("invalid_timestamp")
            continue
        if long_format:
            candidates = [(str(row["metric"]), str(row["value"]))]
        else:
            candidates = [
                (metric, str(row[metric]))
                for metric in wide_metrics
                if str(row[metric]).strip()
            ]
        if not candidates:
            reject("missing_metric_value")
        for identifier, raw_value in candidates:
            metric = _metric(identifier)
            if metric is None:
                reject("unsupported_metric", identifier)
                continue
            native = str(row.get("native_type") or identifier)
            native_metric = _metric(native)
            if native_metric is not None and native_metric != metric:
                reject("conflicting_metric_identifiers", identifier)
                continue
            try:
                value = float(raw_value)
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid HRV value")
            except (ValueError, TypeError, OverflowError):
                reject("invalid_metric_value", identifier)
                continue
            original_unit = str(row.get("unit", "")).strip()
            assumed_unit = not original_unit and not long_format
            if assumed_unit:
                original_unit = "ms"
            if original_unit.lower() in {"ms", "millisecond", "milliseconds"}:
                multiplier = 1.0
            elif original_unit.lower() in {"s", "second", "seconds"}:
                multiplier = 1000.0
            else:
                reject("missing_or_unsupported_unit", identifier)
                continue
            value *= multiplier
            record = dict(raw)
            record.update(
                {
                    "ts": timestamp,
                    "source_ts": str(row["ts"]),
                    "source_row": source_row,
                    "metric": metric,
                    "native_type": native,
                    "value": value,
                    "unit": "ms",
                    "original_value": raw_value,
                    "original_unit": str(row.get("unit", "")) or None,
                    "unit_basis": (
                        "legacy_metric_header_ms" if assumed_unit else "source_unit"
                    ),
                    "rmssd": value if metric == "rmssd" else None,
                    "sdnn": value if metric == "sdnn" else None,
                    "source_artifact_sha256": digest,
                    "processing_version": ADAPTER_VERSION,
                    "source_record_json": json.dumps(
                        raw, sort_keys=True, ensure_ascii=False, allow_nan=False
                    ),
                }
            )
            records.append(record)
            accepted_rows.add(source_row)
            assumed_unit_records += int(assumed_unit)
    expected = [
        "ts",
        "metric",
        "native_type",
        "value",
        "unit",
        "rmssd",
        "sdnn",
        "source_ts",
        "source_row",
        "original_value",
        "original_unit",
        "unit_basis",
        "source_artifact_sha256",
        "processing_version",
        "source_record_json",
    ]
    result = pd.DataFrame(records) if records else pd.DataFrame(columns=expected)
    result["ts"] = result["ts"].astype("Int64")
    for column in ("value", "rmssd", "sdnn"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.sort_values(["ts", "source_row", "metric"], kind="stable")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f".{out_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        result.to_parquet(temporary, index=False)
        os.replace(temporary, out_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    rejected_rows = {item["source_row"] for item in rejections}
    report = {
        "adapter_version": ADAPTER_VERSION,
        "import_run_id": str(uuid.uuid4()),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "source": str(source_path.resolve()),
        "source_artifact": str(original_path.resolve()),
        "source_sha256": digest,
        "out": str(out_path),
        "output_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "input_rows": len(frame),
        "accepted_input_rows": len(accepted_rows),
        "rejected_input_rows": len(rejected_rows - accepted_rows),
        "partially_rejected_input_rows": len(rejected_rows & accepted_rows),
        "rows": len(result),
        "rejected_records": len(rejections),
        "rejections": rejections,
        "assumed_ms_records": assumed_unit_records,
        "timestamp_unit": timestamp_unit,
        "timestamp_policy": (
            "per-record contemporary s/ms auto"
            if timestamp_unit is None
            else f"explicit {timestamp_unit}"
        ),
        "naive_timezone": naive_timezone,
        "availability_policy": "source timing retained; ingestion is not historical availability",
        "metric_counts": {
            str(k): int(v) for k, v in result["metric"].value_counts().items()
        },
    }
    manifest_dir = out_path.parent / "import_manifests"
    manifest_dir.mkdir(exist_ok=True)
    manifest = manifest_dir / f"hrv-{report['import_run_id']}.json"
    manifest.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    )
    report["manifest"] = str(manifest)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", required=True, help="CSV with ts plus explicit HRV metric(s)"
    )
    parser.add_argument("--out", default="storage/analytics/hrv.parquet")
    parser.add_argument("--timestamp-unit", choices=("s", "ms"), default=None)
    parser.add_argument(
        "--source-timezone",
        default=None,
        help="IANA timezone for otherwise naive source timestamps",
    )
    args = parser.parse_args()
    report = ingest_hrv_csv(
        args.source, args.out, args.timestamp_unit, args.source_timezone
    )
    # Rejected source rows are retained in the manifest, not printed to logs.
    print(
        {
            key: report[key]
            for key in ("rows", "input_rows", "rejected_records", "out", "manifest")
        }
    )


if __name__ == "__main__":
    main()
