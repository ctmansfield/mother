# ΦID Analytics Platform — System Architecture & Implementation Plan (adapted for this repo)

Purpose
- Add an information-theoretic analytics layer (MI/TE + PID/ΦID) to discover unique, redundant, and synergistic predictors of clinically relevant events (e.g., nocturnal lows, adrenergic surges, BP spikes), and to prioritize interventions (diet timing, meds, electrolytes) using your personal portal + genomics data.

Repo alignment
- We will use the existing FastAPI service in mother_app as the runtime host for rule-based, near-real-time risk scoring (/risk/score) and explain endpoints.
- We will use the existing scripts/ and storage/ patterns for ingestion helpers and simple feature-store concepts.
- We will add a new analytics/ subtree for offline pipelines, MI/TE/PID/ΦID, rule mining, evaluation, and service glue. Offline results (e.g., rules.json, feature ranks) are read by mother_app at runtime.
- We will integrate Nightscout as a primary data source for CGM via a new adapter (analytics/preprocess/sources/nightscout_adapter.py), pulling data from your existing Nightscout installation.

Outcomes
- Event-risk models that explain what matters (unique) and what only matters in combination (synergy).
- Actionable rules for alerts and protocols (e.g., “CGM ↓10 mg/dL/10 min AND HRV ↓15% AND >3h since last snack → high-risk in next 30–60 min”).
- Feature triage for product UI (drop redundant sensors, surface unique/synergistic combos).

1) Monorepo Layout (added in this repo)
- analytics/
  - phiid_core/           # estimators, PID/ΦID decomposition, TE, MI (Python)
  - preprocess/           # ingestion, alignment, resampling, feature-engineering
    - sources/nightscout_adapter.py   # Nightscout ingestion
  - events/               # event labeling (hypo, surge, bp spike), windows
  - models/               # risk models, calibration, SHAP-like explanations
  - rules/                # rule generator + runtime rule application
  - eval/                 # offline evaluation, ablation, bootstrap
  - services/             # batch & integration glue (used by mother_app)
  - ui/                   # JSON schemas for cards/widgets + example notebooks
  - genomics/             # variant ingestion, feature joiners, GxE synergy tests
  - config/               # YAML for data sources, windows, lags, thresholds
  - tests/                # unit/integration tests
- docs/phiid-analytics/ARCHITECTURE.md    # this file

2) Data Contracts
Signals (time series, 1–5 min bins)
- CGM (glucose, rate of change, arrows via Nightscout), meals (macros), electrolytes intake, meds timestamps (tadalafil, clonidine, etc.), symptoms (MCAS markers), sleep (stages), HR/HRV, BP, activity, temp/environment.

Static / Slow-varying covariates
- Genotype: MTHFR rs1801133, MTRR rs1801394, FUT2 rs602662, CYPs (if available).
- Demographics, diagnoses (MCAS, A3 inflammatory score if available), baseline labs.

Events (labels)
- night_hypo (<70 mg/dL or urgent-low-soon), adrenergic_surge (symptom tap or Physio pattern), bp_spike (e.g., SBP>140 + delta threshold).
- Windows: predictive horizon H = 30–60 min, context lags L = 15–180 min.

