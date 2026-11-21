"""Explicit, deliberately small scalar unit vocabulary for qualified adapters."""

import math

GLUCOSE_MMOL_L_TO_MG_DL = 18.01559


def normalize_scalar(channel: str, value, unit: str) -> tuple[float, str]:
    """Normalize known channel/unit pairs; never guess an unreported unit."""
    if isinstance(value, bool):
        raise ValueError("Boolean is not a scalar measurement")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid scalar measurement") from exc
    if not math.isfinite(number):
        raise ValueError("Non-finite scalar measurement")
    aliases = {
        "heart_rate": {
            "count/min": "beats/min",
            "bpm": "beats/min",
            "beats/min": "beats/min",
        },
        "resting_heart_rate": {
            "count/min": "beats/min",
            "bpm": "beats/min",
            "beats/min": "beats/min",
        },
        "respiratory_rate": {"count/min": "breaths/min", "breaths/min": "breaths/min"},
        "hrv_sdnn": {"ms": "ms"},
        "hrv_rmssd": {"ms": "ms"},
        "blood_pressure_systolic": {"mmHg": "mmHg"},
        "blood_pressure_diastolic": {"mmHg": "mmHg"},
        "lactate": {"mmol/L": "mmol/L"},
        "ketone": {"mmol/L": "mmol/L", "ppm": "ppm", "mg/dL": "mg/dL"},
        "oxygen_saturation": {"%": "%"},
        "wrist_temperature": {"degC": "Cel", "°C": "Cel", "Cel": "Cel"},
    }
    if channel == "glucose":
        if unit in ("mg/dL", "mg/dl", "mgdl"):
            return number, "mg/dL"
        if unit in ("mmol/L", "mmol/l", "mmol"):
            return number * GLUCOSE_MMOL_L_TO_MG_DL, "mg/dL"
    elif unit in aliases.get(channel, {}):
        return number, aliases[channel][unit]
    raise ValueError(f"Unsupported unit for channel {channel}")
