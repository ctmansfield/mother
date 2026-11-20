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
