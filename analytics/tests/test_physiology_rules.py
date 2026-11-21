import json

import pandas as pd

from analytics.rules.mine_rules import mine_rules


def test_default_miner_without_optional_feature_file_writes_discovery_only_rules(
    tmp_path,
):
    path, output = tmp_path / "windows.parquet", tmp_path / "rules.json"
    pd.DataFrame(
        {
            "a": [1.0, 2.0, 3.0, 4.0],
            "b": [4.0, 3.0, 2.0, 1.0],
            "y_test": pd.Series([0, 1, 1, pd.NA], dtype="Int8"),
        }
    ).to_parquet(path, index=False)
    count = mine_rules(
        str(path),
        "y_test",
        ["a", "b"],
        str(output),
        min_support=1,
        min_ppv=0,
        enable_triads=False,
        n_boot=5,
    )
    result = json.loads(output.read_text())
    assert count == len(result["rules"]) > 0
    assert result["evaluation"]["scope"] == "discovery_only"
    assert result["evaluation"]["held_out_evaluation"] is None
    for rule in result["rules"]:
        assert rule["metadata"]["evaluation_scope"] == "discovery_only"
        assert rule["metadata"]["held_out_evaluation"] is None
        assert rule["metadata"]["support"] <= 3


def test_no_rules_still_produces_valid_json_without_optional_import(tmp_path):
    path, output = tmp_path / "windows.parquet", tmp_path / "rules.json"
    pd.DataFrame({"a": [1.0], "b": [4.0], "y_test": [0]}).to_parquet(path, index=False)
    count = mine_rules(str(path), "y_test", ["a", "b"], str(output), min_support=20)
    assert count == 0
    assert json.loads(output.read_text())["rules"] == []
