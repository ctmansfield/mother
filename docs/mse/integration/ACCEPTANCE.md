# Independent MSE integration acceptance

MSE-INTEGRATION-20261120-01 r1. [Directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041443650)

The fixture pack uses fabricated UUIDs, readings, source labels and opaque anchors. Captured JSON follows the HealthArchive/SavedReading fields in [HealthBridge source](https://github.com/ctmansfield/mother-health-bridge/blob/9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6/MotherHealthBridge/ContentView.swift). Dates are seconds since 2001-01-01 UTC, matching the default Swift Codable Date representation. Coverage and delivery identity are inputs to the scenario stored separately in expected.json. The capture does not assert device identity, permission coverage, native deletion time or server commit time.

| Case | Fixture | Acceptance assertion |
| --- | --- | --- |
| Baseline | HR and SDNN, one deleted reading and one unknown UUID tombstone | Preserve both tombstones and the deleted observation history. Unknown tombstone channel stays unknown. |
| Partial | Existing SDNN only | Preserve observations omitted from this capture and avoid duplicate revisions for the unchanged reading. |
| Empty | Empty readings and tombstones | Preserve prior evidence and unknown coverage. |
| Malformed | Truncated JSON | No accepted normalized observations or advanced acceptance checkpoint. Record rejection or quarantine. |
| Conflicting UUID | Two incompatible values for one UUID in a capture | No silent first-wins, last-wins or partial normalized acceptance. |
| Changed batch | Same scope and delivery ID as baseline, different bytes | Reject delivery conflict. Preserve the original receipt and artifact. |
| Identical retry | Exact baseline bytes and delivery identity | Reopen the store and verify stable commitment identity and no duplicate revisions. |
| Late | Biological interval predates baseline, source receipt follows it | Exclude from baseline online cutoff. Include in a later snapshot with lineage. |

The oracle at `tests/fixtures/mse_integration/expected.json` records exact artifact hashes, UUID lists, tombstone lists and logical revision memberships. Revision 1 is the fixture's expected first logical revision membership. Map this to the frozen adapter and archive contracts once their exact heads arrive. No fixture invents source-native revision metadata.

Run the fixture-only checks:

```sh
python3 -m unittest discover -s tests/acceptance/mse_integration -v
```

## Author-head acceptance pending

- Adapter: bind the exact artifact digest, verify parsed source times and unknowns, and compare live IDs, measured history and tombstones. Check fixture bytes before and after.
- Artifact and ledger: retry the same bytes, reject the changed batch, isolate malformed and conflicting observations, and reopen stores to reconcile exact membership and commitment identities.
- Snapshot and MSE: verify historical and later cutoff views, explicit unknown coverage, source pointers and distinction between measured and derived evidence. Exercise an unavailable model path without losing committed source evidence.
- Recovery: record the fault boundary and reopened state using the combined pinned implementation. Do not count specification-only cases as runtime passes.

Source baseline `c05f38096406965496d7d4a09edf4b3575235311`. Requirements and plan `91d67e387e91d93a7a60aec03c8164c11c7aa994`. Open PF-001 dependency PR #18 `b4e70b7123689ec164ba09e2974645ae36b184a2`. The fixture checks are standalone. Adapter, ledger, recovery and MSE executions await the exact author heads and frozen interfaces.

## Candidate 0.1 edge coverage (r2)

ATLAS PR #28 candidate `a732adda92cc79659bf2413c7d45891cf2d13264` is provisional. The edge pack exercises repeated delete timestamps in both source locations, an unknown UUID deletion, ambiguous upserts, duplicate JSON keys, reversed intervals, and exponent-form measurement lexemes and half-even Date ties. A fixed UTF-8 canonical JSON digest vector checks encoding independently of an adapter. It does not bind a receipt, revision or snapshot schema.

The exact receipt tests will mutate one binding at a time: subject, source instance, batch, artifact digest and export digest. Each mutation must fail without acceptance or checkpoint advancement. The test suite will consume the schema-specific golden preimages when ATLAS publishes them. Combined author-head runs remain pending. [r2 assignment](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041572809)

## Destination readiness and synthetic qualification

MSE-DESTINATION-READINESS-20261121-01 r1 assigns a metadata audit. PHOENIX owns the observed inventory and disposition. Record the evidence source, timestamp, expected binding and observed result for each check. Use **observed**, **configuration only**, **documentation only**, **unavailable**, or **untested**. Keep hostnames, paths with sensitive identifiers, and credentials in approved private custody. [Directive](https://github.com/ctmansfield/mother/pull/23#issuecomment-7041665721)

| Gate | Evidence needed before proposing synthetic qualification |
| --- | --- |
| Service and schema | Observe the existing service state, version, ownership and exact runtime binding. Reconcile read-only catalog metadata with versioned migrations and constraints for artifact identity, scoped unique batch, receipt, revisions, tombstones and lineage. An unrelated running database cannot satisfy these checks. |
| Durable capacity | Observe the mounts and available capacity for artifact, journal and archive state. Record free bytes/inodes, the expected growth and retention budget, ownership, and restart persistence. A configured path or container volume name alone leaves backing storage and durability unverified. |
| Access | Identify the current private route, endpoint, TLS identity, expected caller and least-privileged service account from established records and permitted readback. Record absent components and untested authenticated write/deny behavior. |
| Backup and restore | Record backup schedule and most recent successful run from metadata. Identify the single recoverable boundary spanning original bytes, acceptance state and revisions, the documented restore invocation, and measured restore evidence or its absence. Schedule and backup success do not establish recoverability. |

A later authorized synthetic run must use the exact tested source and destination revisions, an isolated destination and fresh delivery identities. Use only fabricated HR/SDNN data. Before exercising write or fault cases, record the empty baseline, expected permissions, storage budget and restoration target. The current audit does not execute any of these cases.

1. **Commit and reconciliation.** Intake the baseline fixture. Verify original bytes and SHA-256 after reopening custody. Reconcile exact scope, batch, artifact digest, byte length, source schema, bound export, receipt and transaction identities. Match the live observation, historical revision and tombstone sets against the independent oracle.
2. **Lost response and conflict.** Interrupt after durable commit and before acknowledgment. Reopen and retry identical bytes under the original scoped batch. Require the same commitment identity and clocks with no duplicate artifact, logical revision or cursor movement. Change the bytes under the same identity and require a conflict. Mutate subject, source, batch and digests independently and verify no cross-scope acceptance.
3. **Interrupted commit and reopen.** Interrupt between artifact custody, ledger and normalization at each actual write boundary. Restart and reconcile orphan blobs, missing bindings and incomplete normalization. Require a documented pending or quarantined outcome until exact reopen evidence supports successful normalization.
4. **Restore.** Back up a checkpoint containing the original bytes, artifact/ledger bindings and normalized archive state. Restore into a separate isolated target. Verify byte hashes, receipt IDs and clocks, exact revision/tombstone sets, cutoff views and retry behavior. Record elapsed recovery time and the last recoverable commit against the proposed recovery objectives.
5. **Field parity.** For HR (`bpm`) and HRV SDNN (`ms`), match the native UUID, metric, original value/unit and numeric lexeme or lossless locator, interval start/end, source name/bundle, and collector receipt time. Reconcile embedded `deletedAt` and UUID tombstone values separately, preserving distinct times, unknown-UUID deletions and source locators. Preserve opaque anchors and backfill metadata as capture provenance. Check decimal and timestamp conversions for recorded loss. Keep missing device, calibration, source revision and permissions unknown. Keep collector receipt, MOTHER receipt and durable commit clocks separate.

Use PHOENIX's **NOT READY** or **READY FOR SYNTHETIC QUALIFICATION** disposition with exact gaps and owners. This checklist supplies no production or real-data qualification.

## ATLAS 0.2 compatibility check

Fetch `git fetch origin pull/28/head` and ensure the exact object
`928a60b704c342c091eabd25ba41c8eb84d562de` is available. The acceptance
suite independently reconstructs the nine candidate golden preimages and
binds raw artifact length/digest and decoded anchor digests. Receipt mutation
checks cover lookup scope, archive and batch, and show why a stable lookup ID
alone cannot establish the unchanged artifact/export binding. These are
digest checks. JSON Schema validation, authoritative receipt rejection and
combined implementation execution remain separate.

Candidate implications for the fixture oracle: count distinct deletion facts
at exact source times even if display UTC ties, and deduplicate equivalent
facts while retaining all locators. Unknown-derivation HR must survive in the
physiological snapshot but be excluded from the native MSE projection. The
current fixtures contain no independently verified measured-HR evidence.
