Offline-to-online flow
- Run analytics/preprocess/sources/nightscout_adapter.py (or your orchestrator) to sync CGM/treatments to storage/analytics.
- Build windows and run analytics to produce analytics/rules/rules.json and analytics/eval/feature_importance.json.
- Start mother_app (uvicorn) with AN_RULES_PATH=analytics/rules/rules.json.
- Use POST /risk/score to apply rules to current features.
