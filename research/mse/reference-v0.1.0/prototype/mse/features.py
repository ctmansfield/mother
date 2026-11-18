"""Explicit observed-support integration: never bridge an unsupported gap."""
from __future__ import annotations

import math

from .contracts import ContractError, timestamp


def meal_area(points, *, start, end, baseline, max_gap_seconds=900):
    """Signed and positive incremental area over only supported linear segments.

    points: iterable of (ISO timestamp, scalar). Scalar unit is declared by caller.
    A partial observed area is returned separately; a whole-window area is withheld
    unless every second is supported by a bracketing pair within max_gap_seconds.
    """
    a, b = timestamp(start), timestamp(end)
    if b <= a or not math.isfinite(baseline) or max_gap_seconds <= 0:
        raise ContractError("Invalid integration window or baseline")
    values = sorted((timestamp(t), float(value)) for t, value in points)
    if any(not math.isfinite(v) for _, v in values):
        raise ContractError("Nonfinite area input")
    if len({t for t, _ in values}) != len(values):
        raise ContractError("Duplicate area timestamps need an explicit sensor-selection policy")
    observed_seconds = signed = positive = 0.0
    for (t0, y0), (t1, y1) in zip(values, values[1:]):
        gap = (t1 - t0).total_seconds()
        if gap <= 0 or gap > max_gap_seconds:
            continue
        left, right = max(t0, a), min(t1, b)
        if right <= left:
            continue
        yl = y0 + (y1 - y0) * (left - t0).total_seconds() / gap - baseline
        yr = y0 + (y1 - y0) * (right - t0).total_seconds() / gap - baseline
        dt = (right - left).total_seconds()
        observed_seconds += dt
        signed += (yl + yr) * dt / 120.0
        if yl >= 0 and yr >= 0:
            positive += (yl + yr) * dt / 120.0
        elif yl > 0:
            positive += yl * (dt * yl / (yl - yr)) / 120.0
        elif yr > 0:
            positive += yr * (dt * yr / (yr - yl)) / 120.0
    duration = (b - a).total_seconds()
    complete = abs(observed_seconds - duration) <= 1e-6
    return {"status": "complete_observed_support" if complete else "partial_observed_support",
            "coverage_fraction": observed_seconds / duration,
            "observed_signed_incremental_area": signed,
            "observed_positive_incremental_area": positive,
            "whole_window_signed_incremental_area": signed if complete else None,
            "whole_window_positive_incremental_area": positive if complete else None,
            "unit": "input_scalar_unit * minute", "baseline": baseline,
            "max_gap_seconds": max_gap_seconds,
            "assumption": "Linear between bracketing observations only; no extrapolation or gap filling"}
