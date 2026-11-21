"""Exact-decimal accounting for the auxiliary PF-001 binary64 projection."""

from __future__ import annotations

from decimal import Decimal
from math import isfinite


def project_binary64(lexeme: str) -> tuple[float | None, str | None]:
    """Project a validated decimal, describing rounding or unusable output."""
    exact = Decimal(lexeme)
    projected = float(exact)
    if not isfinite(projected) or (projected == 0 and exact != 0):
        return None, "pf001_binary64_out_of_range"
    if Decimal.from_float(projected) != exact:
        return projected, "pf001_binary64_rounding"
    return projected, None
