# Separate private typed BP history service

This service supersedes the earlier proposed file exchange. It implements
[ATLAS r3](https://github.com/ctmansfield/mother/pull/23#issuecomment-7058180458)
and is separate from the opaque bulk receiver on 8447 and live pilot on
8446. The phone sends one approved exact page over verified private TLS. The
server validates it, seals its original using public-only age, and commits
ciphertext, typed lineage, checkpoint and receipt together. Only the
post-commit pre-cutoff witness makes them visible. The server returns a pending status before independent off-VM verification.

## Exact app wire and private witness

Use the pinned [canonical page and receipt schema](bp-page.schema.json) and
[synthetic vector](bp-http-vectors.json). The PUT and GET route is
`/v1/bp-history/enrollments/{enrollment_id}/streams/{feed}/pages/{page_seq}`.
Each configured stream ID maps to one of `correlation`, `systolic`, `diastolic`. Sequence
is a positive path integer beginning at 1 independently per feed. The
body contains no sequence field. The server binds it to the body's trusted
enrollment, source instance, feed, fixed historical cutoff and opaque
cursor chain. The approved native anchor stays local. Transport UTC and
historical sample cutoff are separate. The candidate caps a page at 1 MiB
and 128 upserts plus deletions, matching the canonical parser. Standard
HTTPS validates the hostname. No redirect, compression or chunked upload.

- PUT needs the upload bearer. A new or exact pending PUT returns 202
  with the exact bounded `mse.historical-bp-page-pending/0.1` envelope and
  status `awaiting_custodian_witness`. It never advances the phone cursor. Exact accepted PUT replay returns 200, changed bytes
  under an existing sequence return 409. Only one unwitnessed staged page
  is allowed per enrollment in this candidate.
- GET with a distinct finite receipt bearer returns 202 in-window while
  durable custody awaits verification, 200 for a typed durable receipt,
  403 for an expired unaccepted page, or 404 for an unknown page. No receipt body is
  returned for sealed or unverified data. Operator export needs its own
  grant and returns only witnessed typed facts. The phone validates the
  exact receipt hash/length, enrollment/archive/store/cutoff/feed, cursor
  echo, counts, completion and ciphertext binding before promoting its
  protected local checkpoint.
- Custodian GET and PUT use only the page path plus `/custody`. The
  guest verifies a dedicated client CA and the exact enrollment-pinned
  leaf DER SHA-256. The phone bearer conveys no custody authority. GET
  returns the closed witness template, the immutable ciphertext receipt,
  and standard base64 ciphertext in a bounded JSON envelope.
- The custodian compares the trusted local page binding and authenticates
  the immutable ciphertext with the pinned `sealed_page.authenticate_page`
  helper and its detached age identity. It then sends the exact closed
  UTF-8 witness object as PUT `/custody` with application/json over mTLS.
  The service persists the authenticated certificate fingerprint, exact
  witness bytes and SHA-256. An exact replay returns the stored decision;
  altered witness bytes or bindings fail. Only a typed decision and
  checkpoint observed durable before cutoff can publish a receipt.

## Guest configuration and commands

Use a dedicated nonlogin account, new 0700 canonical state root on approved
protected storage, separate private bind/relay with exact phone and operator
peer rules, and guest-terminated TLS at explicit port 8448. The SQLite
file contains plaintext typed BP facts and encrypted originals. Restrict
the mount and account independently. Verify trusted guest UTC at each
start and during the lease. Transport lease and sample snapshot are
independent. Apply the frozen sample-start predicate to admitted API rows
as specified by ATLAS. Store observed times unmodified. The predicate is
not a guarantee of transactional HealthKit snapshot completeness.

The service-owned private JSON config contains exactly these fields
(example placeholders, no actual acceptance authority):

```json
{
  "bind": "<assigned RFC1918 IPv4>",
  "archive_id": "demo-archive",
  "enrollment_id": "demo-enrollment",
  "source_instance": "demo-store",
  "streams": {"correlation": "correlation", "systolic": "systolic", "diastolic": "diastolic"},
  "snapshot": {"sample_start_at": null, "sample_end_before": "2026-11-21T00:00:00Z"},
  "transport_starts_at": "2026-11-22T00:00:00Z",
  "transport_ends_at": "2026-11-22T02:00:00Z",
  "enabled": false,
  "max_pages": 1000,
  "max_bytes": 1073741824,
  "reserve_bytes": 1073741824,
  "age_executable": "<trusted absolute path>",
  "age_sha256": "<digest of architecture-specific age executable>",
  "recipient_file": "<service-owned private file with one public age recipient>",
  "recipient_sha256": "<digest of exact recipient file>",
  "provenance_key_file": "<service-owned private file with 32 random bytes>",
  "custodian_ca_file": "<dedicated client CA bundle>",
  "custodian_cert_sha256": "<exact enrolled leaf DER SHA-256>",
  "grants": {
    "upload": {"sha256": "<digest>", "expires_at": "2026-11-22T02:00:00Z"},
    "receipt": {"sha256": "<digest>", "expires_at": "2026-11-22T03:00:00Z"},
    "export": {"sha256": "<digest>", "expires_at": "2026-11-22T03:00:00Z"}
  }
}
```

Use independent random 32-byte bearer values, encoded unpadded base64url.
Keep only their digests in guest config. The provenance key is not an age
identity. The detached private age identity stays off guest. The quotas
exclude ongoing free-space/typed growth monitoring. Choose and verify a
protected mount budget before enable.

```sh
python -B -m integrations.mse_health_history.bp_server init --root "$bp_root" --config "$bp_config"
python -B -m integrations.mse_health_history.bp_server serve --root "$bp_root" --config "$bp_config" \
  --bind "$assigned_guest_ipv4" --port 8448 --cert "$leaf_chain" --key "$leaf_key"
```

Initialize once on an empty root. Ordinary restart uses only serve and the
same enrollment, root and fixed lease. Stage disabled. No data or phone
transfers before the approved release. At cutoff no fresh bytes can be
accepted. Unwitnessed rows remain sealed and absent from operator reads.
Restart cannot synthesize a witness. A late proof-only commit can finish
a decision witnessed before cutoff. It adds no original, facts or sequence.
A staged outstanding page blocks later uploads for restricted reconciliation.
A durable custodian proof without a publication witness is an indeterminate
hold. During the transport window, exact phone retries and receipt lookups,
along with custodian reads and commits, return HTTP 503 with
`{"error":"indeterminate"}`. After cutoff, unaccepted pages return HTTP 403.
Keep the protected phone queue and checkpoint, ciphertext, receipts, proof,
and database with its journal intact. Escalate to the archive operator for
read-only reconciliation by archive, enrollment, stream, sequence, and
digest. Only a persisted, valid, in-window publication witness establishes
acceptance. A proof alone never advances a checkpoint or authorizes repair.
For a lost response after publication, the scoped receipt lookup returns the
same durable receipt, including after upload cutoff.

Pin [upstream age v1.3.2](https://github.com/FiloSottile/age/releases/tag/v1.3.2).
Verified Linux release archive and executable SHA-256 values are below.
Check the architecture, independent provenance and actual guest version.
The runtime package excludes binaries and private data.

| Linux architecture | Archive SHA-256 | age executable SHA-256 |
| --- | --- | --- |
| arm64 | `6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4` | `41b072352f4561018949623c674d16ef704019b9108a9bbdbd21292efebfc94f` |
| amd64 | `cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10` | `eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c` |
