# Coding workflow review and next diagnostic

19 November 2026. Source: [FW00567 actual host receipt](https://github.com/ctmansfield/production-framework/issues/133#issuecomment-7008931692), pinned implementation `d18ee0350cbfecd3bda3984f8deeb8a9cfa194b0`. This document reviews an observed completed run and proposes the next diagnostic. It does not claim to have read the host-local raw responses.

## Observed campaign

| Experimental contrast | Strict protected pass | Guided protected pass | Strict/guided human-review eligible |
|---|---:|---:|---:|
| Baseline: GPT-OSS 20B coder | 7/8 | 8/8 | 0/8 / 0/8 |
| Qwen2.5-Coder 14B Q8 | 0/8 | 5/8 | 0/8 / 1/8 |
| Devstral Small 2 24B | 0/8 | 4/8 | 0/8 / 0/8 |
| Qwen3-Coder 30B | 0/8 | 7/8 | 0/8 / 2/8 |
| Planning/QA control: GPT-OSS coder | 7/8 | 8/8 | 0/8 / 0/8 |

All 80 planner outputs satisfied the plan-shape gate. There were 400 sequential role calls. Protected code passed in 46/80 workflows (14/40 strict, 32/40 guided), while 3/80 workflows became eligible for human review. The published false-approval count is zero for every arm; this alone says little about useful review coverage without the count of valid review decisions.

The implementation's `false_review_approval` counter includes reviewer A, reviewer B and QA in the same loop. Interpret this as an aggregate false-approval count across those three decision requests, despite the report's narrower column label.

## Main unresolved question

Why did 43 protected-passing workflows remain held? The public summary table cannot distinguish invalid review JSON, missing decisions, deliberate HOLD, disagreement, or another adjudication condition. The source already writes these distinctions into the private result data; review those before spending GPU time on a new campaign.

The implementation writes `summary.json` with per-role `review_valid`, `held`, `review_disagreements`, `unsafe_review_approvals`, family-specific results and latency totals. It also writes each workflow to `raw-local.jsonl`, including parsed review decisions, role status, code-format handling and protected result. No source or raw model text needs to be exported to answer the first diagnostic question.

## Exact preserved evidence locations

```text
/home/chad/.local/state/mother-fw00567/live-d18ee0350cbf/summary.json
/home/chad/.local/state/mother-fw00567/live-d18ee0350cbf/raw-local.jsonl
```

Published summary SHA-256:

```text
6a1b3282cfcb65577a06863c4e0092401df2fbb6ba7e1a88ef636f7a09c0ec89
```

Published raw output SHA-256:

```text
fb24c7c6374b82ccf64eb3997b646b922eeb3172a41659080111d6b02fe7444e
```

## First read-only diagnostic

Run this from `chad`'s host account. It reads the existing summary, verifies its published byte hash, and prints aggregate counts only. It does not run models or alter the original evidence.

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib, json

p = Path.home() / '.local/state/mother-fw00567/live-d18ee0350cbf/summary.json'
blob = p.read_bytes()
expected = '6a1b3282cfcb65577a06863c4e0092401df2fbb6ba7e1a88ef636f7a09c0ec89'
actual = hashlib.sha256(blob).hexdigest()
if actual != expected:
    print('HOLD: summary differs from published receipt', actual)
else:
    data = json.loads(blob)
    print('Verified summary SHA-256:', actual)
    print('Source:', data.get('source_pin'))
    for trial, conditions in data['results'].items():
        for protocol, cell in conditions.items():
            print(json.dumps({
                'trial': trial,
                'protocol': protocol,
                'workflows': cell['workflows'],
                'protected_pass': cell['protected_pass'],
                'eligible': cell['human_review_eligible'],
                'held': cell['held'],
                'valid_review_decisions': cell['review_valid'],
                'disagreements': cell['review_disagreements'],
                'unsafe_approvals': cell['unsafe_review_approvals']
            }, sort_keys=True))
PY
```

This command uses fields actually defined by `integration.summarize`, not guessed report names.

## Next local analysis, after the aggregate diagnostic

Build a role-by-protocol table over the 46 protected-passing workflows, with separate counts for `GENERATED`, `INVALID_REVIEW` and request errors, then count parsed APPROVE/HOLD decisions and disagreement. Repeat the same counts for protected failures. Keep valid-decision denominators explicit. Preserve unknown parsing causes: the stored role status identifies an invalid review but does not persist its specific parser exception.

If malformed review output dominates, examine a bounded local sample against the exact review contract to identify missing/extra keys, quoted or altered hashes, invalid decision strings, or prose/fence contamination. Raw samples stay on the host. A repair proposal should cite counts and one sanitized structural example without changing a historical result.

If valid HOLD decisions dominate, examine whether reviewers are applying a different acceptance standard than the protected task, or whether QA has additional information that legitimately holds the result. Do not weaken the protected gate simply to raise eligibility.

## Proposed next campaign

The guided treatment combines JSON guidance for planner/reviewers/QA with bounded fenced-source recovery for the coder. Separate those changes in a 2×2 protocol experiment before attributing all gains to model reasoning. Freeze exact source, task version, model digests, context budget and output limits; vary one factor per contrast.

Review calibration can reuse frozen candidate/test receipts, avoiding new coder calls: pair protected-passing and deliberately failing candidates, predeclare the expected review decision and use held-out cases. Report correct approvals, correct holds, false approvals, false holds, invalid protocols and latency separately for each reviewer and QA role.

Only after the handoff works reliably should the next code-capability experiment add multi-file repair, dependency navigation and bounded test/repair iterations. Do not transform the eight-task screen into a permanent model assignment.

## Source evidence

- [Campaign design and roster mapping](https://github.com/ctmansfield/production-framework/blob/d18ee0350cbfecd3bda3984f8deeb8a9cfa194b0/packages/fw00567/README.md)
- [Integration and persisted summary fields](https://github.com/ctmansfield/production-framework/blob/d18ee0350cbfecd3bda3984f8deeb8a9cfa194b0/packages/fw00567/integration.py)
- [Actual completed campaign receipt](https://github.com/ctmansfield/production-framework/issues/133#issuecomment-7008931692)
