# Separate private typed BP history service

This service supersedes the earlier proposed file exchange. It implements
[ATLAS r3](https://github.com/ctmansfield/mother/pull/23#issuecomment-7058180458)
and is separate from the opaque bulk receiver on 8447 and live pilot on
8446. The phone sends one approved exact page over verified private TLS. The
server validates it, seals its original using public-only age, and commits
ciphertext, typed lineage, checkpoint and receipt together. Only the
post-commit pre-cutoff witness makes them visible. The 10-field receipt is
returned inline. It proves server acceptance of that page, not an off-guest
decryption or raw-vault receipt.

## Exact app wire

See the [synthetic vector](bp-http-vectors.json). Its connection config is
the value under `connection` in ORACLE's private enrollment document. Use a
separately transferred `write_token` member in that document. Use hostname
validation, no redirects, and a separate device-only credential. Do not
reuse the fabricated hostname, token or values. In each stream sequence
starts at 1 and `cursor_in` is null. A fresh 43-character base64url token
is needed for every new page, including an empty terminal page. A terminal
receipt completes only that query traversal. No native anchor bytes are
transferred.

PUT/GET `/v1/bp-history/enrollments/{enrollment_id}/streams/{stream_id}/pages/{page_seq}`.
PUT sends exact UTF-8 JSON with one Content-Length and Content-Type
`application/json`, no content/transfer encoding. Maximum 1 MiB and 512
total entries. 201 means new durable acceptance. 200 returns the identical
receipt on exact accepted PUT retry or separately authorized GET. 400 is
invalid shape/binding, 401 invalid/expired grant, 403 scope or transport
lease, 404 absent receipt, 409 page/digest/cursor/terminal conflict, 413 caps,
and 503 indeterminate. Phone exact replay uses its upload grant before the
lease expires. After expiry the operator can reconcile a receipt using the
separate receipt grant. One accepted history export role may call
`/v1/bp-history/enrollments/{enrollment_id}/streams/{stream_id}/export?from=1&through=1`,
at most four sequence positions and 2 MiB. It returns typed history and
tombstones with protected references. Keep physiology and references in
restricted custody. No ciphertext or raw original route is exposed.

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
  "streams": {"bp_correlation": "demo-correlation", "systolic": "demo-systolic", "diastolic": "demo-diastolic"},
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
No recovery by deleting a page or advancing a phone checkpoint.

Pin [upstream age v1.3.2](https://github.com/FiloSottile/age/releases/tag/v1.3.2).
Verified Linux release archive and executable SHA-256 values are below.
Check the architecture, independent provenance and actual guest version.
The runtime package excludes binaries and private data.

| Linux architecture | Archive SHA-256 | age executable SHA-256 |
| --- | --- | --- |
| arm64 | `6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4` | `41b072352f4561018949623c674d16ef704019b9108a9bbdbd21292efebfc94f` |
| amd64 | `cbe24006683f8eb669266162894b9a522a1af52f2665fbc63a4bb032ed26ac10` | `eb7dd1b518f0a307c99cd97782623c5321da049154b04acd2d98d21aa7bc9b2c` |
