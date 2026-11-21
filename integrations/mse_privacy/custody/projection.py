"""Allowlist the provisional ATLAS analytical 0.1 envelope on write and read."""

import re

PURPOSE = "aggregate_hr_sdnn"
POLICY = "synthetic-aggregate-hr-sdnn/0.1"
HEADER = {
    "schema_version": "mse.analytics-view/0.1",
    "purpose": PURPOSE,
    "policy_version": POLICY,
    "projection_version": "relative-hour-mean/0.1",
    "time_basis": "relative_60_minute_bucket",
}
UNITS = {"heart_rate": "bpm", "hrv_sdnn": "ms"}
ROW_FIELDS = {"bucket_index", "channel", "unit", "mean_value"}
LOSS_CODES = {
    "coverage_unknown",
    "cross_bucket_interval_assigned_by_start",
    "relative_time_binning",
    "some_inputs_excluded",
    "some_outputs_suppressed",
    "value_aggregation_and_rounding",
}
POPULATED_LOSSES = {"relative_time_binning", "value_aggregation_and_rounding"}
MEAN = re.compile(r"(?:0\.[1-9]|[1-9][0-9]*\.[0-9])")


def validate_projection(payload, *, view_id, grant):
    def invalid():
        return ValueError("Invalid analytical projection")

    if (
        type(payload) is not dict
        or set(payload) != set(HEADER) | {"view_id", "rows", "projection_loss"}
        or any(payload[field] != value for field, value in HEADER.items())
        or payload["view_id"] != view_id
        or grant.purpose != PURPOSE
        or grant.policy_version != POLICY
    ):
        raise invalid()
    rows, losses = payload["rows"], payload["projection_loss"]
    if (
        type(rows) is not list
        or len(rows) > 48
        or type(losses) is not list
        or len(losses) > len(LOSS_CODES)
        or any(type(code) is not str or code not in LOSS_CODES for code in losses)
        or losses != sorted(set(losses))
        or not (
            POPULATED_LOSSES <= set(losses) if rows else "coverage_unknown" in losses
        )
    ):
        raise invalid()
    approved = []
    for row in rows:
        if type(row) is not dict or set(row) != ROW_FIELDS:
            raise invalid()
        bucket, channel, unit, value = (
            row["bucket_index"],
            row["channel"],
            row["unit"],
            row["mean_value"],
        )
        if (
            type(bucket) is not int
            or not 0 <= bucket <= 23
            or type(channel) is not str
            or type(unit) is not str
            or UNITS.get(channel) != unit
            or type(value) is not str
            or len(value) > 512
            or not MEAN.fullmatch(value)
        ):
            raise invalid()
        approved.append(
            dict(bucket_index=bucket, channel=channel, unit=unit, mean_value=value)
        )
    keys = [(row["bucket_index"], row["channel"]) for row in approved]
    if keys != sorted(set(keys)):
        raise invalid()
    return {
        **HEADER,
        "view_id": view_id,
        "rows": approved,
        "projection_loss": list(losses),
    }
