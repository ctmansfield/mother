#!/usr/bin/env bash
# Run this file with bash from the pinned MOTHER source checkout.
# No shell option changes, background service changes, or issue publication.

run_scientific() {
  local gpu_pack_root gpu_mother_root gpu_mother_pin gpu_attempt gpu_framework gpu_status gpu_dependency
  gpu_pack_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2
  gpu_mother_root="$(git -C "$gpu_pack_root" rev-parse --show-toplevel)" || return 2
  gpu_mother_pin="$(git -C "$gpu_mother_root" rev-parse HEAD)" || return 2
  gpu_dependency="ba6fbb90c031f122b7db61d2f67f2b22ef1cf130"

  if [ "$#" -ne 0 ]; then
    printf 'Usage: bash RUN-SCIENTIFIC.sh\n' >&2
    return 2
  fi
  if [ -n "$(git -C "$gpu_mother_root" status --porcelain --untracked-files=all)" ]; then
    printf 'REFUSED: MOTHER source checkout must be clean.\n' >&2
    return 2
  fi
  for gpu_dependency_command in gh git python3 sha256sum tee timeout; do
    if ! command -v "$gpu_dependency_command" >/dev/null 2>&1; then
      printf 'REFUSED: required command is absent: %s\n' "$gpu_dependency_command" >&2
      return 2
    fi
  done
  if ! (cd "$gpu_pack_root/scientific" && sha256sum -c SHA256SUMS); then
    printf 'REFUSED: scientific wrapper manifest differs.\n' >&2
    return 2
  fi

  umask 077
  gpu_attempt="$(mktemp -d "$HOME/fw-scientific-gpu.XXXXXXXX")" || return 2
  gpu_framework="$gpu_attempt/framework"
  printf 'ATTEMPT: %s\nMOTHER SOURCE: %s\nFRAMEWORK SOURCE: %s\n' "$gpu_attempt" "$gpu_mother_pin" "$gpu_dependency"
  printf '%s\n' "$gpu_mother_pin" > "$gpu_attempt/mother-source-pin.txt"
  printf '%s\n' "$gpu_dependency" > "$gpu_attempt/framework-source-pin.txt"
  if ! gh repo clone ctmansfield/production-framework "$gpu_framework" -- --quiet; then
    printf 'REFUSED: source checkout failed; retained attempt: %s\n' "$gpu_attempt" >&2
    printf '2\n' > "$gpu_attempt/launch-exit.code"
    return 2
  fi
  if ! git -C "$gpu_framework" checkout --detach "$gpu_dependency"; then
    printf 'REFUSED: exact framework source unavailable.\n' >&2
    printf '2\n' > "$gpu_attempt/launch-exit.code"
    return 2
  fi

  # The wrapper performs exact source/receipt, model digest, and idle checks
  # before issuing a request. All models run serially. Existing attempts remain.
  # The outer watchdog only owns this local client. If it fires, Ollama server
  # completion is unknown: retain logs and inspect before any retry/new run.
  timeout --signal=TERM --kill-after=15s 12500s \
    python3 -u -B "$gpu_pack_root/scientific/scientific_compare.py" \
      --checkout "$gpu_framework" \
      --state "$gpu_attempt/results" --live --gpu-idle-confirmed \
      2>&1 | tee "$gpu_attempt/runner.log"
  gpu_status=${PIPESTATUS[0]}
  printf '%s\n' "$gpu_status" > "$gpu_attempt/launch-exit.code"
  printf '\nScientific GPU screen exit: %s\nLOCAL EVIDENCE: %s\n' "$gpu_status" "$gpu_attempt"
  if [ "$gpu_status" -eq 124 ] || [ "$gpu_status" -eq 137 ]; then
    printf 'WATCHDOG: inspect Ollama/GPU completion before another run; no automatic retry.\n'
  fi
  return "$gpu_status"
}

run_scientific "$@"
