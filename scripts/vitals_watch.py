#!/usr/bin/env python3
import csv
import argparse
import json
import subprocess
import sys

try:
    import yaml
except Exception:
    yaml = None


def load_yaml(path):
    if yaml is None:
        return None
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def parse_days(s):
    s = str(s).strip().lower()
    if s.endswith("d"):
        try:
            return int(float(s[:-1]))
        except:
            return 1
    try:
        return int(float(s))
    except:
        return 1


def load_vitals_csv(path):
    rows = []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(
                {
                    "date": row["date"],
                    "resting_hr": float(row.get("resting_hr", "") or 0),
                    "hrv": float(row.get("hrv", "") or 0),
                    "steps": float(row.get("steps", "") or 0),
                    "sleep_min": float(row.get("sleep_min", "") or 0),
                }
            )
    rows.sort(key=lambda x: x["date"])
    return rows


def mean(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else 0.0


def compute_baseline(rows, metric, exclude_last_n=1, window=14):
    if len(rows) <= exclude_last_n:
        return 0.0
    end = len(rows) - exclude_last_n
    start = max(0, end - window)
    vals = [rows[i][metric] for i in range(start, end)]
    return mean(vals)


def eval_cond(value, baseline, cond_str):
    c = cond_str.replace(" ", "")
    try:
        if c.startswith(">baseline+"):
            return value > baseline + float(c.split("+", 1)[1])
        if c.startswith("<baseline*"):
            return value < baseline * float(c.split("*", 1)[1])
        if c.startswith(">baseline*"):
            return value > baseline * float(c.split("*", 1)[1])
        if c.startswith("<baseline-"):
            return value < baseline - float(c.split("-", 1)[1])
    except Exception:
        return False
    return False


def motherctl_select(category, reasons, dry_run=True):
    cmd = [
        "python3",
        "scripts/motherctl.py",
        "select",
        "--category",
        category,
        "--tone",
        "auto",
        "--channel",
        "auto",
    ]
    if reasons:
        cmd += ["--reasons", reasons]
    if dry_run:
        cmd += ["--dry-run"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return json.loads(out.strip())
    except Exception as e:
        return {"allowed": False, "reason": f"motherctl_error:{e}"}


def main():
    ap = argparse.ArgumentParser(
        description="Evaluate vitals against rules and propose guarded actions."
    )
    ap.add_argument("--source", default="data/fixtures/vitals.csv")
    ap.add_argument("--rules", default="content/templates/vitals_rules.yaml")
    ap.add_argument("--window", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rules_yaml = load_yaml(args.rules)
    if not isinstance(rules_yaml, dict) or "rules" not in rules_yaml:
        print(json.dumps({"error": "rules_yaml_invalid"}))
        sys.exit(0)

    rows = load_vitals_csv(args.source)
    if not rows:
        print(json.dumps({"error": "no_vitals"}))
        sys.exit(0)

    latest = rows[-1]
    triggers = []
    for key, rule in (rules_yaml.get("rules") or {}).items():
        metric = rule.get("metric")
        cond = str(rule.get("cond", "")).strip()
        persist_days = parse_days(rule.get("persist", "1d"))
        category = rule.get("category") or "hydration"
        msg = rule.get("msg") or key
        cooldown = rule.get("cooldown", "0h")

        baseline = compute_baseline(
            rows, metric, exclude_last_n=persist_days, window=args.window
        )

        ok = True
        for i in range(1, persist_days + 1):
            if len(rows) - i < 0:
                ok = False
                break
            v = rows[-i][metric]
            if not eval_cond(v, baseline, cond):
                ok = False
                break
        if not ok:
            continue

        reason = f"{metric}={latest[metric]:.1f} vs baseline={baseline:.1f} ({cond})"
        sel = motherctl_select(category, f"{msg}. {reason}", dry_run=args.dry_run)
        triggers.append(
            {
                "rule": key,
                "tier": rule.get("tier", "INFO"),
                "category": category,
                "message": msg,
                "reason": reason,
                "cooldown": cooldown,
                "selection": sel,
            }
        )

    print(
        json.dumps(
            {"date": latest["date"], "triggers": triggers, "count": len(triggers)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
