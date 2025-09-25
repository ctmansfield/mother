#!/usr/bin/env bash
python3 -V >/dev/null 2>&1 || { echo 'Python3 required'; exit 0; }
[ -d .venv ] || python3 -m venv .venv || true
. .venv/bin/activate 2>/dev/null || true
pip install --upgrade pip >/dev/null 2>&1 || true
echo 'Installed venv (if available).'
