# Synthetic captured HealthArchive adapter

`normalize_capture` accepts immutable UTF-8 bytes from a caller-owned coherent
capture, together with explicit synthetic subject, source-instance and batch
tokens and the capture kind. It returns a new exchange object and performs no
file, database or network operations. The caller must retain the original bytes
separately and check the artifact byte length and SHA-256 at custody. The
adapter cannot establish that a caller's capture was atomically taken.

`capture.py` parses the collector format at MotherHealthBridge
`9b85cf1a12ecb1f91f414e8f5366d81f3dbb81d6`. The local prototype rejects inputs
greater than 4 MiB and source numbers outside its bounded decimal parser range.
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

`export.py` is the provisional exchange boundary for [ATLAS draft 0.1][atlas].
The raw digest is the provisional capture ID. The provisional revision digest
also binds exact source times, excluding locators and receiver clocks. Distinct
source times therefore survive UTC rounding. This preimage is defined here for
adapter testing and remains subject to joint contract review. Heart-rate
derivation stays unknown under dispatch revision 2. SDNN stays vendor-derived.
This draft establishes neither PF-001 acceptance nor MSE projection.

Run the standalone synthetic checks from the repository root.

```sh
python3 -B -m unittest discover -s tests/integration/healthbridge -v
```

[atlas]: https://github.com/ctmansfield/mother/blob/a732adda92cc79659bf2413c7d45891cf2d13264/docs/mse/integration/contracts/README.md
