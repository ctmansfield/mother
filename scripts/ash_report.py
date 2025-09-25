#!/usr/bin/env python3
import yaml
import os
from datetime import datetime


def load_yaml(p):
    try:
        with open(p, "r") as f:
            return yaml.safe_load(f)
    except Exception:
        return {}


def count_rows(path):
    if not os.path.exists(path):
        return 0
    with open(path, "r") as f:
        c = sum(1 for _ in f) - 1
        return max(0, c)


def main():
    tab = load_yaml("content/ash_table.yaml").get("ash_table", {})
    tau = (
        load_yaml("content/ash_tau.yaml").get("ash_tau", {}).get("tau_by_category", {})
    )
    upl = tab.get("uplift", {}) or {}
    gen = tab.get("generated_at", "")
    lines = []
    lines.append(f"# Ash Uplift Report\n\nGenerated: {gen}\n")
    lines.append("## Per-category τ\n")
    for c, v in (tau or {}).items():
        lines.append(f"- **{c}**: τ = {v}")
    lines.append("\n## Top uplift cells (exact keys)\n")
    exact = [(k, v) for k, v in upl.items() if not k.startswith("*")]
    exact.sort(key=lambda kv: kv[1], reverse=True)
    for k, v in exact[:20]:
        lines.append(f"- `{k}` → {v:+.4f}")
    exps = count_rows("out/ash_log.csv")
    pas = count_rows("out/passive_actions.csv")
    lines.append(f"\n_Data: exposures={exps}, passive_actions={pas}_\n")
    outpath = f"/incoming/ash_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    with open(outpath, "w") as f:
        f.write("\n".join(lines) + "\n")
    print({"report": outpath})


if __name__ == "__main__":
    main()
