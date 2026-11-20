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

## Verify a synthetic capture from the command line

Run from the repository root with a local synthetic fixture. The CLI reads
only stdin, stops after the byte limit plus one byte, and opens no ledger
or output file. It prints one deterministic JSON summary containing the
artifact and export digests, byte length and counts. The summary omits
scope, records, numeric values, and detailed loss locators. Keep even the
digests in local custody when applicable.

```sh
python3 -B -m integrations.healthbridge \
  --subject-id synthetic-demo --source-instance demo-store \
  --batch-id batch-1 --capture-id capture-1 --capture-kind full_file \
  < synthetic-healtharchive.json
```

Defaults are 4 MiB, 20,000 records, nesting depth 32 and numeric-token
length 256. The respective `--max-byte-length`, `--max-records`,
`--max-depth` and `--max-numeric-token-length` options can reduce them.
Exit 0 means the export was constructed, exit 1 rejects the capture or an
input read, and exit 2 denotes invalid arguments. Error text omits source
bytes and invalid argument values. For a durable synthetic trial use the
existing `ingest_capture` Python entry point above.

### PF-001 numeric projection

Exporter `healtharchive-capture:0.2.1` accounts for the auxiliary PF-001
binary64 projection of eligible positive observations. Comparison uses the
exact binary64 value against the exact source decimal. It detects both
subtle rounding such as decimal 0.1 and changes visible in the serialized
numeric value. Findings use the frozen 0.2 loss shape and identify the
`original_value` and `value` fields at their original reading pointer.
Exact decimal values, original lexemes and source revision identities are
unchanged. Timestamp rounding remains a separate finding.

The projection helper returns no usable float for overflow or underflow to
zero. The exporter marks this explicitly. The FORGE writer must omit those
records while preserving source evidence. Reconstruction of historical
exports must explicitly use `healtharchive-capture:0.2`, which keeps its
original loss behavior. Do not rewrite older receipts with the new exporter.

## Output and custody boundaries

For a status check outside the local evidence transcript, use
`--status-only`. Success then prints only `{"status":"valid"}` and retains
the same exit codes. The default summary's digests, counts and size are
linkable evidence and belong in a restricted transcript. The CLI opens no
file by name, prints no capture content, and accepts synthetic inputs only.

The original and full export are separately restricted. The original may
contain native UUIDs, exact measurement and receipt times, source and bundle
strings, opaque query anchors, unknown extension names and values, and
deletion UUIDs/times. The export additionally binds subject/store, capture
and batch tokens; it carries canonical UUIDs, clock/value representations,
source/bundle strings, stable digests and original locators. A deletion
pointer can contain a UUID, and an extension pointer can contain an
arbitrary source key. Structured device, calibration and availability
fields are null for this capture shape; source strings or unknown original
extensions can still carry identifying material. Missing structured fields
cannot establish anonymity.

The library performs no logging. Its capture and delivery wrappers suppress
field-bearing default representations. Callers should log an approved
status category and keep full exports, receipts, exceptions and tracebacks
in restricted custody. Parser errors are sanitized, while downstream
validation exceptions may contain the rejected instance. The full export
is authoritative exchange input and is unsuitable as an analytics or
telemetry view. Any reduced-identity projection needs a separate reviewed
contract and must not rewrite this evidence.
