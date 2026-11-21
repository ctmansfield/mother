# Ciphertext-only history receiver candidate

This module implements a single opaque history enrollment on a dedicated
private guest root. It never opens the plaintext ZIP, holds the detached age
identity, or writes typed records. A ciphertext receipt proves byte custody
only. The existing synthetic and selected pilot services use different roots,
accounts, listeners and grants.

## Private configuration

Use a dedicated nonlogin account, a new canonical root owned by that account
with mode 0700, a verified local persistent mount, and a mode-0600 config
owned by that account. Use a private IPv4 assigned to the isolated guest.
Keep exact peer restriction and certificate/hostname verification outside
this process. Verify the root/mount, available capacity, expiry and current
live pilot isolation before starting. Use a new stage enrollment for synthetic
traffic, a new finite enrollment for any later approved actual transfer.

```json
{
  "bind": "<assigned RFC1918 guest IPv4>",
  "enrollment": {
    "vault_id": "<opaque fresh vault ID>",
    "import_id": "<opaque fresh import ID>",
    "recipient_fingerprint": "<approved recipient SHA-256>",
    "expected_sha256": "<exact ciphertext SHA-256>",
    "expected_length": 1,
    "cutoff": "<UTC with six fractional digits>",
    "max_allocation_bytes": 12884901888,
    "reserve_bytes": 17179869184,
    "enabled": false
  },
  "grants": {
    "upload": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"},
    "receipt": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"},
    "ciphertext": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"}
  }
}
```

Replace the sample length with the pinned positive ciphertext length. The
receiver permits at most 8 GiB ciphertext, at most 12 GiB allocated for this
object and its metadata, and at least a 16 GiB free-space floor. The upload
grant must expire at or before the cutoff. All bearer secrets are independent
32-byte random tokens encoded as 43 unpadded base64url characters. Store only
their SHA-256 digests here. The archive remains readable to explicitly
authorized receipt and ciphertext roles while their finite grants are valid.

Run from the verified source-only receiver package. It uses Python 3.10+
and the standard library only.

```sh
python -B -m integrations.mse_health_history.vault_server init \
  --root "$history_root" --config "$history_config"

python -B -m integrations.mse_health_history.vault_server serve \
  --root "$history_root" --config "$history_config" \
  --bind "$assigned_guest_ipv4" --port 8447 --cert "$leaf_chain" --key "$leaf_key"
```

The initializer refuses a populated root and pins every enrollment field
except the enable switch. The receipt-witness layout is `history-vault/2`.
Preserve any earlier staged root and qualify this package in a fresh root. Regular restart uses serve. Use TLS with the
approved guest-terminated certificate and client-verified hostname. There
is no wildcard, SQL or plaintext listener. Disable intake and close only its
separate relay when stopping. Leave the files in place.

## Upload and readback

- Upload PUT `/v1/history/imports/{import_id}` with an exact content length,
  media type `application/octet-stream`, `Content-Range: bytes start-end/total`
  where end is inclusive, and `X-Chunk-SHA256`. Each chunk is at most 4 MiB.
  No compression or HTTP transfer encoding is accepted. The server verifies
  the entire chunk before appending and fsyncs the prefix. A 202 means the
  prefix is available to resume, with `next_offset`. Authenticated upload
  GET `/progress` reports offset and completion. An exact repeat of a
  contained range is idempotent. Changed, overlapping, or skipped ranges
  fail. No cursor or completion is inferred from a lost response.
- A final 200 means the ciphertext was rehashed and both the final file
  name and candidate receipt were observed durable before cutoff. A separate
  witness binds that pre-cutoff observation to the receipt ID. Only a
  witnessed receipt is visible to readers. If the receipt-directory sync
  returns at cutoff or later, PUT is denied and receipt/ciphertext reads
  stay hidden through restart. Startup never supplies a missing witness.
- An explicit, byte-identical contained retry before cutoff may rehash and
  reverify an interrupted object. After cutoff there is no retry, new
  byte admission, or inferred acceptance. If only the final witness
  directory sync crosses cutoff, the original PUT may return its already
  verified receipt. That sync records proof of a pre-cutoff decision
  and adds no ciphertext. This finite upload lease is separate from
  the selected 48-hour pilot. Unwitnessed bytes remain restricted.
- Receipt GET on the same path requires the receipt role. Use a separate
  ciphertext role for GET `/ciphertext?offset=N`, at most 4 MiB per response.
  The client verifies each response hash and the complete object against
  the pinned receipt. Store filenames, data, token values and exact
  enrollment details stay out of normal logs and shared receipts.

## Custodian and release gates

Only the raw-data custodian authenticates the ciphertext with the independently
verified age executable and detached recipient identity. The receiver never
gets a decrypt key or any plaintext hash/identity. For BP pages the separate
custodian verifier checks the vault receipt and authenticates exact ciphertext
into bounded process memory before any typed/cursor commit. There is no
plaintext page temporary file on this path. The typed history database still
contains restricted physiology and requires its own protected encrypted
working volume. Its separate measurement/pseudonym keys never go to the
guest transit credential.

Run only a synthetic intake after independent review of the exact package,
storage, service-account files, TLS, peer/role and interruption controls.
Reconcile guest versions, source/recipient fingerprints and post-cutoff
closure. A real export still requires native-route and capture-device proof,
custodian approval and a declared capacity budget. Backup/restore is deferred.
