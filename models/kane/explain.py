def explain(top_features):
    parts = []
    for k, v in top_features[:3]:
        if k == "hrv_delta_pct":
            parts.append(f"HRV {int(v)}% vs baseline")
        elif k == "inactivity_min":
            parts.append(f"inactivity {int(v)} min")
        elif k == "readiness":
            parts.append(f"readiness {int(v)}")
        else:
            parts.append(f"{k}={v}")
    return "Why now: " + "; ".join(parts)
