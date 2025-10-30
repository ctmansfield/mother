#!/usr/bin/env bash
set -euo pipefail
BASE="http://localhost:18081"
echo "[mother/VERIFY] Health check:"
curl -sf "$BASE/healthz" | jq .
echo "[mother/VERIFY] Creating test reminder due in 2 minutes..."
DUE=$(date -u -d "+2 minutes" +"%Y-%m-%dT%H:%M:%SZ")
curl -sf -X POST "$BASE/api/reminders" -H "Content-Type: application/json" -d "{"user_id":"00000000-0000-0000-0000-000000000001","title":"Test Hydrate","note":"8oz","due_at":"$DUE","channel":"email"}" | jq .
echo "[mother/VERIFY] Listing next hour:"
TO=$(date -u -d "+60 minutes" +%FT%TZ)
curl -sf "$BASE/api/reminders?to=${TO}" | jq .
echo "[mother/VERIFY] Predict stub:"
curl -sf -X POST "$BASE/api/models/predict" -H "Content-Type: application/json" -d '{"model":"adherence_risk_v1","features":{"recent_skips":1,"last_streak":2}}' | jq .
echo "[mother/VERIFY] OK"
