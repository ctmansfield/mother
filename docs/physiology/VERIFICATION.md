# PF-001 evidence record

The release bundle records exact final compatible revisions, Git tree hashes
and patch checksums in `manifest.json`. Its `verification/` directory contains
the executed installation state, command logs and machine-readable result for
those exact trees. This file states what those results can establish.

## Completed evidence before final packaging

- Both remote main branches matched the handoff review bases. Original clones
  were clean and retained; all implementation used isolated worktrees. No
  deployment host, Compose runtime or representative personal dataset was
  available in the inspected workspace.
- Independent Mother review at `7c60f8f90ab183a939899a670a683f950ed600cd`
  passed 108 existing checks, then reproduced five integration defects with
  new failing regressions. Those failures were fixed, not waived.
- Independent remediation verification at
  `461de1ce9835137cf213feef3b10f3babf108cf1` passed **146** targeted tests,
  including all five regression cases, installed wheel resources, the generic
  evaluator and three additional session-lineage cases.
- E01 separately passed 30 author tests plus five independently authored
  grouping/availability/zero/overlap checks. The extra acceptance tests are
  included in the final release suite.
- Root integration verification of Coach passed **54 tests with 7 explicit
  live-test skips**. Node-RED function fixtures use controlled local inputs;
  no Home Assistant, Node-RED or other notification endpoint was called.
- A synthetic four-source path imported retained originals, generated replay
  JSON and produced Coach HTML with 14 observations and 3 events in its selected
  interval. An older glucose record remained archived outside that interval.
- The package was built and its synthetic demo executed outside the repository
  directory. The independent resource regression separately builds and inspects
  the wheel and loads package-relative analytics configuration.
- Independent packaging review first reproduced two blockers (checkout hook
  effects and untracked Python shadowing), then passed nine bounded cases after
  correction. Those miniature-repository probes are separate from the final
  actual-bundle verification.

## Verification environment

Python 3.12.14; Git 2.51.1; Node 24.22.1. Exact test dependency pins:
pytest 9.2.0, pandas 2.2.3, numpy 2.3.5, pyarrow 26.0.1, jsonschema 4.26.0,
requests 2.34.2, PyYAML 6.0.3 and defusedxml 0.7.1.
Setuptools 84.2.1 and wheel 0.48.0 are pinned for the offline package-resource
build check. Formatting/static checks used
Black 25.9.0 and Ruff 0.13.1 on owned/new Python files. These checks do not certify
unrelated old application code. `requirements-verify.txt` is included in the
bundle; the separate test environment preserves the supplied interpreter's
virtualenv path.

## Evidence not established

No real source bundle was reconciled, no personal response model was trained or
evaluated, no production migration/deployment occurred, and no live sensor,
latency, interruption or restart behavior was verified. Device models and
raw H10 ECG/RR history remain unknown. No credential was changed.

The optional legacy MI/bootstrap integration run was interrupted (exit 130),
not passed. Browser layout inspection remains open: the available Playwright
package lacked a browser binary and its attempted download failed. HTML output
generation, schema checks, escaping and source lineage are verified separately;
there is no screenshot-based layout approval in this release.

Repeated offline verification must not be described as real-data or clinical
validation. The synthetic evaluator's numerical errors test arithmetic only.
