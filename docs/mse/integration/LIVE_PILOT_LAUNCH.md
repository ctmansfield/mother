# Two-day live archival pilot

[MSE-LIVE-PILOT-20261121-05 r1](https://github.com/ctmansfield/mother/pull/23#issuecomment-7057163283) records Chad's explicit authorization to install and run the selected-data pilot. It supersedes the previous source-only/no-install/no-live limits within this scope. Backup/restore remains deferred. This is a launch record template until actual owning evidence and timestamps are entered; it is not a running-pilot claim.

## Scope and lifetime

- Destination: a separately initialized selected-record archive on the dedicated private archive VM. Existing synthetic archive and sequence-4 evidence remain unchanged.
- Data: the 14 selected HealthKit types in [the next-build requirements](LIVE_PILOT_NEXT_BUILD.md). No routes/GPS, waveform, arbitrary metadata, historical collector-file upload or LLM forwarding.
- Window: prospective collection from actual verified launch, with server and phone using the same UTC start and end exactly 48 hours apart. Record Guam equivalents. No historical backfill is included.
- Stop: stop collection and ingestion at cutoff; preserve unacknowledged pending bytes locally rather than silently delete or upload beyond scope. A manual stop must be available.
- Retention: accepted originals, revisions/tombstones, receipt and processing history have no automatic age purge after the trial. Current views reflect explicit deletions. Archive erasure remains a separate action.
- Capacity: publish measured storage and finite intake/backpressure limits. Reaching a limit stops further acceptance safely rather than discarding retained evidence.

## Launch evidence

| Gate | Required owning evidence | Current state |
| --- | --- | --- |
| Live app | Tested source/product pin, actual private HTTPS/Keychain/window/receipt path, prospective filter and background-capability facts | In progress |
| Live service | Reviewed package, isolated selected store, HTTPS enrollment/type/window/role limits, exact original/view/export round trip | In progress |
| Runtime | Installed source/config/schema, private file access, ready service, sufficient storage, exact-peer route and TLS/grant lifetime | Pending |
| Phone preservation | Intended device/signer, opaque immediate collector pre/post comparison and safe in-place install | Pending |
| Native steps | User-completed selected Health permissions and exact dedicated private CA trust if required | Pending |
| Independent readiness | SENTINEL source/runtime controls; PROVENANCE source/product/destination binding | Pending |
| Launch | Actual shared UTC/Guam start/end and explicit PM release | Not set |
| First commit | Private exact real original/receipt/current/history/export reconciliation; public counts/digests only | Not sent |
| Followup | Subsequent acknowledgment/queue status, actual availability and gaps, finite stop enforcement | Pending |

The current selected collector candidate and offline adapter alone do not satisfy live readiness. No phone installation or live activation is claimed by this document. User permission to run is already established; future questions are limited to actual native user steps or genuine missing inputs.

## Operator discipline

PHOENIX alone changes VM/runtime/network state. NICKY alone owns phone operations and may designate a serialized UI proxy. ORACLE authors/signs the app and FORGE packages the service. ATLAS freezes the window/type/retention contract. SENTINEL independently reviews controls; PROVENANCE binds exact artifacts and privately reconciles live evidence. LONESTAR tracks staged, installed, released, first committed, running and cutoff separately.

Keep health values, identifying screenshots, raw captures, private keys and bearer credentials with custodians. Shared reports contain scope, availability, counts, digests, timing and failure states. Transport encryption and actual access/at-rest facts are reported separately; no anonymity claim follows from pseudonymous IDs. No public exposure, main merge, unrelated VM/IDS work or backup gate is introduced.

The current two-minute startup issue has already been independently reduced to 5.244 seconds to active service, with authenticated HTTPS verified by 28.72 seconds and accepted evidence unchanged. Strict CI prerequisite #46 is separately qualified. Fresh clean-VM reproduction remains a distinct open task; do not relabel it as passed from an existing-VM test.
