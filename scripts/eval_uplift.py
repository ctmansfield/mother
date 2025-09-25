#!/usr/bin/env python3
import csv


def load_exposures(path="out/ash_log.csv"):
    rows = []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            row["ts"] = int(row["ts"])
            row["treatment"] = int(row["treatment"])
            row["p"] = float(row.get("p", 0.0) or 0.0)
            rows.append(row)
    return rows


def load_feedback(path="out/nudges.csv"):
    fbs = []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            if str(row.get("reward", "")).strip() == "":
                continue
            fbs.append(
                {"ts": int(row["ts"]), "arm": row["arm"], "reward": int(row["reward"])}
            )
    fbs.sort(key=lambda x: x["ts"])
    return fbs


def join_reward(exp, fbs, window=1800):
    for fb in fbs:
        if fb["arm"] != exp["arm"]:
            continue
        if fb["ts"] < exp["ts"]:
            continue
        if fb["ts"] - exp["ts"] <= window:
            return fb["reward"]
    return 0


def main():
    exps = load_exposures()
    fbs = load_feedback() if exps else []
    win = 1800
    data = []
    for e in exps:
        r = join_reward(e, fbs, win) if e["treatment"] == 1 else 0
        data.append(
            (
                e["treatment"],
                r,
                e.get("category", ""),
                e.get("daypart", ""),
                e.get("tone", ""),
                e.get("channel", ""),
            )
        )
    # simple overall uplift
    t_shows = sum(1 for t, _, *__ in data if t == 1)
    c_shows = sum(1 for t, _, *__ in data if t == 0)
    t_acts = sum(r for t, r, *__ in data if t == 1)
    c_acts = sum(r for t, r, *__ in data if t == 0)
    rt = t_acts / max(1, t_shows)
    rc = c_acts / max(1, c_shows)
    print(
        f"overall_treatment_ctr={rt:.4f}, control_ctr={rc:.4f}, uplift={rt-rc:.4f}, shows_t={t_shows}, shows_c={c_shows}"
    )


if __name__ == "__main__":
    main()
