# Behavioral episodic continuity — source-only v0.1

A deterministic, CPU-only continuation to the 24-case Behavioral COACH screen. It implements an append-only hash-chained event ledger for **four synthetic episode patterns**, without executing interventions or drawing clinical conclusions.

## Four required episodes

1. Acknowledgment, action and matching measured host response (may be synthesized from event records; never inferred from acknowledgment alone).
2. Behavioral change with **no physiological change**.
3. Physiological change with **no behavioral change**.
4. Prediction failure with linked observation, provisional lesson and successor-model continuity.

The event schema preserves `observed_at`, `available_at`, and `recorded_at`. Late-arriving values cannot be used in forecasts predating availability. Behavior and physiology have separate measurement types, metrics and before/after states. The lesson's only permitted status is `UNVERIFIED_EXPERIENCE`, not scientific fact. Model replacement requires exact predecessor/successor lineage; episodes and failure histories are never deleted.

The code does **not** automatically generate behavior advice or predictions and does not assign models or register memory in production. It uses only synthetic fixtures in tests. Hashes detect accidental tampering but do not establish author identity, trust, secure timestamps or independent evaluation. A real deployment needs authenticated writers, authorization, storage policy, concurrency controls across hosts, restart tests, privacy review and clinician/scientific validation where relevant.

## Offline verification

```bash
cd docs/reviews/gpu-round-20261120/behavior/episodes
sha256sum -c SHA256SUMS
python3 -B -m unittest -v test_episodes
```

These commands make zero network/GPU/model calls and do not alter running services.

## Release notes and follow-on tests

- Added typed, independently measured behavior and physiology.
- Added prediction target/availability binding and explicit outcome-error verification.
- Added two independently linked gates for lessons: historical prediction and measured discrepancy.
- Added successor-model version lineage without erasing failed predictions.
- Added seventeen offline regression cases, all self-contained and fictional.
- Next: four scripted complete episode fixtures, process-restart/recovery and independent reviewer adjudication, then role-based GPU evaluation **only after** the ongoing scientific Protocol B work has finished and been reviewed.

GitHub drafts are source-only. Do not merge or deploy from a passing synthetic test alone.
