# Selected HealthKit pilot service

The selected v2 service uses the ATLAS 0.1 schema and
[prospective 48-hour admission rules](../../docs/mse/integration/selected-healthkit/LIVE_PILOT_48H.md).
It has its own process, archive identity, credentials and SQLite root. The
existing synthetic v1 service and root are separate. PHOENIX owns guest setup
and keeps the hostname, exact peer restrictions, private inputs and health
evidence in restricted custody.

## Stage and start

Verify the source package and manifest, then install the six pinned packages
from `requirements.txt` in a dedicated Python 3.10+ environment using the
approved guest wheel digests. Record the actual Python, SQLite and OpenSSL
versions. Use a dedicated nonlogin service account, local persistent storage
and an empty, canonical, service-owned directory at mode 0700. The stores
remain after the pilot. Use one process for this root. Confirm a trusted UTC
clock at every service start. Keep host ingress limited to the intended phone
and separately authorized operators. The Python service does not manage the
forwarder or host policy.

Create a service-owned mode-0600 UTF-8 JSON file. Exactly the following fields
are required for the pilot. The archive ID, enrollment ID and scope stay
fixed across staged startup, release, restart and stop. Use distinct random
32-byte bearer secrets, encoded as 43 unpadded base64url characters, and store
only their lowercase SHA-256 values in the server config. Use separate expiry
instants. The phone expiry covers the scheduled window. Reader, exporter and
evidence expiry can be later and remain finite.

```json
{
  "archive_id": "<fresh private archive ID>",
  "scope": {
    "subject_id": "<fresh pseudonymous ID>",
    "source_system": "healthkit",
    "source_instance": "<fresh selected store namespace>",
    "collection": "healtharchive-selected"
  },
  "expected_guest_ipv4": "<assigned private RFC1918 IPv4>",
  "pilot": {
    "enrollment_id": "<fresh enrollment ID>",
    "start": null,
    "end": null,
    "enabled": false,
    "max_commits": 20000,
    "reserve_bytes": 1073741824
  },
  "grants": {
    "phone": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"},
    "reader": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"},
    "exporter": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"},
    "evidence": {"sha256": "<digest>", "expires_at": "<UTC with six fractional digits>"}
  }
}
```

For separate synthetic qualification only, choose a `synthetic-` subject and
add `allowed_artifact_sha256` with reviewed synthetic hashes. Never use that
root or credentials for the pilot. Choose and record the real quota after
checking the mounted filesystem and preserving reserve for the existing
service. The example values are placeholders for capacity planning. Each
admitted body is at most 128 KiB, 128 records, depth 16, 20 integer token
characters, and schema-bounded decimal text. Check free space under the
selected mount before release. The commit cap and disk free-space guard
apply to new batches even when quarantined. They provide backpressure and
never trigger deletion. They do not replace filesystem capacity monitoring.

From the extracted source directory, as the service identity:

```sh
python -B -m integrations.mse_archive_service.selected_server init \
  --root "$selected_root" --config "$selected_config"

python -B -m integrations.mse_archive_service.selected_server serve \
  --root "$selected_root" --config "$selected_config" \
  --bind "$assigned_guest_ipv4" --port 8446 --cert "$leaf_chain" --key "$leaf_key"
```

Run `init` once. It refuses a populated root. This release uses
`selected-healthkit-pilot-sqlite/2` and refuses earlier staged layouts on
reopen. Preserve any earlier qualification root and stage in a fresh one. Ordinary start and restart use
`serve` with the same configured identity. Explicit private IPv4 and port
are required, and a wildcard is refused. Verify hostname and CA against the
client-facing private hostname and use guest-terminated TLS. The service
has no plaintext or SQL listener. Only the actual PM release supplies
canonical UTC start and end exactly 48 hours apart and sets `enabled` to
true. For intentional stop, remove phone ingress and set `enabled` false
before restarting. The first enabled startup records an immutable window.
No restart extends it. The passive cutoff latch persists when observed;
trusted UTC and external phone ingress expiry still need operator verification.

## Request and evidence behavior

- Phone PUT uses exact `application/json` with content length and immutable
  body on `/v2/archive/batches/{batch_id}`. GET on the same path retrieves a
  matching receipt only during the pilot and with a valid phone grant.
  Success replies use selected batch/receipt 0.1. A quarantined receipt
  is terminal custody without an authoritative commit ID. A different body
  after binding returns 409. Closed ingestion returns 403 with a still-valid
  grant, or 401 once that grant expires. There are 60 authenticated requests
  per minute per role and a five-second body deadline.
- Only complete prospective intervals and collector clocks at or after
  start and observed by the server before cutoff are admitted. Deletes
  require an already accepted or same-batch eligible upsert under the same
  metric/UUID key. There is no old data import or boundary clipping.
- Full-sync custody and receipt transactions each need an in-window
  verification after SQLite commit returns. The final witness records when
  the already-durable receipt was observed. A crash or cutoff before either
  observation leaves durable bytes and any candidate receipt sealed and
  absent from operator receipt, original and export endpoints. No restart
  infers a witness from an unwitnessed candidate. A pending transaction
  blocks new admission for independent reconciliation.
- A witness can prove only an already-durable in-window receipt. If
  witness persistence or the response reaches cutoff, the phone receives
  no success. Authorized operator readback can reconcile a witnessed
  pre-cutoff receipt historically. The witness cannot add a batch or
  change the receipt or its sequence. Stop phone access at cutoff and
  retain the root and restricted evidence. Do not delete, replay, or
  normalize incomplete custody automatically.
- Reader GET uses `/v2/archive/operator/receipts/{batch_id}` or
  `/v2/archive/operator/rows?from=1&through=1`. Exporter uses
  `/v2/archive/operator/export` with the same bounds. Evidence GET uses
  `/v2/archive/operator/originals/{batch_id}`. Each requires its own
  grant. Rows and export accept at most eight commit positions; optional
  `mode=current` and paired `event_start`/`event_end` select the documented
  projection. Raw originals return as exact bytes and can be checked against
  receipt SHA-256. CSV conversion or cross-source summation is outside the
  pinned representation. Operator readback remains available after phone
  cutoff while each operator grant is valid.

Keep commands and service logs free of bearer values, full URLs, receipt
bodies and sample data. The service emits generic errors and disables normal
request logging. A failed start, hot journal that cannot reopen read-only,
or incomplete custody requires evidence-preserving operator review. Backup,
restore and explicit archive erasure remain deferred.