Storage
- Columnar (Parquet) under storage/analytics/*.parquet. Tables: timeseries, events, intake, genotypes, windows.
- Schema example (Parquet/Arrow):
  - timeseries(user_id, ts, signal, value)
  - events(user_id, t_start, t_end, event_type, metadata)
  - intake(user_id, ts, type, amount, units, macro_json)
  - genotypes(user_id, rsid, genotype, effect)
  - windows(user_id, t0, horizon_min, y_event, features_json)

3) Preprocessing Pipeline
Goals: align heterogeneous streams, generate lagged features, ensure stationarity for information estimators.

Steps
- Ingest sources → standardize to UTC, de-duplicate, quality flags.
- Resample to 5-min bins (configurable), forward-fill limited signals with max gap rules.
- Feature engineering:
  - CGM deltas: Δ10 min, Δ30 min; rolling slope; % time <70 in last 2–4 h.
  - HRV metrics (RMSSD, pNN50) lagged 15, 30, 60 min.
  - Meal features: grams carbs, protein, fat; GI class; “minutes since meal/snack.”
  - Electrolytes: rolling Na/K/Mg intake in past 6–12 h.
  - Sleep: binary asleep; stage if available; “minutes since sleep onset.”
  - Med impulses: one-hot impulses with decay kernels (e.g., tadalafil half-life param).
- Windows & labels: For each index time t0, compute y_event if event begins in (t0, t0+H]. Serialize feature vectors & lags to windows.

Config example (analytics/config/pipeline.yaml)
- resample_minutes: 5
- horizon_minutes: [30, 60]
- lags_minutes: [15, 30, 60, 120, 180]
- cgm_features: [delta_10, delta_30, slope_15, slope_30]
- hrv_features: [rmssd_lag15, rmssd_lag30]
- meal_features: [carb_g, protein_g, fat_g, minutes_since_meal]
- electrolytes: [na_mEq_6h, k_mEq_6h, mg_mg_12h]
- meds_decay:
  - tadalafil: {half_life_h: 17.5}
  - clonidine: {half_life_h: 12, note: "safety flag if used < snack"}

Nightscout integration
- Adapter analytics/preprocess/sources/nightscout_adapter.py pulls CGM data from your existing Nightscout instance via REST:
  - Entries: /api/v1/entries/sgv.json?find[dateString][$gte]=ISO8601&count=N
  - Treatments: /api/v1/treatments.json (meals/boluses/notes)
- Configure via env or analytics/config/sources.yaml: NIGHTSCOUT_URL, NIGHTSCOUT_API_SECRET.

4) Core Analytics (MI/TE → PID/ΦID)
Estimators (continuous)
- MI: Kraskov k-NN (bias-resistant)
- TE: k-NN TE for directed influence (X_{t−lag} → Y_t)
- PID: Williams/Beer lattice or BROJA-like estimators for unique, redundant, synergistic info
- ΦID: time-lagged multi-variate extension decomposing storage, transfer, modification into redundant/unique/synergistic parts

Library stack (Python)
- numpy, scipy, numba
- pyitlib (MI, conditional MI)
- dit (PID primitives)
- IDTxl or JIDT (TE) — JIDT via jpype if needed
- Optional: scikit-learn, xgboost (baseline predictive model for comparison)

API sketch (analytics/phiid_core/api.py)
- class InfoDecomposition
  - mi(self, X, Y) -> float
  - cmi(self, X, Y, Z) -> float
  - te(self, X_lagged, Y) -> float
  - pid(self, sources: dict, target) -> dict
  - phiid(self, sources: dict, target, lags: dict) -> dict

Outputs we persist
- feature_rank_unique: features with highest unique info for each event
- synergy_sets: minimal sets (size 2–3) with significant synergistic info
- redundant_groups: clusters of interchangeable features (candidate drops)

Statistical rigor
- Block bootstrap (time-aware) for CIs
- Permutation tests for synergy significance (preserving autocorrelation)
- Sliding windows (e.g., 7–14 days) to handle non-stationarity

5) Rule Generation (from synergy → actionable logic)
Goal: convert synergy sets into human-readable, testable rules.
Example
- If [CGM_delta_10 <= -10 mg/dL] AND [HRV_RMSSD_lag15 <= -15% baseline] AND [minutes_since_meal >= 180] THEN risk(night_hypo_60min) = HIGH

Implementation
- Discretize contributing features with optimal cut-points (MDL or decision stump)
- Evaluate candidate rules on validation folds; keep those with stable PPV/NPV across bootstraps
- Serialize as JSON rules for the app (analytics/rules/rules.json)

Runtime application
- mother_app exposes POST /risk/score to apply offline rules.json to live features/context. The initial implementation uses a lightweight evaluator (analytics/rules/apply.py) so we do not bring heavy dependencies into the API process.

6) Services & Jobs
Batch (offline)
- Build windows → run MI/TE → PID/ΦID → emit feature_rank_unique, synergy_sets, rules.json
- Orchestrate via scripts/ or a simple cron (later Airflow/Celery)

Streaming (near-real-time)
- mother_app FastAPI endpoint consumes latest 30–180 min context, applies rules.json, returns risk state + recommendation
- No heavy estimation online; decomposition stays offline

Endpoints (in mother_app)
- POST /risk/score   body: { user_id, t0, current_features }   resp: { risk_scores: {...}, triggered_rules: [...], suggestions: [...] }
- GET /explain/feature-importance?event=night_hypo_60m   resp: { unique_rank: [...], synergy_sets: [...] }

7) Privacy, Security, Compliance
- PHI under HIPAA: encrypt at rest (KMS) + in transit (TLS)
- Pseudonymize user_id in analytics tables; keep key in secure vault
- Access-controlled S3/GCS buckets or on-prem equivalent
- Audit logs for data access
- Genomics: consent storage, data minimization, variant subset only used for modeling

8) Evaluation Plan
Offline metrics
- Event detection: AUC-PR, sensitivity@fixed-FPR, calibration (Brier)
- Ablation: compare baseline model vs model with synergy features vs rule-only system
- Stability: bootstrap CI for synergy sets/rules; drift detection over weeks

Online/prospective
- Track: time-below-range, surge frequency, nocturnal alerts avoided, user interventions accepted
- A/B or pre/post where ethical

9) Roadmap & TODO (mapped to this repo)
Phase 0 — Scaffolding (Week 1–2)
- [x] Create folders, config YAMLs, data contracts
- [x] Nightscout IO adapter skeleton
- [x] Simple windows builder (placeholder)

Phase 1 — Baselines (Week 2–4)
- Implement MI (Kraskov) + TE (IDTxl/JIDT) with tests
- First pass feature ranking to event labels; notebook in analytics/ui

Phase 2 — PID/ΦID Core (Week 4–6)
- PID primitives using dit; lattice verification on toy data
- ΦID time-lag API and unit tests on synthetic VAR processes
- Sliding-window decomposition; bootstrap CIs

Phase 3 — Rule Mining (Week 6–7)
- Discretization, candidate rule induction from synergy sets
- Rule scoring & pruning; serialize rules.json
- Notebook: “Top synergy rules and their PPV/CI.”

Phase 4 — Service Layer (Week 7–8)
- mother_app /risk/score applies rules.json
- Integration test with UI; JSON schema for cards

Phase 5 — Genomics (Week 8–10)
- Ingest selected variants
- G×E synergy tests (variant × diet/electrolytes)
- Privacy review & consent checkpoint

Phase 6 — Evaluation & Docs (Week 10–12)
- Offline eval suite, ablation plots
- User-facing “why this alert” explainers
- Finalize docs

Stretch
- Active learning: suggest which data to collect to reduce uncertainty
- On-device lightweight risk inference (TinyML rules)

10) Testing Strategy
- Unit tests: estimators on known distributions (Gaussian MI ground truth; TE on synthetic)
- Property tests: permutation destroys synergy signal; bootstraps give stable CIs
- Integration: end-to-end from Nightscout + other streams → rules.json → /risk/score

11) Developer Notes
- Use analytics/environment.yml for offline work (conda/uv/venv)
- Deterministic seeds; log estimator params (k, bins, lags)
- Profiles: “dev” (small sample), “prod” (full rolling windows)
- Notebooks in analytics/ui/notebooks/ for exploratory runs

12) Example Pseudocode (window → ΦID → rules)
- windows_df: (t0, horizon, y_event, features...)
- X_sources = {
    "cgm_delta_10": windows_df["cgm_delta_10"].values,
    "rmssd_lag15": windows_df["rmssd_lag15_pct"].values,
    "minutes_since_meal": windows_df["minutes_since_meal"].values
  }
- Y = windows_df["y_night_hypo_60m"].values
- phi = InfoDecomposition()
- pid_res = phi.pid(X_sources, Y)
- phiid_res = phi.phiid(X_sources, Y, lags={"cgm_delta_10":10, "rmssd_lag15":15})
- synergy_sets = select_significant_synergy(pid_res, alpha=0.05)
- rules = discretize_and_score_rules(synergy_sets, X_sources, Y)
- save_json(rules, "analytics/rules/rules.json")

13) UX/Explainability Contracts
Explain card JSON (delivered with an alert)
- {
  "event": "night_hypo_60m",
  "risk": "high",
  "why": {"unique_top": ["minutes_since_meal", "cgm_delta_10"], "synergy": [["cgm_delta_10", "rmssd_lag15"]]},
  "suggested_action": "slow_carb_protein_snack",
  "confidence": 0.78
}

14) Risks & Mitigations
- Non-stationarity → sliding window analytics; weekly rule refresh
- Data sparsity → start with limited feature set; aggregate across days; regularization
- Estimator bias → use multiple estimators; sanity tests on synthetic data
- Privacy → strictly minimal genotype set; isolate PII

15) Open Questions (to resolve in implementation)
- Which event horizons (30 vs 60 min) yield practical lead time without false alarms?
- How often to refresh rules (nightly vs weekly) given drift?
- Thresholds for user action fatigue (alert throttling)
- Governance: process for promoting new rules to production

Nightscout setup notes
- Set env vars in your shell or .env:
  - NIGHTSCOUT_URL=https://<your>.herokuapp.com (or your host)
  - NIGHTSCOUT_API_SECRET=<api-secret or token>
- The adapter supports date ranges and incremental sync; output Parquet is written to storage/analytics/cgm.parquet (and treatments to storage/analytics/treatments.parquet).

DONE means
- Pipelines reproducible end-to-end on a 2–3 week personal dataset
- rules.json and /risk/score API produce consistent, explainable decisions
- Evaluation notebook shows synergy adds value over single-feature alerts
