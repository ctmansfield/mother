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
first sighting's payload. Other sightings remain recoverable from original
bytes. The export's coverage and unavailable fields stay explicit. Heart-rate
derivation is unknown, and SDNN is vendor-derived. Zero values remain in the
capture evidence with a reference exclusion. Negative values are rejected
under the candidate's unsigned decimal schema; disposition of other otherwise
valid out-of-domain values awaits contract review. Anchor keys from the
collector are translated from `heartRate` and `hrvSDNN` to the draft labels.
Other anchor labels are preserved in the original bytes and reported as a loss.
This draft establishes neither PF-001 acceptance nor MSE projection.

Run the standalone synthetic checks from the repository root.

```sh
python3 -B -m unittest discover -s tests/integration/healthbridge -v
```

[atlas]: https://github.com/ctmansfield/mother/blob/3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c/docs/mse/integration/contracts/README.md

## Local adapter-to-ledger integration

`ingest_capture` accepts a configured FORGE `IngestV02` service and the public
FORGE mapper callable `map_export(export, context)`. The service supplies the
expected scope. The adapter constructs the export from the original bytes and
checks the retained bytes, digest and scope before invoking the mapper. It then
compares the authoritative receipt against the same artifact and export and asks
the service to verify it from reopened custody. The result contains the export
and verified receipt. A quarantined receipt remains quarantined.

For integration tests, assemble the adapter paths into a disposable checkout of
the pinned FORGE PR #31, which includes PF-001 PR #18. Do not use a separate
checkout on PYTHONPATH alone because the existing `mother` package can shadow
PF-001. Supply these local paths and run the unittest command above.

- `MSE_ATLAS_CONTRACT_DIR` points at PR #28 contracts at
  `3fe247446f03b7ee3e8a36a0a18bd19eb5a1329c`.
- `MSE_HEALTHBRIDGE_FIXTURES` points at PR #25 fixture directory at
  `4ba53e16185f3620a239b70cefbc2e03292552e2`.
- `MSE_FORGE_MAPPER` is the production-path FORGE mapper in module:callable
  form. Until its pinned implementation is available, accepted fixture tests
  are skipped. The invalid fixture checks still use the actual ledger service
  and assert that neither custody nor archive is created.

PF-001 schema validation requires the FORGE Python environment with jsonschema.
The adapter itself has no added Python dependency.
