#!/usr/bin/env bash

verify_synthetic() {
  local python_executable="${PYTHON:-python3}"
  if [ -z "${PYTHON:-}" ] && [ -x .venv/bin/python ]; then
    python_executable=.venv/bin/python
  fi

  "$python_executable" -m scripts.replay_synthetic --days 14 --out out/report.json || return
  "$python_executable" -m scripts.eval_calibration --log out/nudges.csv --out out/calibration.json || return
  "$python_executable" -m scripts.eval_qini --log out/nudges.csv --out out/uplift.json || return
  printf '%s\n' '--- SUMMARY ---'
  cat out/report.json out/calibration.json out/uplift.json
}

verify_synthetic "$@"
