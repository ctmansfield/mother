# Historical health source candidate

This source-only increment implements synthetic native Apple Health XML/ZIP
inventory, paired blood pressure, an independent ciphertext receiver, and
a read-only Mother/Coach projection. It shares no live pilot configuration,
store or grant. No actual device measurement or Nightscout endpoint was used.

## Raw intake and coverage

See [ciphertext receiver lifecycle](VAULT_OPERATOR.md). Opaque ciphertext
custody occurs before type parsing and is independent of whether a parser
understands any bytes. The synthetic XML/ZIP scanner hashes the original,
then each safe member and attachment. It never extracts ZIP paths to disk.
It checks archive, central directory, member/expansion, row/depth and
XML-token bounds, rejects ambiguity and special files, and checks member
length and original stability. Inline Apple Health DTD declarations are
permitted without entity declarations, parameter entity parsing, or external
resolution. Unsupported declarations or shapes prohibit typed publication
and do not erase a separately received ciphertext original.

Coverage counts actual XML top-level occurrences and member files by type.
Correlation components and unsupported children are counted separately.
Types with zero observed rows are unverified until the source inventory can
distinguish not available, unsupported API/OS/entitlement, permission unknown,
or no visible data. The candidate normalizes only paired/incomplete/ambiguous
BP correlations and standalone BP components. Other quantities, categories,
correlations, characteristics, workouts, activity, routes/series, ECG,
audiogram, vision and clinical/medication families are retained or reported
as observed/unmapped when present. Attachments are separately counted and
hashed; none is silently interpreted. The native export's actual coverage,
owned entitlement gaps, and supplemental API capture remain unqualified.

## BP page and durable cursor seam

Draft wire `mse.historical-bp-page/0.1` binds a separate enrollment and
canonical UTC cutoff, feed (`correlation`, `systolic`, `diastolic`), prior
and next SHA-256 cursor digests, typed upserts and deleted UUIDs. Initial
prior cursor digest is JSON null. Canonical sample times have six UTC
fractional digits and canonical BP scalar strings express mmHg. A nullable
scalar cannot complete a pair. Correlation membership is explicit.
Unassociated pulse is not attached to a BP pair. Each API UUID and its
bounded source/sync provenance are protected; published consumer rows omit
those identifiers. Native XML UUIDs are optional. Without a reliable UUID,
identity is original digest, member and ordinal within the historical
enrollment. Equal times or values do not prove duplication or live overlap.
Conflicting native-key revisions remain in history and are withheld from
the default current view without an authoritative revision policy. The
existing 14-type pilot has no BP feed, and broader cross-live linkage needs
separate source namespace proof and qualification.

A terminal empty page sets `exhausted:true`, includes no upserts/deletes,
and still binds its next digest. It may keep the prior digest. A nonempty
page must advance. A completed feed accepts exact retry only. The backend
does not read or store opaque phone anchor bytes. A successful typed receipt
has `schema_version:mse.historical-bp-page-receipt/0.1` and
`status:typed_and_cursor_durable`, exact plaintext digest/length, archive,
enrollment, cutoff, feed, prior and next cursor digests and exhaustion.
The authorized sealed route additionally binds the independent durable
ciphertext receipt for the exact authenticated plaintext. The custodian
decrypts off-guest with the verified age executable and detached key. The
typed/cursor transaction begins after successful authenticated decrypt and
plaintext pin match. Exact retry reproduces the receipt. The client must
validate it before advancing its locally protected cursor.
This seam still needs ATLAS/ORACLE wire signoff and independent signed-app
data-to-page verification.

## Pseudonymous consumer boundary

A separate purpose-only SQLite snapshot contains vetted BP pairs and bounded
synthetic Nightscout SGV projections, with a distinct HMAC subject per purpose
and 15-minute UTC alignment. A common time bucket does not establish sample
pairing or a causal relationship. Consumers open the snapshot SQLite
read-only with filesystem isolation. No source IDs, device information,
locations, raw rows, mapping keys or endpoint credentials are included.
Exact physiology and temporal patterns can still identify an individual.
Blood pressure projection requires an explicit pair and excludes conflicted
and tombstoned keys or components. The SGV experiment uses local fabricated
files, known units and exact source-time conflict checks.

Use a separately authorized Nightscout ingestion lane into the protected
pseudonymous projection for future Mother/Coach testing. Direct reading
would put provider credentials and schema inside the consumers. The existing
[Nightscout source qualification](https://github.com/ctmansfield/mother/issues/10)
remains scoped and does not approve current access or complete history. A
future request needs a named source/collection, authorized finite range,
least-privilege grant, pagination/revision proof, explicit unit evidence, and
separate access/custody review.

## Synthetic test entry point

```sh
MSE_HISTORY_AGE_BIN="$verified_age_binary" \
  python -B -m unittest discover -s tests/integration/mse_health_history -v
```

The age test generates isolated synthetic keys and ciphertext. With no age
binary supplied, that test skips explicitly. No capture, user export request,
installation, key transfer, projection deployment or backup/restore is
part of this source candidate.
