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
Feed names are exactly `correlation`, `systolic`, `diastolic`. Sequence
is a positive path integer beginning at 1 independently per feed. The
body contains no sequence field. The server binds it to the body's trusted
enrollment, source instance, feed, fixed historical cutoff and opaque
cursor chain. The approved native anchor stays local. Transport UTC and
historical sample cutoff are separate. The candidate caps a page at 1 MiB
and 128 upserts plus deletions, matching the canonical parser. Standard
HTTPS validates the hostname. No redirect, compression or chunked upload.

- PUT needs the upload bearer. A new or exact pending PUT returns 202
  `{"status":"pending_custodian_verification"}`. It never advances the
  phone cursor. Exact accepted PUT replay returns 200, changed bytes
  under an existing sequence return 409. Only one unwitnessed staged page
  is allowed per enrollment in this candidate.
- GET with a distinct finite receipt bearer returns 202 in-window while
  durable custody awaits verification, 200 for a typed durable receipt,
  or 404 when there is no authorized visible receipt. No receipt body is
  returned for sealed or unverified data. Operator export needs its own
  grant and returns only witnessed typed facts. The phone validates the
  exact receipt hash/length, enrollment/archive/store/cutoff/feed, cursor
  echo, counts, completion and ciphertext binding before promoting its
  protected local checkpoint.
- The separately enrolled custodian bearer alone can GET `/custody` and
  `/ciphertext` appended to the page route, then POST `/commit`. The
  custody JSON is the exact witness statement. The ciphertext response
  is bounded binary. In restricted custody independently compare
  archive/enrollment/source instance, feed/path sequence, exact expected
  plaintext digest and length. Authenticate the downloaded ciphertext with
  the existing exact age receipt and detached identity. Then sign the
  canonical UTF-8 witness JSON with the enrolled Ed25519 signing key.
  The VM independently verifies the exact statement and signature before
  it can publish a typed checkpoint. The signing key and age identity
  both stay off-VM. The recipient and verification keys on-VM are public.

Use the local custodian CLI only on approved protected paths. The
`--binding` JSON has exactly `archive_id`, `enrollment_id`,
`source_instance`, `feed`, `page_seq`, `plaintext_sha256`, and
`plaintext_length` from independent custody. Never obtain that binding
solely by copying the server statement.

```sh
python -B -m integrations.mse_health_history.bp_witness \
  --statement "$custody_metadata" --binding "$independent_binding" \
  --ciphertext "$restricted_ciphertext" --age-executable "$age" \
  --age-sha256 "$age_sha256" --recipient-fingerprint "$recipient_sha256" \
  --identity-file "$off_vm_age_identity" --signing-key "$off_vm_ed25519_key" \
  --openssl "$openssl3" --output "$new_proof_file"
```

POST the protected output JSON unchanged with the custodian bearer and
Content-Type application/json; do not put it in ordinary logs. A valid
signature over another page or enrollment cannot authorize this one.
The signature and ciphertext metadata enter the SQLite decision before
its FULL-sync durability observation. Cursors and receipt visibility
advance only once a valid decision was observed durable before cutoff.
A cutoff or failed proof leaves pending data sealed. Restart never
infers acceptance.

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
  "custodian_public_key_file": "<service-owned Ed25519 public PEM>",
  "custodian_public_sha256": "<exact public PEM digest>",
  "openssl_executable": "/usr/bin/openssl",
  "grants": {
    "upload": {"sha256": "<digest>", "expires_at": "2026-11-22T02:00:00Z"},
    "receipt": {"sha256": "<digest>", "expires_at": "2026-11-22T03:00:00Z"},
    "export": {"sha256": "<digest>", "expires_at": "2026-11-22T03:00:00Z"},
    "custodian": {"sha256": "<digest>", "expires_at": "2026-11-22T02:00:00Z"}
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
No recovery by deleting a page or advancing a phone checkpoint.

Pin [upstream age v1.3.2](https://github.com/FiloSottile/age/releases/tag/v1.3.2).
Verified Linux release archive and executable SHA-256 values are below.
Check the architecture, independent provenance and actual guest version.
The runtime package excludes binaries and private data.

| Linux architecture | Archive SHA-256 | age executable SHA-256 |
| --- | --- | --- |
| arm64 | `6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4` | `41b072352f4561018949623c674d16ef704019b9108a9bbdbd21292efebfc94f` |
| amd64 | `cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10` | `eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c` |
