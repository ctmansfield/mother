"""Aggregate analytical output from a restricted local synthetic snapshot."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction
import json

from integrations.mse_ingest.connected import ConnectedIngest
from integrations.mse_privacy.custody import Custody

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
class ProjectionBinding:
    """Trusted workflow selection; never deserialize this from a reader request."""

    scope: tuple[tuple[str, str], ...]
    archive_id: str
    snapshot_sha256: str
    recipient: str
    generation: int


class AnalyticalExporter:
    """Publish an aggregate only after opening a genuine scoped grant."""

    def __init__(self, custody: Custody, open_ledger, binding: ProjectionBinding):
        if type(custody) is not Custody or type(binding) is not ProjectionBinding:
            raise ExportDenied("Analytical export denied")
        self._custody = custody
        self._open_ledger = open_ledger
        self._binding = binding

    def export(
        self,
        credential: str,
        load_snapshot,
        *,
        requested_fields: frozenset[str] = FIELDS,
        status_only: bool = False,
    ) -> dict:
        """Use trusted deferred loaders and return only a published handle or status."""
        try:
            if (
                type(requested_fields) is not frozenset
                or requested_fields != FIELDS
                or type(status_only) is not bool
            ):
                raise ExportDenied("Analytical export denied")
            # Do not open or parse any restricted input before authenticating.
            self._authorize(credential)
            view_id = None
            if not status_only:
                view_id = self._custody.issue_view(credential)
                self._authorize(credential, view_id)
            snapshot = self._snapshot(load_snapshot())
            start = _instant(snapshot["measurement_start"])
            end = _instant(snapshot["measurement_end"])
            if not timedelta(0) < end - start <= timedelta(hours=24):
                raise ExportDenied("Analytical export denied")
            ledger = self._open_ledger()
            if (
                type(ledger) is not ConnectedIngest
                or snapshot["scope"] != ledger.scope.fields()
                or snapshot["archive_id"] != ledger.archive_id
                or not ledger.verify_snapshot(snapshot)
            ):
                raise ExportDenied("Analytical export denied")
            if status_only:
                self._authorize(credential)
                return {"status": "available"}
            rows, losses = _aggregate(snapshot, start, end)
            self._authorize(credential, view_id)
            self._custody.put_projection(credential, view_id, {
                "schema_version": "mse.analytics-view/0.1",
                "purpose": "aggregate_hr_sdnn",
                "policy_version": POLICY_VERSION,
                "projection_version": PROJECTION_VERSION,
                "time_basis": "relative_60_minute_bucket",
                "view_id": view_id,
                "rows": rows,
                "projection_loss": losses,
            })
        except Exception:
            # Restricted loaders and validators can raise value-bearing errors.
            raise ExportDenied("Analytical export denied") from None
        return {"view_id": view_id}

    def _authorize(self, credential: str, view_id: str | None = None) -> None:
        decision = self._custody.authorize_projection(credential, view_id)
        binding = self._binding
        if (
            decision["scope"] != dict(binding.scope)
            or decision["purpose"] != "aggregate_hr_sdnn"
            or decision["policy_version"] != POLICY_VERSION
            or decision["recipient"] != binding.recipient
            or decision["generation"] != binding.generation
        ):
            raise ExportDenied("Analytical export denied")

    def _snapshot(self, snapshot: dict) -> dict:
        binding = self._binding
        if (
            type(snapshot) is not dict
            or snapshot.get("snapshot_sha256") != binding.snapshot_sha256
            or snapshot.get("purpose") != "offline_synthetic_replay"
            or snapshot.get("scope") != dict(binding.scope)
            or snapshot.get("archive_id") != binding.archive_id
            or len(snapshot["observations"]) + len(snapshot["tombstones"]) > MAX_MEMBERS
        ):
            raise ExportDenied("Analytical export denied")
        # Verify and aggregate the same detached snapshot, within a byte ceiling.
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
