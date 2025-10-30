from __future__ import annotations
import os
import json
import pandas as pd
import numpy as np

from analytics.events.window_builder import build_windows
from analytics.eval.run_mi_te import compute_mi_synergy
from analytics.rules.mine_rules import mine_rules


def test_e2e_parquet_to_rules(tmp_path):
    # Create minimal CGM & treatments
    cgm = pd.DataFrame(
        {
            "ts": pd.date_range("2025-01-01", periods=200, freq="5T", tz="UTC").astype(
                "int64"
            )
            // 1_000_000,
            "sgv": np.concatenate(
                [np.linspace(100, 60, 100), np.linspace(60, 120, 100)]
            ),
        }
    )
    treatments = pd.DataFrame(
        {
            "ts": [cgm["ts"].iloc[10], cgm["ts"].iloc[120]],
            "event": ["Meal", "Meal"],
            "carbs": [20, 15],
            "insulin": [0, 0],
        }
    )

    cgm_p = tmp_path / "cgm.parquet"
    trt_p = tmp_path / "treat.parquet"
    win_p = tmp_path / "win.parquet"
    feat_p = tmp_path / "feat.json"
    rules_p = tmp_path / "rules.json"

    cgm.to_parquet(cgm_p, index=False)
    treatments.to_parquet(trt_p, index=False)

    # windows
    res = build_windows(str(cgm_p), str(trt_p), str(win_p))
    assert res["rows"] > 0

    # MI
    win = pd.read_parquet(win_p)
    tcols = [c for c in win.columns if c.startswith("y_")]
    feat = compute_mi_synergy(win, tcols, k=3, n_boot=20, block=12)
    with open(feat_p, "w") as f:
        json.dump(feat, f)

    # rules
    event = tcols[0]
    cand = [c for c in win.columns if c not in tcols + ["glucose"]][:4]
    n_rules = mine_rules(
        str(win_p),
        event,
        cand,
        str(rules_p),
        topn=3,
        min_support=5,
        min_ppv=0.1,
        n_boot=20,
        block=12,
    )
    assert os.path.exists(rules_p)
    assert n_rules >= 0
