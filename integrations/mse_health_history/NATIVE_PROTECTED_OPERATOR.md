# Protected native archive import qualification

This offline source candidate is separate from the running 8446 pilot,
the frozen 8448 mTLS package and the 8447 ciphertext receiver. It neither
starts a service nor requests phone access. The CLI currently restricts
enrollment and source identity to synthetic values. Independent review
and an explicit protected execution plan are prerequisites for any actual
archive parsing.

## Custodian boundary

Before an authorized execution, independently verify the protected,
non-synced scratch and typed volumes, owner isolation, exact age executable
and recipient, detached age identity and private provenance key, filesystem
capacity, and the trusted 8447 raw receipt and original plaintext pins.
The program checks ownership/private paths, digests and available scratch
space. It cannot attest filesystem encryption or native export privacy.
Keep the age identity and protected raw originals off the archive VM's
network receiver and outside the consumer boundary.

The runner streams age output into an anonymous file on the explicitly
chosen protected scratch volume. Do not point scratch at an ordinary
temporary directory. Nothing reaches the parser until age exits
successfully and the plaintext digest and length match. The ciphertext is
checked before and after decryption. Scratch closes on exit. An exact
authenticated replay returns the same receipt; interrupted typed work
rolls back and may be repeated from the same exact source. There is no
plaintext-original copy under the typed destination. A refused typed
archive leaves the separately retained ciphertext untouched.

## Synthetic commands

Use an empty private typed directory and a private scratch directory on
approved storage. The 32-byte provenance and consumer keys have separate
custody. The private binding JSON contains only `receipt`,
`recipient_fingerprint`, `plaintext_sha256`, `plaintext_length` and
`age_sha256`. Supply the same root, enrollment, source instance and
provenance key on reopen. If a separately qualified BP API backfill also
uses this catalog, pin its own `--bp-cutoff` when initializing.

```sh
python -B -m integrations.mse_health_history.native_runner init \
  --root "$typed_root" --enrollment synthetic-native-review \
  --provenance-key-file "$provenance_key"

python -B -m integrations.mse_health_history.native_runner import \
  --root "$typed_root" --enrollment synthetic-native-review \
  --provenance-key-file "$provenance_key" --scratch-root "$protected_scratch" \
  --custodian-binding "$private_binding" --ciphertext "$verified_ciphertext" \
  --identity-file "$detached_identity" --age-executable "$pinned_age"

python -B -m integrations.mse_health_history.native_runner snapshot \
  --root "$typed_root" --enrollment synthetic-native-review \
  --provenance-key-file "$provenance_key" --purpose mother-bp-cgm-review \
  --consumer-key-file "$consumer_key" --start "$window_start" --end "$window_end" \
  --output "$protected_output/new-bp-snapshot.sqlite3"
```

Use approved UTC bounds and a fresh output path. A consumer opens the
resulting SQLite database with `mode=ro`. The protected catalog offers
`members`, `coverage`, `blood_pressure_lineage` and `blood_pressure`
history/current reads. The lineage query attaches exact artifact,
member number, top-level ordinal and normalized revision to each BP
sighting. The consumer snapshot includes explicit current pairs only and
uses a purpose-specific pseudonym and time alignment. Dates and physiology
can still identify a person. No direct names, UUIDs, paths, device metadata
or raw originals appear in that consumer snapshot. The snapshot command
does not request Nightscout.

## Inventory and typed limits

XML and ZIP inputs are bounded by file/member/directory/expansion/ratio
limits and XML depth, lexical token, element and type-bucket limits. ZIP
entries are never extracted to named paths. Duplicate/equivalent paths,
path escape, special members, unsupported encodings and invalid local/central
pointers refuse. Inline Apple Health DTD element declarations are allowed.
The inline declaration subset is byte-bounded. Default and fixed
attribute values, entity declarations and external resolution are refused.
Only explicitly supplied attributes reach classification. Embedded file-reference attributes are inventoried without
following the path. Archive members, top-level source occurrences and
nested occurrences are separate counts. Family labels report evidence
present in the input. An absent family does not establish lack of
permission, API support or source data. Unknown rows and attachments retain
custody without invented typed facts.

BP uses only explicit correlation membership. Exact original mmHg strings
are retained in the restricted typed lineage beside canonical decimal
values and source clocks. Incomplete, ambiguous and standalone components
remain separate. If a BP row cannot normalize, report it as unnormalized
and increment the BP invalid count. Unlinked pulse remains unassociated.
Native XML with no verified UUID has only export-local occurrence
identity. Equal values and clocks never cause automatic pairing or
deduplication. Within an independently proven same-store enrollment an API
tombstone can suppress a matching explicitly identified component from
current pairs without erasing historical sightings. No overlap is inferred
with another store or the live pilot. This candidate does not normalize
non-BP families, interpret arbitrary attachment content, or claim whole
phone coverage. No backup/restore work is included.
