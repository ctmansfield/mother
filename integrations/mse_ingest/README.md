# Local MSE ingest harness

This synthetic harness depends on the PF-001 implementation in PR #18 at
`b4e70b7123689ec164ba09e2974645ae36b184a2`. Select a dedicated private local
directory for the pair of SQLite files. Keep both files together. PF-001 is the
physiological archive. The custody journal stores exact incoming bytes and
receipt state so interrupted delivery work can resume. The trial retains those
bytes in both custody and PF-001 after acceptance. Storage policy is open.

`LocalIngest.ingest` takes the caller's scope, batch identity, exact original
bytes, export digest, source schema, adapter version and trusted local
normalizer. The callback receives the retained bytes and a run context. It
constructs PF-001 revisions and records for that context and returns the two
collections without writing to either database. The harness derives the PF-001
source namespace from the whole scope. The callback must compute revision
identities in that namespace and bind each source revision to the artifact
digest. The caller currently supplies the export digest. Verification against
the actual shared export and complete export mapping are downstream integration
work.

Custody is committed first. A short-lived journal writer lock serializes the
PF-001 step and receipt publication. A reopen can locate a previously created
run by its stable receipt correlation. Pending work requires the identical
original delivery and the same versioned normalizer on retry. Once PF-001
commits, the journal verifies run, artifact and member linkage before publishing
a receipt. The receipt sequence orders finalized local journal receipts.
`committed_at` comes from PF-001 archive completion. A retry after response loss
reopens the same receipt and verifies archive linkage. Conflicting input leaves
the existing commitment unchanged. Normalization errors leave custody pending
and propagate to the caller. The public receipt encoder currently covers
successful normalization only and follows provisional ATLAS draft 0.1.

Run from the repository root in an isolated Python environment with PF-001's
`jsonschema>=4.18` dependency installed:

```sh
python -B -m unittest discover -s tests/integration/mse_ingest -v
```

Tests use local temporary directories, synthetic records, real PF-001 JSON
Schema validation and injected exceptions at the durable boundaries. Those
checks do not exercise process termination, power loss, backup/restore or
filesystem failures. This interface has no listener, transport authorization,
retention or acquisition checkpoint. Use the harness only for the offline
synthetic trial.

## Provisional ATLAS 0.2 boundary

Use `IngestV02` in a fresh private trial directory with a configured archive ID,
expected scope and the exact ATLAS #28 schema. The caller supplies the parsed
0.2 export and a trusted local mapper. The harness validates the envelope,
original byte digest/length, scoped source fact digests and canonical export
digest before custody. The mapper binds each PF-001 source row through
`mse_source_revision_sha256` in its canonical raw JSON. Unknown-derivation HR
stays in source evidence without an invented PF-001 observation class. The
combined ORACLE adapter and processing-revision mapping need separate
acceptance.

The deterministic external ID binds archive, scope and batch. Internal run
correlation is independent. Custody and terminal normalization/quarantine
are separate durable stages with journal sequences and UTC clocks.
`read_receipt` and `verify_receipt` reopen the configured store before trusting
an authoritative receipt. Validation failures before custody raise errors and
issue no durable stage. The application-specific rejection response and
quarantine taxonomy are pending shared contract review.

The local `facts_at` helper selects earliest accepted sightings through a
journal cutoff, preserves distinct delete facts including unseen UUIDs and
suppresses upserts at and after a committed deletion. It does not construct
the complete exchange snapshot or select a processing version. The trial
stores remain disposable.

Run the original suite and the 0.2 golden tests by setting
`MSE_ATLAS_CONTRACT_DIR` to a checkout of the contracts directory at
`928a60b704c342c091eabd25ba41c8eb84d562de`. Keep that separate checkout or
download outside this repository. With no contract path the five golden
tests are skipped.

```sh
MSE_ATLAS_CONTRACT_DIR=/path/to/pinned/contracts \
  python -B -m unittest discover -s tests/integration/mse_ingest -v
```
