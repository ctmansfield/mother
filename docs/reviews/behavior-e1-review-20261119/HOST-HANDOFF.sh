#!/usr/bin/env bash
# Isolated source verification and optional E1 acquisition. Invoke with bash.
# Every failure preserves logs and returns to the caller; no shell strict mode.

run_logged() {
  local name rc
  name="$1"
  shift
  "$@" > "$FW_REVIEW_RUN/logs/$name.log" 2>&1
  rc=$?
  tail -n 5 "$FW_REVIEW_RUN/logs/$name.log"
  printf '%s: exit %s\n' "$name" "$rc"
  printf '%s\n' "$rc" > "$FW_REVIEW_RUN/logs/$name.exit"
  return "$rc"
}

verify_package() {
  local checkout package
  checkout="$1"
  package="$2"
  (cd "$checkout/packages/$package" && sha256sum -c SHA256SUMS)
}

run_suite() {
  local checkout package pattern
  checkout="$1"
  package="$2"
  pattern="$3"
  (cd "$checkout" && python3 -B -m unittest discover -s "packages/$package/tests" -p "$pattern" -v)
}

main() {
  local mode base scout_pin behavior_pin literature_pin actual rc
  mode="${1:-tests}"
  if [ "$#" -gt 1 ] || { [ "$mode" != 'tests' ] && [ "$mode" != '--run-e1' ]; }; then
    echo 'Usage: bash HOST-HANDOFF.sh [--run-e1]' >&2
    return 2
  fi
  for dependency in git gh python3 sha256sum mktemp; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
      printf 'Missing required command: %s\n' "$dependency" >&2
      return 2
    fi
  done
  scout_pin='8f9907e7f6b5c4f639123ff1e8b8fe629b8d0308'
  behavior_pin='7666e95f7d9b761515496141bf5e6fd647b6f82e'
  literature_pin='a5c946c858081470aa59dfb9e00f1cf88559b524'
  base="$(mktemp -d "$HOME/fw-next-round.XXXXXX")" || return 2
  FW_REVIEW_RUN="$base"
  mkdir "$base/logs" || return 2
  printf 'LOCAL RUN: %s\n' "$base"
  printf 'scout %s\nbehavior %s\nliterature %s\n' "$scout_pin" "$behavior_pin" "$literature_pin" > "$base/source-pins.txt"
  if ! run_logged clone gh repo clone ctmansfield/production-framework "$base/repo" -- --no-checkout; then
    echo 'Clone failed; existing worktrees and services were not changed.' >&2
    return 2
  fi
  if ! run_logged fetch git -C "$base/repo" fetch --no-tags origin "$scout_pin" "$behavior_pin" "$literature_pin"; then
    return 2
  fi
  if ! run_logged checkout-scout git -C "$base/repo" worktree add --detach "$base/scout" "$scout_pin"; then return 2; fi
  if ! run_logged checkout-behavior git -C "$base/repo" worktree add --detach "$base/behavior" "$behavior_pin"; then return 2; fi
  if ! run_logged checkout-literature git -C "$base/repo" worktree add --detach "$base/literature" "$literature_pin"; then return 2; fi
  actual="$(git -C "$base/scout" rev-parse HEAD)" || return 2
  if [ "$actual" != "$scout_pin" ]; then echo 'Scout commit mismatch' >&2; return 2; fi
  actual="$(git -C "$base/behavior" rev-parse HEAD)" || return 2
  if [ "$actual" != "$behavior_pin" ]; then echo 'Behavior commit mismatch' >&2; return 2; fi
  actual="$(git -C "$base/literature" rev-parse HEAD)" || return 2
  if [ "$actual" != "$literature_pin" ]; then echo 'Literature commit mismatch' >&2; return 2; fi

  # Recheck source manifests before any tests. None of these commands posts reports.
  for package in fw00410 fw00411 fw00412 fw00414; do
    if ! run_logged "manifest-$package" verify_package "$base/literature" "$package"; then return 2; fi
  done
  if ! run_logged manifest-behavior verify_package "$base/behavior" fw00413; then return 2; fi
  if ! run_logged manifest-scout-fix verify_package "$base/scout" fw00411; then return 2; fi
  for package in fw00410 fw00411 fw00412; do
    if ! run_logged "tests-$package" run_suite "$base/literature" "$package" 'test_*.py'; then return 4; fi
  done
  if ! run_logged tests-scout-pin run_suite "$base/scout" fw00411 'test_pin_regression.py'; then return 4; fi
  if ! run_logged tests-behavior run_suite "$base/behavior" fw00413 'test_*.py'; then return 4; fi
  if ! run_logged tests-literature bash "$base/literature/packages/fw00414/scripts/verify_local.sh"; then return 4; fi
  if ! run_logged smoke-graph python3 -B "$base/literature/packages/fw00410/scripts/smoke.py"; then return 4; fi
  if ! run_logged smoke-scout python3 -B "$base/literature/packages/fw00411/scripts/smoke.py"; then return 4; fi
  printf 'PASS: isolated CPU source checks. Logs: %s/logs\n' "$base"
  printf 'Behavior source: %s/behavior\nLiterature source: %s/literature\n' "$base" "$base"
  echo 'No model inference or external report publication was performed.'

  if [ "$mode" = '--run-e1' ]; then
    run_logged e1-trial python3 -B "$base/literature/packages/fw00414/trial.py" \
      --root /mnt/nas_storage/research/e1-literature \
      --limit 27 --enable-network --allow-open-access-fulltext
    rc=$?
    printf 'E1 trial exit: %s; receipt: %s/logs/e1-trial.log\n' "$rc" "$base"
    echo 'Exit 0 describes completed processing; the receipt gives actual download and queue counts.'
    return "$rc"
  fi
  echo 'To acquire E1 articles after these tests, run the trial command in the literature README.'
  return 0
}

main "$@"
