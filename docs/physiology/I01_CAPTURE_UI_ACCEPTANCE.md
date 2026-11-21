# I01-U acceptance — Coach browser capture to Mother archive

**Status:** Isolated, synthetic cross-repository verification.
**Mother base:** I01-T2 PR #6, which already depends on Mother I01-D PR #5.
**Coach dependency:** I01-U manual capture PR #4, pinned to
`6ab02988c44e3069d5b5e6ef4bca4966330b3d8e`.
**Shared contract:** 1.0.0, no schema or migration changes.

## Purpose

Run the **actual Coach capture_ui.js** event and envelope builders through
Mother's existing 1.0.0 strict envelope receiver, immutable ingestion,
SQLite restart, and retrospective replay. Do not substitute a test-only
reimplementation of the wire format.

This uses only synthetic data, in temporary SQLite archives. The browser
capture page remains offline and does not send events to a live service.

## Worker ownership

- Coach interaction owner: `coach_app/physiology/manual_capture.html`,
  `capture_ui.js`, and its Node acceptance tests.
- Mother integration/verification owner: this pinned workflow,
  `tests/physiology/generate_ui_fixture.cjs` and
  `test_capture_ui_crossrepo.py`.
- PM only: shared contract, time utility, migrations and release manifests.

No worker may modify the other's owned files or install on the NAS.

## INSTALL / VERIFY

Use an isolated Mother worktree based on I01-T2 and an isolated Coach checkout
at the pinned commit. Run with Node 22, Python 3.11+, and jsonschema. Set
`COACH_CHECKOUT` to the absolute path to the reviewed Coach checkout.

```bash
COACH_CHECKOUT="/path/to/pinned-coach" \
PYTHONPATH="/path/to/mother:/path/to/pinned-coach" \
python -m unittest discover -s tests/physiology -p test_capture_ui_crossrepo.py -v
```

The pinned GitHub Actions job checks the Coach SHA before generating test
packets. It then reruns existing Mother I01-T2 handoff tests against the
checked-out sender.

## Acceptance cases

- A unicode-containing user marker exported from the real UI module is
  accepted with exact submitted bytes and SHA-256 source lineage.
- Recorded UTC time remains distinct from optional occurrence time with its
  explicit +10:00 offset; unknown knowledge remains null.
- The same file after archive restart is idempotent, with a stable revision.
- A standalone reported action is distinct from a subsequently reported
  outcome, which references its archived action.
- No user report is converted to a sensor measurement or medical conclusion.

## Release limits / rollback

No automated prompt, authenticated HTTP transport, account authorization,
wearable integration, inference, intervention, NAS service change, original
personal data, or production rollout is part of this review. GitHub CI uses
temporary data and no notifications. Clinical or recovery conclusions remain
outside scope.

The checksum verifies bytes, not the author or authority of the event.
Actual browser layout/download accessibility remains an independent QA gate;
the test invokes the UI's real JS builders in Node, not the browser DOM.
No existing archive migration is changed; rollback is to leave this
review-only test and UI unmerged/uninstalled.
