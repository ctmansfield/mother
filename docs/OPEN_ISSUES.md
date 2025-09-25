# Open Issues & Follow-ups

# Open Issues

<!-- HUDSON_FOLLOWUPS_20250924_215301 -->
## Hudson follow-ups
- [ ] **Traffic ramp helper**: auto-increase `traffic` daily (env override + dry-run mode)
- [ ] **HTML report**: pretty `/incoming` report with sparkline CTRs
- [ ] **Strict schema validation**: enforce schema for `experiments.yaml` (CI gate)
- [ ] **SRM guard**: chi² SRM check on every run; auto kill-switch (`active:false`) on FAIL@0.01 with override
- [ ] **Daily rollups**: cron job to aggregate 1/7/28-day CTR; smooth with Wilson shrinkage
- [ ] **Join hygiene**: propagate `impression_id` to `out/nudges.csv` for exact joins

### Notes
- Keep `--exp-off` path working even when experiments are active.
- Consider per-category traffic ramps (e.g., movement 100%, hydration 25%).

## Passive Actions
- Wire Apple Health/Google Fit exports into scripts/ingest_passive.py (CSV schedule).
- Add smart-bottle webhook → local CSV writer.
- Add OS Focus/DND listener → CSV (category=focus).

## Ash (Uplift)
- Evaluate per-category τ stability weekly (scripts/ash_autotune.py).
- Add uplift curves and gains chart to report.
- Consider richer features (recent HRV/RHR state) for uplift table.

## Bishop (Contextual)
- Tune epsilon and learning rate via online eval.
- Add L2 regularization and per-feature caps.
- Option: LinUCB or Thompson when numpy allowed.

## Bishop Advanced
- Add per-arm cold-start priors configurable via YAML.
- Compare contextual (logistic), LinUCB, Thompson offline using synthetic replays.
- Optional numpy fast-paths when available.

## Passive Bus
- Add auth token and local TLS option.
- Add file-watcher tailer to ingest exported CSVs automatically.
