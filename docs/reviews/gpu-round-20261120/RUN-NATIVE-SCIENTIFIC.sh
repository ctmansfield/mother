#!/usr/bin/env bash
# Run the cached native scientific engines serially after the Ollama comparison.

run_native_scientific() {
  local native_pack_root native_repo native_prior native_attempt native_pin native_status native_all_status native_engine native_python
  if [ "$#" -ne 1 ]; then
    printf 'Usage: bash RUN-NATIVE-SCIENTIFIC.sh /absolute/scientific-attempt-directory\n' >&2
    return 2
  fi
  native_prior="$1"
  native_pack_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || return 2
  native_repo="$(git -C "$native_pack_root" rev-parse --show-toplevel)" || return 2
  native_pin="$(git -C "$native_repo" rev-parse HEAD)" || return 2
  if [ -n "$(git -C "$native_repo" status --porcelain --untracked-files=all)" ]; then
    printf 'REFUSED: MOTHER source checkout must be clean.\n' >&2
    return 2
  fi
  for native_engine in scientific behavior native; do
    if ! (cd "$native_pack_root/$native_engine" && sha256sum -c SHA256SUMS); then
      printf 'REFUSED: %s manifest differs.\n' "$native_engine" >&2
      return 2
    fi
  done
  # This gate reads existing scientific evidence only; it issues no model call.
  if ! python3 -B - "$native_pack_root" "$native_prior" <<'PY'
from pathlib import Path
import sys
pack, prior = map(Path, sys.argv[1:])
sys.path.insert(0, str(pack / 'behavior'))
import behavior_compare
behavior_compare.check_scientific_predecessor(prior / 'results')
sys.path.insert(0, str(pack / 'scientific'))
import scientific_compare
scientific_compare.check_source((prior / 'framework').absolute())
print('Completed scientific predecessor and clean framework source verified.')
PY
  then
    printf 'REFUSED: inspect the existing scientific attempt before native inference.\n' >&2
    return 2
  fi

  umask 077
  native_attempt="$(mktemp -d "$HOME/fw-native-science.XXXXXXXX")" || return 2
  printf '%s\n' "$native_pin" > "$native_attempt/mother-source-pin.txt"
  printf '%s\n' "$native_prior" > "$native_attempt/scientific-attempt.txt"
  printf 'NATIVE ATTEMPT: %s\nMOTHER SOURCE: %s\n' "$native_attempt" "$native_pin"
  if ! python3 -B "$native_pack_root/native/native_science.py" inspect > "$native_attempt/readiness.json"; then
    printf 'REFUSED: readiness inspection failed; see %s\n' "$native_attempt" >&2
    printf '2\n' > "$native_attempt/launch-exit.code"
    return 2
  fi

  native_all_status=0
  for native_engine in medcpt txgemma; do
    native_python="$HOME/ai-envs/$native_engine/bin/python"
    if [ ! -x "$native_python" ]; then
      printf 'HELD: existing environment is absent: %s\n' "$native_python"
      native_status=2
    else
      # Each supervisor takes the shared lock, rechecks idle state, and owns
      # only its child worker. An engine failure is retained independently.
      "$native_python" -u -B "$native_pack_root/native/native_science.py" "$native_engine" \
        --source "$native_prior/framework" 2>&1 | tee "$native_attempt/$native_engine.log"
      native_status=${PIPESTATUS[0]}
    fi
    printf '%s\n' "$native_status" > "$native_attempt/$native_engine-exit.code"
    if [ "$native_status" -ne 0 ]; then
      native_all_status=4
    fi
    if [ "$native_status" -eq 130 ] || [ "$native_status" -eq 137 ] || [ "$native_status" -eq 143 ]; then
      printf 'INTERRUPTED: inspect the owned worker and GPU before continuing.\n'
      break
    fi
  done
  printf '%s\n' "$native_all_status" > "$native_attempt/launch-exit.code"
  printf '\nNative scientific screen exit: %s\nLOCAL EVIDENCE: %s\n' "$native_all_status" "$native_attempt"
  return "$native_all_status"
}

run_native_scientific "$@"
