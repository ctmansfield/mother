#!/usr/bin/env python3
import csv
import time
import os
from collections import defaultdict
from datetime import datetime


def load_yaml(path):
    try:
        import yaml

        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def u_local_hour(ts):
    try:
        return datetime.fromtimestamp(int(ts)).hour
    except Exception:
        return 0


def main():
    cfg = (load_yaml("content/vasquez.yaml") or {}).get("vasquez", {})
    half_life = float(cfg.get("half_life_days", 14.0))
    window_days = int(cfg.get("window_days", 30))
    match_window = int(cfg.get("match_window_s", 1800))
    alpha = float(cfg.get("alpha", 1.0))
    beta = float(cfg.get("beta", 3.0))
    min_shows = float(cfg.get("min_shows", 10.0))
    hours_per_day = int(cfg.get("hours_per_day", 6))
    neighbor_pad = int(cfg.get("neighbor_pad", 1))
    fallback_hours = list(cfg.get("fallback_hours", [10, 12, 14, 16, 18, 20]))

    # Load nudges log (ts,arm,reward) with exposures (reward blank) + feedback rows
    path = "out/nudges.csv"
    if not os.path.exists(path):
        print("warn: out/nudges.csv not found; writing fallback windows")
        write_windows({}, hours_per_day, neighbor_pad, fallback_hours)
        return

    exposures = []
    feedback = []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            ts = row.get("ts") or row.get("\ufeffts") or ""
            arm = row.get("arm", "")
            rw = row.get("reward", "")
            if str(rw).strip() == "":
                exposures.append({"ts": int(ts or 0), "arm": arm})
            else:
                try:
                    feedback.append(
                        {"ts": int(ts), "arm": arm, "reward": int(float(rw))}
                    )
                except Exception:
                    pass

    now = int(time.time())
    cutoff = now - window_days * 86400
    exposures = [e for e in exposures if e["ts"] >= cutoff]
    feedback = sorted([f for f in feedback if f["ts"] >= cutoff], key=lambda x: x["ts"])

    # Join: for each exposure, find first feedback for same arm within window
    fb_by_arm = [f for f in feedback]  # already sorted

    def match_reward(exp):
        for fb in fb_by_arm:
            if fb["arm"] != exp["arm"]:
                continue
            if fb["ts"] < exp["ts"]:
                continue
            if fb["ts"] - exp["ts"] <= match_window:
                return fb["reward"]
        return 0

    # Aggregate by category, hour with exponential decay
    def arm_cat(arm):
        parts = (arm or "").split("|")
        return (parts + [None])[-1] or "hydration"

    shows = defaultdict(float)
    acts = defaultdict(float)
    for e in exposures:
        cat = arm_cat(e["arm"])
        hour = u_local_hour(e["ts"])
        if hour < 0 or hour > 23:
            continue
        age_days = (now - e["ts"]) / 86400.0
        w = 0.5 ** (age_days / half_life) if half_life > 0 else 1.0
        shows[(cat, hour)] += w
        r = match_reward(e)
        acts[(cat, hour)] += w * float(r)

    # Build windows
    windows = {"generated_at": datetime.now().isoformat(), "by_category": {}}
    cats = set([k[0] for k in shows.keys()]) | set([k[0] for k in acts.keys()])
    if not cats:
        for c in ["hydration", "movement", "posture", "focus", "sleep"]:
            windows["by_category"][c] = {"hours": fallback_hours}
        return write_windows(windows, hours_per_day, neighbor_pad, fallback_hours)

    for c in ["hydration", "movement", "posture", "focus", "sleep"]:
        scored = []
        for h in range(24):
            s = shows.get((c, h), 0.0)
            a = acts.get((c, h), 0.0)
            ctr = (a + alpha) / (s + alpha + beta)
            scored.append((h, ctr, s))
        # filter if we have too little total shows
        total_s = sum(s for (_, _, s) in scored)
        if total_s < min_shows:
            base = list(fallback_hours)
            windows["by_category"][c] = {"hours": base}
            continue
        # pick top hours_per_day by ctr, then expand with neighbor_pad
        scored.sort(key=lambda t: (t[1], t[2]), reverse=True)
        pick = [h for (h, _, _) in scored[: max(1, hours_per_day)]]
        allowed = set()
        for h in pick:
            for k in range(h - neighbor_pad, h + neighbor_pad + 1):
                allowed.add((k + 24) % 24)
        windows["by_category"][c] = {"hours": sorted(allowed)}

    write_windows(windows, hours_per_day, neighbor_pad, fallback_hours)


def write_windows(windows, k, pad, fb):
    # If windows is empty, craft skeleton
    if not windows:
        windows = {"generated_at": datetime.now().isoformat(), "by_category": {}}
        for c in ["hydration", "movement", "posture", "focus", "sleep"]:
            windows["by_category"][c] = {"hours": fb}
    # Write YAML without requiring PyYAML
    out = ["vasquez_windows:", '  generated_at: "%s"' % windows.get("generated_at", "")]
    out.append("  by_category:")
    for c, meta in (windows.get("by_category") or {}).items():
        hours = meta.get("hours") or fb
        out.append(f"    {c}:")
        out.append("      hours: [" + ",".join(str(int(h)) for h in hours) + "]")
    txt = "\n".join(out) + "\n"
    os.makedirs("content", exist_ok=True)
    with open("content/vasquez_windows.yaml", "w") as f:
        f.write(txt)
    print("wrote content/vasquez_windows.yaml")


if __name__ == "__main__":
    main()
