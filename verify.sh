#!/usr/bin/env bash
. .venv/bin/activate 2>/dev/null || true
python3 scripts/replay_synthetic.py --days 14 --out out/report.json || true
python3 scripts/eval_calibration.py --log out/nudges.csv --out out/calibration.json || true
python3 scripts/eval_qini.py --log out/nudges.csv --out out/uplift.json || true
echo '--- SUMMARY ---'
[ -f out/report.json ] && cat out/report.json || echo 'no report'
[ -f out/calibration.json ] && cat out/calibration.json || echo 'no calibration'
[ -f out/uplift.json ] && cat out/uplift.json || echo 'no uplift'
