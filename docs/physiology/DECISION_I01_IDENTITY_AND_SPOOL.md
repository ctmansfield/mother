# I01-U design decision brief: identity, authorization and offline spool

**Status:** Open for architecture/design and deployment reconciliation.
**Owner:** PM integration; design session decides consequential authentication
and user-to-subject policy. This brief is not authorization to configure
credentials or deploy an endpoint.

## Gap and why it matters

The offline Coach capture page accepts a user-supplied subject ID, generates
a versioned event, and exports an envelope protected by SHA-256. Mother's
offline receiver validates bytes, event structure, typed parent links and
subject equality in the archive.

**A valid envelope is not proof of who created it.** If a live endpoint
accepted unauthenticated files and trusted user-supplied subject IDs, one
person could write records into someone else's physiology archive. Because
the records can become training/evaluation evidence, false attribution is
a durable correctness and privacy failure, not just a UI issue.

The downloaded event file is base64 **encoded but not encrypted**. Browsers
may keep it in Downloads or backups; its retention/cleanup policy has not
been specified. The UI does not keep records in localStorage.

## Evidence and remaining uncertainty

- Coach I01-U Node synthetic tests verify event shape, timestamps, distinct
  action/outcome kinds, and exact envelope bytes.
- Mother pinned crossrepo synthetic tests verify digest, strict record checks,
  immutable archival revisions, idempotency and restart/replay.
- No actual runtime auth layer, session identity, API gateway, network
  topology, user-to-subject mapping, file ACL policy or transfer method has
  been inspected on the restored NAS.
- No personal export has been transferred. Browser download/layout QA is
  separate and remains open.

## Viable options / tradeoffs

| Option | Advantages | Risks and constraints |
| --- | --- | --- |
| A. User-initiated offline file import with OS permissions and an authenticated local operator | Minimal service exposure; explicit reviewed evidence; works before live integration | Manual workflow; Download folder retention, copy mistakes and user friction; still requires subject authorization |
| B. Authenticated internal-only Coach→Mother API via a verified existing reverse proxy / identity provider | Better UX, immediate acknowledged receipt, explicit server-side subject mapping | Requires runtime inventory, CSRF/origin policy, rate limits, audit, restart/queue semantics and approval for existing credentials |
| C. Explicit signed client events with per-device keys and strict server subject grants | Can preserve remote-origin provenance across delayed/offline transfer | Credential lifecycle, revocation, secure key storage, clock uncertainty and more implementation complexity |

## Recommendation

Keep **Option A** for offline qualification and pre-deployment review.
After the NAS environment is reconciled, consider **Option B** using
an *existing authorized* identity system, without creating or changing
credentials until explicitly approved. The server must derive the subject
from authenticated identity and grant checks, not from an untrusted JSON
field. Every durable write requires an explicit receipt correlated with
the immutable event ID and source revision. Retried delivery must be safe
after a lost receipt. Silence, a missing answer and an unobserved outcome
remain unknown.

The design session needs to decide whether future capture is single-user
local-only or multi-user/remote and whether copies of personal event files
must be encrypted, retained or securely removed on endpoints. This is not
a decision about treatments, dosing, medical thresholds or hardware.

## Requirements/interfaces affected

- Coach capture and transfer: identity context, event version, local outbox
  policy, explicit "prepared vs accepted" UX and retry/receipt states.
- Mother receiver: authenticated principal, approved subject mapping, parent
  reference authorization, input limits, CSRF/origin/transport controls,
  audit events and durable idempotent acknowledgments.
- Archive: immutable original bytes, revision IDs and processing versions.
- Release: separate source tests, synthetic integration, authentication
  integration, deployed restart and verified live behavior.

## Work that can proceed

- Browser visual, keyboard and download accessibility QA with synthetic data.
- Offline packets, lineage, archive restart and replay regression suites.
- Read-only inventory of the NAS runtime *when the operator is ready*.
- Source export qualification and channel coverage analysis independently.
- Versioned target design after the physiological source data is qualified.

No task may infer consent to modify NAS services, credentials or live
notifications from this proposal.
