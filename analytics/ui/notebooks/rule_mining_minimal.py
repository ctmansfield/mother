# Converted from minimal notebook to script to satisfy pre-commit hooks
import os
import json
import pandas as pd
from itertools import combinations

WINDOWS = "storage/analytics/windows.parquet"
OUT_RULES = "analytics/rules/rules.json"
EVENT = "y_night_hypo_60m"
CANDIDATES = ["cgm_delta_10", "minutes_since_meal", "cgm_delta_30", "slope_15"]

assert os.path.exists(WINDOWS), WINDOWS
win = pd.read_parquet(WINDOWS)
win = win.dropna(subset=CANDIDATES + [EVENT])


def ppv(y_true, y_pred):
    tp = ((y_true == 1) & (y_pred == 1)).sum()
    fp = ((y_true == 0) & (y_pred == 1)).sum()
    return tp / (tp + fp) if (tp + fp) > 0 else 0.0


results = []
for f1, f2 in combinations(CANDIDATES, 2):
    q1 = win[f1].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
    q2 = win[f2].quantile([0.1, 0.25, 0.5, 0.75, 0.9]).values
    for t1 in q1:
        for t2 in q2:
            pred1 = ((win[f1] <= t1) & (win[f2] >= t2)).astype(int)
            pred2 = ((win[f1] >= t1) & (win[f2] <= t2)).astype(int)
            ppv1 = ppv(win[EVENT], pred1)
            ppv2 = ppv(win[EVENT], pred2)
            results.append(
                {
                    "features": [f1, f2],
                    "ops": ["<=", ">="],
                    "values": [float(t1), float(t2)],
                    "ppv": float(ppv1),
                }
            )
            results.append(
                {
                    "features": [f1, f2],
                    "ops": [">=", "<="],
                    "values": [float(t1), float(t2)],
                    "ppv": float(ppv2),
                }
            )

res_sorted = sorted(results, key=lambda x: -x["ppv"])[:5]
rules = []
for i, r in enumerate(res_sorted, start=1):
    if r["ppv"] <= 0:
        continue
    feats = r["features"]
    ops = r["ops"]
    vals = r["values"]
    rules.append(
        {
            "id": f"rule_{i:03d}",
            "event": "night_hypo_60m",
            "if_all": [
                {"feature": feats[0], "op": ops[0], "value": vals[0]},
                {"feature": feats[1], "op": ops[1], "value": vals[1]},
            ],
            "action": "slow_carb_protein_snack",
            "metadata": {"ppv": r["ppv"]},
        }
    )

os.makedirs(os.path.dirname(OUT_RULES) or ".", exist_ok=True)
with open(OUT_RULES, "w") as f:
    json.dump({"rules": rules}, f, indent=2)
print(f"Wrote {len(rules)} rules to {OUT_RULES}")
