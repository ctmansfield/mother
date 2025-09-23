#!/usr/bin/env bash
# simple, non-destructive checks
set -euo pipefail
echo "[verify] Ping mother-api..."
curl -s http://localhost:8000/health && echo

echo "[verify] Demo nudge:"
curl -s http://localhost:8000/nudge/demo | python -c 'import sys, json; print(json.load(sys.stdin)["message"])'
