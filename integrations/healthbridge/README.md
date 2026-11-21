# Synthetic captured HealthArchive adapter

`normalize_capture` accepts immutable UTF-8 bytes from a caller-owned coherent
capture, together with explicit synthetic subject, source-instance and batch
tokens, an explicit capture ID and the capture kind. It returns a new exchange object and performs no
file, database or network operations. The caller must retain the original bytes
separately and check the artifact byte length and SHA-256 at custody. The
adapter cannot establish that a caller's capture was atomically taken.

`capture.py` parses the collector format at MotherHealthBridge
`9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6`. Caller-configurable byte, record, nesting and numeric token limits have local
synthetic defaults. Source numbers must fit the bounded decimal parser range.
Numeric Date tokens are interpreted as exact decimal seconds since 2001-01-01
UTC, with ties-to-even microsecond rounding. Locators recover the original date
tokens from the original bytes. Rounded fields produce a loss entry. Measurement
values retain the original number lexeme and an exact decimal representation.
Anchors contribute only digests of the decoded opaque bytes. Unknown metadata,
extension fields and permission coverage stay explicit. Observed limits describe
only exported readings.

Identical upserts and equal delete facts combine their original locators.
Unequal upserts for one UUID fail. Distinct embedded and dictionary deletions
remain distinct even when rounded UTC matches. An unobserved UUID may have a
tombstone. Partial and empty captures imply no deletion for missing UUIDs.
The adapter emits captured facts. The downstream archive determines a current
projection and authoritative commitment.

`export.py` implements the exchange and digest rules in [ATLAS draft 0.2][atlas].
Caller-assigned capture and batch identities are separate from the raw SHA-256.
The source revision digest binds exact numeric facts, independently of date
rounding, number spelling, collector receipt drift or capture location.
Repeated equivalent upserts within one capture retain all locators and use the
lowest numeric reading-index sighting's entire payload. Other sightings remain recoverable from original
bytes. The export's coverage and unavailable fields stay explicit. Heart-rate
derivation is unknown, and SDNN is vendor-derived. Finite nonpositive values remain in the capture
evidence with an explicit source-only exclusion. Anchor keys from the
collector are translated from `heartRate` and `hrvSDNN` to the draft labels.
Other anchor labels are preserved in the original bytes and reported as a loss.
This draft establishes neither PF-001 acceptance nor MSE projection.

Run the standalone synthetic checks from the repository root.

```sh
python3 -B -m unittest discover -s tests/integration/healthbridge -v
```

[atlas]: https://github.com/ctmansfield/mother/blob/769a0966da251da4d08633cc7663af9869da70e6/docs/mse/integration/contracts/README.md

## Local adapter-to-ledger integration

`ingest_capture` accepts a configured FORGE `ConnectedIngest` service. The service supplies the
expected scope. The adapter constructs the export from the original bytes and
passes it to the public `ingest_export` entry point. The service validates custody
and maps PF-001 revisions and records. The adapter compares the returned receipt
against the same artifact and export and asks the service to verify it from
reopened custody. The result contains the export
and verified receipt. A quarantined receipt remains quarantined.

For integration tests, assemble the adapter paths into a disposable checkout of
FORGE PR #31 at `d2441050726f1b3f50c928d5f8205d5ea179276d`,
which includes PF-001 PR #18. Do not use a separate
checkout on PYTHONPATH alone because the existing `mother` package can shadow
PF-001. Supply these local paths and run the unittest command above.

- `MSE_ATLAS_CONTRACT_DIR` points at PR #28 contracts at
  `769a0966da251da4d08633cc7663af9869da70e6`.
- `MSE_HEALTHBRIDGE_FIXTURES` points at PR #25 fixture directory at
  `13d2e19825aa872c04cf174cd8adef1bc8d40756`.
PF-001 schema validation requires the FORGE Python environment with jsonschema.
The adapter itself has no added Python dependency.
