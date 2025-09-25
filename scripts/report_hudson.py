#!/usr/bin/env python3
import csv
import os
import math
import time
from datetime import datetime

try:
    import yaml
except Exception:
    yaml = None

EXPOSURES = "out/experiments_log.csv"
FEEDBACK = "out/experiments_feedback.csv"
EXPS = "content/experiments.yaml"


def wilson(p, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (p, max(0.0, center - margin), min(1.0, center + margin))


# chi2 criticals for alpha=0.05 and 0.01 up to df=10
CHI2_05 = {
    1: 3.84,
    2: 5.99,
    3: 7.81,
    4: 9.49,
    5: 11.07,
    6: 12.59,
    7: 14.07,
    8: 15.51,
    9: 16.92,
    10: 18.31,
}
CHI2_01 = {
    1: 6.63,
    2: 9.21,
    3: 11.34,
    4: 13.28,
    5: 15.09,
    6: 16.81,
    7: 18.48,
    8: 20.09,
    9: 21.67,
    10: 23.21,
}


def load_yaml(path):
    if yaml is None:
        return None
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def main(incoming="/incoming"):
    # Load config
    cfg = load_yaml(EXPS) or {}
    exps = cfg.get("experiments") or []
    # Load exposures
    exposures = []
    if os.path.exists(EXPOSURES):
        with open(EXPOSURES, "r") as f:
            r = csv.DictReader(f)
            for row in r:
                row["ts"] = int(row["ts"])
                row["p"] = float(row["p"])
                row["threshold"] = float(row["threshold"])
                row["allowed"] = int(row["allowed"])
                exposures.append(row)
    # Load feedback
    fbs = []
    if os.path.exists(FEEDBACK):
        with open(FEEDBACK, "r") as f:
            r = csv.DictReader(f)
            for row in r:
                fbs.append(
                    {
                        "ts": int(row["ts"]),
                        "arm": row["arm"],
                        "reward": int(row["reward"]),
                    }
                )
    # Join nearest-after within 30m
    fbs_sorted = sorted(fbs, key=lambda x: x["ts"])
    window = 1800
    for ex in exposures:
        ex["reward"] = 0
        for fb in fbs_sorted:
            if fb["arm"] != ex["arm"]:
                continue
            if fb["ts"] < ex["ts"]:
                continue
            if fb["ts"] - ex["ts"] <= window:
                ex["reward"] = fb["reward"]
                break
    # Aggregate by exp+variant
    agg = {}
    for ex in exposures:
        key = (ex.get("experiment_id", ""), ex.get("variant", ""))
        a = agg.setdefault(key, {"shows": 0, "acts": 0, "sum_p": 0.0})
        a["shows"] += ex["allowed"]
        a["acts"] += ex["reward"]
        a["sum_p"] += ex["p"]
    # Build report
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"# Hudson Report — {ts}", ""]
    for exp in exps:
        eid = exp.get("id")
        variants = exp.get("variants") or {}
        lines.append(f"## {eid}")
        # Table header
        lines.append("| variant | shows | acts | ctr | 95% CI | avg_p |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        # compute SRM
        total_shows = 0
        obs = {}
        expw = {}
        for vname, meta in variants.items():
            a = agg.get((eid, vname), {"shows": 0, "acts": 0, "sum_p": 0.0})
            shows = a["shows"]
            acts = a["acts"]
            ctr = acts / max(1, shows)
            lo, hi = wilson(ctr, shows)[1:]
            avg_p = a["sum_p"] / max(1, shows)
            lines.append(
                f"| {vname} | {shows} | {acts} | {ctr:.4f} | [{lo:.4f}, {hi:.4f}] | {avg_p:.4f} |"
            )
            obs[vname] = shows
            total_shows += shows
            expw[vname] = float(meta.get("weight", 0.0))
        # SRM only if we have shows
        if total_shows > 0 and len(variants) >= 2:
            wsum = sum(expw.values()) or 1.0
            chi2 = 0.0
            for v in variants:
                expected = total_shows * (expw[v] / wsum)
                if expected > 0:
                    chi2 += (obs[v] - expected) ** 2 / expected
            df = max(1, len(variants) - 1)
            crit05 = CHI2_05.get(df, None)
            crit01 = CHI2_01.get(df, None)
            flag = crit05 is not None and chi2 > crit05
            severity = (
                "FAIL@0.01"
                if (crit01 is not None and chi2 > crit01)
                else ("WARN@0.05" if flag else "OK")
            )
            lines.append("")
            lines.append(f"**SRM**: chi²={chi2:.2f}, df={df} → {severity}")
        # winner suggestion (naive: best CTR with ≥20 shows)
        cand = [(vn, (agg.get((eid, vn), {"shows": 0, "acts": 0}))) for vn in variants]
        cand = [(vn, a) for vn, a in cand if a["shows"] >= 20]
        if cand:
            best = max(cand, key=lambda kv: kv[1]["acts"] / max(1, kv[1]["shows"]))
            bvn, bv = best
            bctr = bv["acts"] / max(1, bv["shows"])
            lines.append(
                f"\n**Pick so far**: `{bvn}` (ctr={bctr:.4f}, shows={bv['shows']})"
            )
        lines.append("\n---\n")
    # write to /incoming
    os.makedirs(incoming, exist_ok=True)
    out = os.path.join(incoming, f"hudson_report_{int(time.time())}.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(out)


if __name__ == "__main__":
    main()
