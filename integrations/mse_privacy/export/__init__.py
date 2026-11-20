"""Aggregate analytical output from a restricted local synthetic snapshot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
import json
from secrets import token_hex

from integrations.mse_ingest.connected import ConnectedIngest

POLICY_VERSION = "synthetic-aggregate-hr-sdnn/0.1"
PROJECTION_VERSION = "relative-hour-mean/0.1"
FIELDS = frozenset({"bucket_index", "channel", "unit", "mean_value"})
CLASSES = {
    ("heart_rate", "bpm"): "measured",
    ("hrv_sdnn", "ms"): "vendor_derived",
}
HOUR = timedelta(hours=1)
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024
MAX_MEMBERS = 20_000


class ExportDenied(ValueError):
    """Generic denial suitable for a restricted local status surface."""


@dataclass(frozen=True, repr=False)
class ProjectionGrant:
    """Trusted local bootstrap configuration; never deserialize from a request."""

    scope: tuple[tuple[str, str], ...]
    archive_id: str
    snapshot_sha256: str
    role: str = "projection_worker"
    purpose: str = "analytical_project"
    policy_version: str = POLICY_VERSION


class AnalyticalExporter:
    """Provisional local worker. The scoped custody registry owns serving."""

    def __init__(self, ledger: ConnectedIngest, grant: ProjectionGrant):
        if type(ledger) is not ConnectedIngest or type(grant) is not ProjectionGrant:
            raise ExportDenied("Analytical export denied")
        self._ledger = ledger
        self._grant = grant

    def export(
        self,
        snapshot: dict,
        *,
        requested_fields: frozenset[str] = FIELDS,
        status_only: bool = False,
    ) -> dict:
        try:
            granted = self._authorize(snapshot, requested_fields, status_only)
            start = _instant(granted["measurement_start"])
            end = _instant(granted["measurement_end"])
            if not timedelta(0) < end - start <= timedelta(hours=24):
                raise ExportDenied("Analytical export denied")
            if not self._ledger.verify_snapshot(granted):
                raise ExportDenied("Analytical export denied")
            if status_only:
                return {"status": "available"}
            rows, losses = _aggregate(granted, start, end)
        except (KeyError, TypeError, ValueError, ArithmeticError, OSError, RecursionError):
            raise ExportDenied("Analytical export denied") from None
        return {
            "schema_version": "mse.analytics-view/0.1",
            "purpose": "aggregate_hr_sdnn",
            "policy_version": POLICY_VERSION,
            "projection_version": PROJECTION_VERSION,
            "time_basis": "relative_60_minute_bucket",
            "view_id": "av_" + token_hex(16),
            "rows": rows,
            "projection_loss": losses,
        }

    def _authorize(self, snapshot, fields, status_only):
        grant = self._grant
        if (
            grant.role != "projection_worker"
            or grant.purpose != "analytical_project"
            or grant.policy_version != POLICY_VERSION
            or type(fields) is not frozenset
            or fields != FIELDS
            or type(status_only) is not bool
            or type(snapshot) is not dict
            or snapshot.get("snapshot_sha256") != grant.snapshot_sha256
            or snapshot.get("purpose") != "offline_synthetic_replay"
            or snapshot.get("scope") != dict(grant.scope)
            or snapshot.get("scope") != self._ledger.scope.fields()
            or snapshot.get("archive_id") != grant.archive_id
            or grant.archive_id != self._ledger.archive_id
        ):
            raise ExportDenied("Analytical export denied")
        if len(snapshot["observations"]) + len(snapshot["tombstones"]) > MAX_MEMBERS:
            raise ExportDenied("Analytical export denied")
        # Use a bounded detached copy so verification and projection share inputs.
        chunks, size = [], 0
        for chunk in json.JSONEncoder(allow_nan=False).iterencode(snapshot):
            size += len(chunk.encode("utf-8"))
            if size > MAX_SNAPSHOT_BYTES:
                raise ExportDenied("Analytical export denied")
            chunks.append(chunk)
        return json.loads("".join(chunks))


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _aggregate(snapshot: dict, start: datetime, end: datetime) -> tuple[list, list]:
    groups = {}
    losses = {"coverage_unknown"}
    if any(loss["reason"] == "outside_reference_positive_domain"
           for loss in snapshot["losses"]):
        losses.add("some_inputs_excluded")
    for member in snapshot["observations"]:
        item = member["source_revision"]["observation"]
        metric = (item["channel"], item["unit"])
        event = _instant(item["event_start"])
        event_end = _instant(item["event_end"])
        value = Decimal(item["value"])
        if (
            CLASSES.get(metric) != item["epistemic_type"]
            or not start <= event <= event_end <= end
            or event >= end
            or not value.is_finite()
            or value <= 0
        ):
            losses.add("some_inputs_excluded")
            continue
        bucket = (event - start) // HOUR
        if event_end > start + (bucket + 1) * HOUR:
            losses.add("cross_bucket_interval_assigned_by_start")
        groups.setdefault((bucket, *metric), []).append(Fraction(value))

    rows = []
    for (bucket, channel, unit), values in sorted(groups.items()):
        tenths = round(sum(values) * 10 / len(values))
        if len(values) < 3 or tenths <= 0:
            losses.add("some_outputs_suppressed")
            continue
        whole, decimal = divmod(tenths, 10)
        rows.append({
            "bucket_index": bucket,
            "channel": channel,
            "unit": unit,
            "mean_value": f"{whole}.{decimal}",
        })
    if rows:
        losses.update(("relative_time_binning", "value_aggregation_and_rounding"))
    return rows, sorted(losses)
