# Two-day live archival pilot

[MSE-LIVE-PILOT-20261121-05 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057163283) records Chad's explicit authorization to install and run the selected-data pilot. It supersedes the previous source-only/no-install/no-live limits within this scope. Backup/restore remains deferred. Status: RUNNING with actual first acceptance and natural follow-up independently reconciled. The full 48-hour outcome is still in progress.

## Scope and lifetime

- Destination: a separately initialized selected-record archive on the dedicated private archive VM. Existing synthetic archive and sequence-4 evidence remain unchanged.
- Data: the 14 selected HealthKit types in [the next-build requirements](LIVE_PILOT_NEXT_BUILD.md). No routes/GPS, waveform, arbitrary metadata, historical collector-file upload or LLM forwarding.
- Window: prospective collection from November 21, 2026 at 14:45:00 Guam (`2026-11-21T04:45:00.000000Z`) through November 23 at 14:45:00 Guam (`2026-11-23T04:45:00.000000Z`), exactly 48 hours. The phone enrollment, server release, phone grant and relay deadline match. No historical backfill is included.
- Stop: stop collection and ingestion at cutoff; preserve unacknowledged pending bytes locally rather than silently delete or upload beyond scope. A manual stop must be available.
- Retention: accepted originals, revisions/tombstones, receipt and processing history have no automatic age purge after the trial. Current views reflect explicit deletions. Archive erasure remains a separate action.
- Capacity: publish measured storage and finite intake/backpressure limits. Reaching a limit stops further acceptance safely rather than discarding retained evidence.

## Launch evidence

| Gate | Required owning evidence | Current state |
| --- | --- | --- |
| Live app | Tested source/product pin, actual private HTTPS/Keychain/window/receipt path, prospective filter and background-capability facts | Qualified source and signed product |
| Live service | Reviewed package, isolated selected store, HTTPS enrollment/type/window/role limits, exact original/view/export round trip | Exact r3 source/package qualified |
| Runtime | Installed source/config/schema, private file access, ready service, sufficient storage, exact-peer route and TLS/grant lifetime | Independently verified; exact private peer relay and TLS; window armed |
| Phone preservation | Intended device/signer, opaque immediate collector pre/post comparison and safe in-place install | Installed 295beda in place; collector and full pilot state matched |
| Native steps | User-completed selected Health permissions and exact dedicated private CA trust if required | Chad confirmed exact pilot CA trust and selected read permissions |
| Independent readiness | SENTINEL source/runtime controls; PROVENANCE source/product/destination binding | SENTINEL and PROVENANCE final readiness GO |
| Launch | Actual shared UTC/Guam start/end and explicit PM release | Exact assigned window; PM enable authorized at start |
| First commit | Private exact real original/receipt/current/history/export reconciliation; public counts/digests only | First receipt 15:04:41 Guam; original/receipt/view/export matched |
| Followup | Subsequent acknowledgment/queue status, actual availability and gaps, finite stop enforcement | Natural second receipt 15:05:07 Guam; phone queue empty; full window pending |

The installed live client is `295bedac2d6602db0d4effd11750eaac033a80df` (49 host tests); deployed service is r3 `e6762b00fac86c79fc08df426ddc5bc95122c124` (17 package tests plus six independent cutoff/crash cases). Independent phone readback confirmed matching destination/scope/window, enabled state, normalized receipts and an empty pending queue. See [window assignment](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057392010), [enable readiness](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057423425) and the acceptance evidence below. User permission to run is established; future questions are limited to actual native user steps or genuine missing inputs.

## Operator discipline

PHOENIX alone changes VM/runtime/network state. NICKY alone owns phone operations and may designate a serialized UI proxy. ORACLE authors/signs the app and FORGE packages the service. ATLAS freezes the window/type/retention contract. SENTINEL independently reviews controls; PROVENANCE binds exact artifacts and privately reconciles live evidence. LONESTAR tracks staged, installed, released, first committed, running and cutoff separately.

Keep health values, identifying screenshots, raw captures, private keys and bearer credentials with custodians. Shared reports contain scope, availability, counts, digests, timing and failure states. Transport encryption and actual access/at-rest facts are reported separately; no anonymity claim follows from pseudonymous IDs. No public exposure, main merge, unrelated VM/IDS work or backup gate is introduced.

The current two-minute startup issue has already been independently reduced to 5.244 seconds to active service, with authenticated HTTPS verified by 28.72 seconds and accepted evidence unchanged. Strict CI prerequisite #46 is separately qualified. Fresh clean-VM reproduction remains a distinct open task; do not relabel it as passed from an existing-VM test.

Guest and host backing-storage checks did not demonstrate encryption at rest. Service identity/file isolation and verified TLS passed; no anonymity or disk-compromise protection is claimed. This fact was disclosed before live activation. The conservative cutoff keeps late or uncertain custody/publication sealed and unacknowledged; the phone retains pending exact bytes. See [PM cutoff disposition](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057329232).

## Actual live acceptance and recovery

The initial 698-byte batch blocked before custody. Its historical HTTP response remains unclassified. The clock was corrected forward by 1.046841 seconds on the exact archive guest; guarded 30-second checks measured 33–38 ms lag afterward. No backward adjustment or window extension occurred. After renewed zero-custody proof, one explicit recovery on signed app `295bedac2d6602db0d4effd11750eaac033a80df` checked receipt first and retried the unchanged uncommitted batch. Collector and full pilot-state copies matched across the in-place update. All 49 host tests and independent signature/product checks passed.

Sequence 1 committed November 21 at 15:04:41 Guam; sequence 2 committed 15:05:07 without another recovery action. Exact phone/server receipts, originals and complete scoped views/exports matched: 23 acknowledged revisions across two types, pending 0, blocked/recovery claim absent. A later readback at 15:11:27 reported 26 rows/five batches across heart rate, steps, walking/running distance and active energy; this is not all 14 types populated. No historical backfill was part of that run.

[PM running report](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057710052) · [Phone evidence](https://github.com/ctmansfield/production-framework/issues/50#issuecomment-7057679587) · [Server evidence](https://github.com/ctmansfield/production-framework/issues/44#issuecomment-7057676218) · [Published operational source](https://github.com/ctmansfield/mother/tree/0ffbc5e0842530d7539b0ad72394248bec612e0d/tools/mse_integration/recovery/selected_live_runtime). The app was backgrounded and Mirroring ended. Post-background server acceptance was observed, without proof of continuous lock state. Optional clock-tolerance #49 remained undeployed.
