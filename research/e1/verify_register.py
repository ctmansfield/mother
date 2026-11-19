#!/usr/bin/env python3
"""Structural verifier for the E1 bibliography. Scientific validity is not tested."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parent
data = json.loads((root / "REFERENCE_REGISTER.json").read_text(encoding="utf-8"))
with (root / "REFERENCE_REGISTER.csv").open(newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
references = data["records"]
keys = [r["key"] for r in references]
assert len(keys) == len(set(keys)), "Duplicate canonical source keys"
assert len(rows) == len(references), "CSV/JSON row-count mismatch"
assert {r["key"] for r in rows} == set(keys), "CSV/JSON key set mismatch"
assert all(r["doi"] == r["key"][4:] and r["url"] == "https://doi.org/" + r["doi"]
           for r in references if r["doi"]), "DOI key/URL mismatch"
counts = data["source_counts"]
assert counts["unique_source_records"] == len(references), "Record-count mismatch"
assert counts["unique_dois"] == sum(bool(r["doi"]) for r in references), "DOI-count mismatch"
aliases = {a for r in references for a in r["legacy_ids"]}
for prefix, count, pad in [("D:S", 72, 2), ("W:R", 70, 2), ("DRAFT02:", 27, 0),
                           ("MSE:S", 17, 0), ("MSE-SEED:", 7, 0)]:
    for i in range(1, count + 1):
        alias = prefix + (str(i).zfill(pad) if pad else str(i))
        assert alias in aliases or any(a.startswith(alias + "/") for a in aliases), (
            "Missing original bibliography alias " + alias
        )
actual_scout = sum(len(r["discoveries"]) for r in references)
assert counts["scout_doi_entries"] == actual_scout, "Scout attribution-count mismatch"
for prior, published in data["predecessor_doi_to_published_doi"].items():
    target = next((r for r in references if r["doi"] == published), None)
    assert target is not None and ("PREPRINT-DOI:" + prior) in target["legacy_ids"], (
        "Missing linked preprint predecessor " + prior
    )
print("PASS: {} unique sources; {} DOI sources; {} Scout attributions; 5 legacy registers reconciled".format(
    len(references), counts["unique_dois"], actual_scout
))
