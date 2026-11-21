# BP-first transport decision and interface proposal

Use a bounded custodian file exchange and a separate VM typed writer. There
is no phone-facing BP listener in this increment. The phone's recent live
enrollment, 8445/8446 services, keys, credentials and anchors are separate.
The full native Health ZIP is not a prerequisite for BP.

## Phone interface for ORACLE

For each approved historical BP feed, persist the exact UTF-8 page bytes
and candidate checkpoint before transferring one page. The protected phone
handoff exports one document, `bp-page.json`, with bytes from the staged
page. Do not wrap, pretty-print, regenerate, or put an actual HKQueryAnchor
into that document. Use the separately approved private file handoff to a
custodian. No automatic upload, direct credential import or app-wide file
sharing is required for this route. Until a valid receipt is imported, keep
the same bytes and leave the durable anchor unchanged.

Configure the historical writer with the expected `archive_id`,
`enrollment`, `source_instance`, fixed historical `through`,
`page_schema_sha256`, and a separately provisioned
`typed_receipt_ed25519_public_key` (32 raw public-key bytes encoded
unpadded base64url). These pins are independent of the live consent,
pilot times and server credentials. The transport does not pick a page
schema on the phone's behalf. The current FORGE synthetic schema and the
ATLAS/ORACLE envelope still need a single shared pin and conformance vector.
That is a release gate for exact page serialization and receipt-field
validation. The file exchange can be built independently of this gate.

The final phone import is a single `bp-receipt.json` with exactly
`receipt_bytes_base64url` and `signature_base64url`. Decode both as strict
unpadded base64url. The detached Ed25519 signature covers the exact decoded
receipt bytes, with no reserialization. After signature validation, require
the pinned typed receipt schema and success status. Validate expected
archive/enrollment/source store, cutoff, feed and page sequence, exact
pending page digest and byte length, incoming/outgoing checkpoint tokens,
terminal flag, and ciphertext custody binding. Reject a raw vault receipt
as a typed success. Only then atomically promote the protected
token-to-anchor mapping. The initial incoming checkpoint token is null;
an empty successful query completes its feed only after receipt import.
Completion of the three feeds is a traversal result, separate from actual
permission, source visibility and coverage.

Suggested app integration signatures for source review:

```swift
func exportPendingBPPage(feed: HistoricalBPFeed) throws -> Data
func importDurableBPReceipt(_ document: Data, feed: HistoricalBPFeed) throws
```

## Custodian and VM handoff

1. Receive the exact staged page in the approved protected custodian
   directory. Hash and count the original. Seal it to the approved public
   age recipient, with the detached identity outside the VM. Upload
   exact ciphertext under a finite, single-object vault enrollment via
   8447 and retrieve its witnessed raw receipt. Qualified BP pages and
   bulk Health ZIPs use separate enrollments. A raw receipt never advances
   a phone checkpoint.
2. In the custodian boundary, authenticate the exact witnessed ciphertext
   and verify the decoded page digest and length before deriving typed facts.
   Pass the VM only a detached Ed25519-signed typed bundle with bounded BP
   observations, tombstones, protected source references, ordered checkpoint
   metadata, exact page identity and the witnessed ciphertext receipt. Keep
   original JSON bytes, raw source metadata, the linkage key and the
   decryption identity off the VM. Never send these to consumer storage.
3. The dedicated VM writer would receive that bounded file through a
   separate restricted operator drop, with no new network listener.
   Reject unknown signing keys, other enrollments, excessive files,
   invalid shapes, conflicting duplicate sequences, absent or mismatched
   raw custody, and stale checkpoint tokens. Bind the raw receipt from
   authenticated receipt-role readback. In one SQLite transaction commit
   typed records/tombstones, current-view updates, page identity,
   checkpoint and typed receipt. Only after durable reopen, sign the
   stored receipt with the VM's dedicated receipt signing key. Return
   the exact signed document to the custodian's protected return path.
4. An exact repeat of an already committed page returns the same durable
   receipt. An orphan ciphertext object or lost typed response never
   authorizes a new cursor. Recover by inspecting witnessed ciphertext
   and typed receipt status using the same page identity. Resume only
   by retrying the identical approved bundle. Do not repair by inventing
   a page sequence, anchor, or relationship between source records.

Proposed VM bundle envelope `mse.historical-bp-typed-bundle/0.1` has
`archive_id`, `enrollment`, `source_instance`, `through`, `feed`,
`page_sequence`, `cursor_in`, `cursor_out`, `exhausted`,
`page_schema_sha256`, `page_sha256`, `page_byte_length`,
`ciphertext_receipt`, `typed_upserts` and `typed_tombstones`, plus
the `schema_version` discriminator. Transfer the exact UTF-8 bundle and
a separate detached 64-byte Ed25519 signature. One staged bundle per feed,
maximum 1 MiB per phone page or VM bundle and 128 entries per page.
The two signatures use distinct custody roles. The VM pins the custodian's
public signing key; the phone pins only the VM's receipt public key.
Neither signing key is an age identity or an upload grant.

The VM configuration needs its own dedicated state and operator-drop
roots under verified protected storage, fixed enrollment and sample
cutoff, expected archive identity, approved schema digests, custodian
public-key pin, local receipt-signing key location, and finite access to
the ciphertext receipt role. It must have no decryption key, original
store linkage key, or permission on current live and synthetic stores.
Plaintext typed physiology still needs protected storage and read access
separate from the consumer projection.

## Verified boundary

The receiver package implements ciphertext custody only. The existing
synthetic custodian-side catalog has authenticated a sealed page and
committed typed facts and cursor locally in tests. The signed typed
bundle exchange, VM writer, receipt signing, phone document return and
exact cross-language contract are proposed interfaces. They have not
been implemented end to end or qualified for use with actual Health data.
Before capture, demonstrate a fabricated Swift page through exact
ciphertext custody, custodian authentication, VM typed reopen, signed
receipt import and checkpoint advance, with tampered and lost receipt
cases. No environment or phone change is implied by this decision.
