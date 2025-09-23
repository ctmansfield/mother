#!/usr/bin/env bash
# safe install: no shell exits, no session closing
set -u
echo "[mother] creating .env.example"
cat > .env.example <<'EOF'
# replace LLM host with your main box LAN IP
MOTHER_MODEL_ENDPOINT=http://192.168.1.50:11434/v1
MOTHER_DB_DSN=postgresql://mother:motherpass@192.168.1.225:55432/mother
MOTHER_API_URL=http://localhost:8000
EOF
echo "[mother] copy .env.example to .env and edit values if needed."
