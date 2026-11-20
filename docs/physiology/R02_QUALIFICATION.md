# R02 — Source-qualification preflight (offline, no model inference)

**Owner:** Acquisition / source-qualification workstream; shared-contract owner: PM.
**Base:** PF-001 Mother `work/physiology-foundation-pf001`.
**Contract:** Coach/Mother physiological evidence `1.0.0`.
**State:** Bounded software preflight; real-data R02 acceptance remains blocked on actual original exports.
**Interface:** Reads a local JSON replay; writes a new diagnostic JSON (never source records).

## Purpose

Use the existing PF-001 import → archive → replay path to identify quality,
availability and source-lineage questions before selecting a physiological
recovery endpoint. The script is intentionally read-only. It never requests
Nightscout data, executes tools, sends notifications, modifies the archive, or
predicts physiological state.

## Install / run

Use the reviewed Mother branch in an isolated worktree or disposable checkout.
Do **not** replace the running Mother service or alter credentials.

Produce an existing version 1.0.0 replay via the current Mother CLI. For
example, the synthetic demo can create one without any personal input:

```bash
python -m mother.physiology.cli demo --output-dir /tmp/r02-synthetic
```

Inspect the demo manifest for the actual replay path. With that replay path:

```bash
python -m mother.physiology.qualification \
  --input /path/to/existing_replay.json \
  --output /path/to/new_r02_report.json
```

The output path must not exist. The report is created with owner-only
permissions on POSIX systems. Input replay files larger than 64 MiB are
rejected rather than silently truncated. The command does not delete or
overwrite existing files.

## VERIFY (bounded, no notifications)

```bash
python -m unittest discover -s tests/physiology -p test_qualification.py -v
```

No application services, live notification tests, remote data, or model
endpoints are needed. The dedicated R02 GitHub Actions workflow runs only
these tests and propagates failures. The older general CI wrapper masks some
failures and is **not** the R02 acceptance gate.

The synthetic acceptance set covers UTC offset equivalence; zero/unknown
separation; conservative cross-source equal-value candidates; missing
availability; incorrect source lineage; invalid timestamps; output data
minimization; exclusive owner-only reports; and oversize input rejection.

## Report semantics

- `source_channels` lists declared observation count, epistemic state, unit
  inventory, unknown source availability, original-clock comparisons, and flags.
- `declared_coverage` repeats the bundle's coverage declarations; it does not
  authenticate completeness or derive cadence.
- `possible_cross_source_equal_sample_groups` counts channel/time/value/unit
  matches in distinct source namespaces. These are **review candidates**, not
  proof that the records are relayed or that either reading is independent.
- `review_flags` identifies timestamp and ingestion anomalies, incomplete
  imports, and unqualified cadence/coverage.
- `real_data_reconciled`, `live_device_qualified`, and
  `no_personal_performance_claim` remain conservative regardless of content.

The script only checks a subset of the replay contract for dependency and
timing consistency. It assumes the input was already validated using the
canonical 1.0.0 schema; this is **not** an independent schema validator.

Raw source payloads, subject identifiers, individual measured values, and
event free text are deliberately excluded from the generated report.
Source-instance labels, flags, and aggregate counts can still be sensitive:
keep actual reports private and outside the public repository.

## Remaining dependencies / handoff

1. **Acquisition owner:** Receive one original overlapping Nightscout entries,
   Apple Health XML, and Polar export interval; record original hashes,
   source/UTC clocks, count, rejected fields and native identities. Never add
   private source records to GitHub.
2. **Independent verifier:** Compare source-native counts and exact normalized
   records against the replay; investigate potential relays rather than
   automatically deduplicating matches.
3. **Analytics owner:** Use qualified coverage, exercise cessation and sleep
   evidence to propose channel-specific outcome and episode recipes. Do not
   assume RR/ECG history or a particular next-sleep endpoint.
4. **Runtime owner:** Read-only inventory of installed revisions, actual
   Nightscout API capability, flow export and archive destination. This
   remains separate from a test against public source code.

**Evidence labels:** source inspected / isolated tests / synthetic integration /
real-data reconciliation / deployed / verified live. The first three do not
substitute for later gates. No schema, migration, credentials, services, or
physiological intervention policy changed in R02 preflight.
