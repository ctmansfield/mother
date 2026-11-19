#!/usr/bin/env bash
# Invoke only after the scientific comparison has completed.

run_behavioral() {
  local behavior_pack_root behavior_repo behavior_prior behavior_attempt behavior_status behavior_pin
  if [ "$#" -ne 1 ]; then
    printf 'Usage: bash RUN-BEHAVIORAL.sh /absolute/scientific-attempt-directory\n' >&2
    return 2
  fi
  behavior_prior="$1"
  behavior_pack_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2
  behavior_repo="$(git -C "$behavior_pack_root" rev-parse --show-toplevel)" || return 2
  behavior_pin="$(git -C "$behavior_repo" rev-parse HEAD)" || return 2
  if [ -n "$(git -C "$behavior_repo" status --porcelain --untracked-files=all)" ]; then
    printf 'REFUSED: MOTHER source checkout must be clean.\n' >&2
    return 2
  fi
  if ! (cd "$behavior_pack_root/scientific" && sha256sum -c SHA256SUMS) ||
     ! (cd "$behavior_pack_root/behavior" && sha256sum -c SHA256SUMS); then
    printf 'REFUSED: source manifests differ.\n' >&2
    return 2
  fi
  umask 077
  behavior_attempt="$(mktemp -d "$HOME/fw-behavioral-gpu.XXXXXXXX")" || return 2
  printf '%s\n' "$behavior_pin" > "$behavior_attempt/mother-source-pin.txt"
  printf '%s\n' "$behavior_prior" > "$behavior_attempt/scientific-attempt.txt"
  printf 'BEHAVIORAL ATTEMPT: %s\nMOTHER SOURCE: %s\n' "$behavior_attempt" "$behavior_pin"
  timeout --signal=TERM --kill-after=15s 20500s \
    python3 -u -B "$behavior_pack_root/behavior/behavior_compare.py" \
      --after-scientific "$behavior_prior/results" \
      --state "$behavior_attempt/results" --live --gpu-idle-confirmed \
      2>&1 | tee "$behavior_attempt/runner.log"
  behavior_status=${PIPESTATUS[0]}
  printf '%s\n' "$behavior_status" > "$behavior_attempt/launch-exit.code"
  printf '\nBehavioral GPU screen exit: %s\nLOCAL EVIDENCE: %s\n' "$behavior_status" "$behavior_attempt"
  if [ "$behavior_status" -eq 124 ] || [ "$behavior_status" -eq 137 ]; then
    printf 'WATCHDOG: inspect Ollama/GPU completion before another run; no automatic retry.\n'
  fi
  return "$behavior_status"
}

run_behavioral "$@"
