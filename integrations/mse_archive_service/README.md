# Private synthetic archive service

## Engine decision

Use SQLite in the first dedicated single-writer archive VM. The private API
owns all database access. No SQL listener or shared archive database files
are part of this profile. Operator reads and exact logical exports use TLS
with certificate-chain and hostname verification. There is no plaintext
fallback. Any future network SQL design requires a separate validated TLS
configuration and reviewed engine migration.

The matched comparison ran on Python 3.12.14, SQLite 3.53.1, PostgreSQL
16.16 (official Postgres.app 2.9.7) and psycopg 3.2.13. PostgreSQL ran in a
disposable cluster with TCP disabled, a private Unix socket, fsync and
synchronous commit enabled. It was stopped after the comparison. The
portable harness used the same schema and generated facts in both engines,
two writers with 8 batches of 64 readings each, and the same initial known
tombstone, retry, conflict and precommit interruption. It verified exact
decimal and original-byte linkage, historical cutoff and identical
**1,025-row** joined outputs. Local elapsed write/read observations were
SQLite **0.0108 / 0.0012 s** and PostgreSQL **0.0204 / 0.0407 s**.
These timings include driver differences and connection overhead. An
application-level sequence serialized both test writers. No production
throughput, parallel SQL capacity, power-loss or remote connection
conclusion follows from this comparison. Log SHA-256
`e8f13afef377bd57d2d083aae26a18cb09b00aa1a3b384594782924406b9c02c`.
[Engine disposition](https://github.com/ctmansfield/mother/pull/23#issuecomment-7056154116)

Repeat only against a fresh disposable PostgreSQL 16 cluster whose
private Unix socket has a dedicated empty `archive_comparison` database.
The comparison driver creates tables and writes synthetic data to that
database. Prepare the isolated psycopg dependency before running:
`python -B tools/mse_integration/compare_archive_engines.py --postgres-socket "$scratch_socket_dir"`.
Do not point it at a guest service database.

SQLite preserves the qualified PF-001 original, immutable revision,
state and receipt relationships with fewer runtime dependencies. Reassess
if future approved scope requires direct SQL, concurrent independent
writers or different failure domains. [Offline reference candidate](https://github.com/ctmansfield/mother/pull/35)

## Private guest inputs and lifecycle

Use an isolated Python 3.10+ virtual environment with the pinned
`requirements.txt` from this directory. Record actual interpreter, SQLite,
OpenSSL and Linux package hashes in the guest receipt. Synthetic local
qualification used Python 3.12.14. Obtain the guest's source bundle and
integrity pin through the authorized handoff. Use the published archive-only
allowlist to avoid installing unrelated checkout content.

Create a private configuration file readable by the dedicated service
account only. Replace each placeholder with an approved synthetic-stage
value. All four bearer credentials must be independent random 32-byte
tokens encoded as 43 unpadded base64url characters. The configuration needs
only their lowercase SHA-256 digests. Protect the credentials and configuration
separately. The artifact allowlist contains the lowercase SHA-256 of exact
reviewed fresh synthetic originals, including a separate synthetic
conflict fixture if that case is needed. A marker inside a submitted capture
provides no admission authority.

```json
{
  "archive_id": "synthetic-stage-archive",
  "scope": {
    "subject_id": "synthetic-stage-subject",
    "source_system": "healthkit",
    "source_instance": "synthetic-stage-store",
    "collection": "healtharchive"
  },
  "expires_at": "<UTC-YYYY-MM-DDTHH:MM:SSZ>",
  "token_sha256": {
    "phone": "<sha256>",
    "reader": "<sha256>",
    "exporter": "<sha256>",
    "evidence": "<sha256>"
  },
  "allowed_artifact_sha256": ["<reviewed-synthetic-sha256>"]
}
```

Use an explicitly allocated private absolute path on verified local
persistent storage, under a caller-owned canonical parent. The root is 0700,
database paths are owned single-link regular files at 0600. The guest
service operator verifies the persistent mount and the exact assigned tailnet
interface/address before start. Tailnet access controls and any host ACL are
managed outside this module. Run one service instance. The server handles
requests serially. Never run a second instance against the same stores.

From the extracted source root and as the archive identity, run fresh
initialization once, only against an empty private archive root:

```sh
python -B -m integrations.mse_archive_service.server init --config "$config" --root "$archive_root"
```

Initialization uses the pinned PF-001 `0001_archive.sql` and journal DDL
from the pinned source. It creates an initialization marker with the frozen
schema digest, scope and both SQLite catalog digests. Startup requires the
existing marker, matching catalogs and scope, and PF-001 schema 1 / contract
1.0.0. If interrupted or mismatched, stop and preserve the root for review.
An ordinary restart uses the same root and identity and runs no initializer.

```sh
python -B -m integrations.mse_archive_service.server serve \
  --config "$config" --root "$archive_root" --bind "$tailnet_ipv4" --port "$port" \
  --cert "$server_certificate_chain" --key "$private_key_file"
```

The entry point requires an explicit tailnet-range IPv4 bind and a TLS
certificate/key. It never binds a plaintext listener. Clients use a
configured HTTPS hostname matching the certificate and its approved trust
chain. There is no remote database TLS configuration in this SQLite profile
because the API uses embedded SQLite. Restrict socket reachability to the
approved private callers. Production certificate/key custody remains with
the guest operator. Stop accepting new requests before planned shutdown.
A service manager may initiate controlled stop with SIGINT; interrupted
writes are reconciled via exact retry. Stop and preserve the stores and
installed pins before rollback. No in-place rollback across incompatible
schemas is implemented. Backup/restore is owner-deferred.

## Wire and operator readback

- Phone PUT and GET `/v1/archive/batches/{batch_id}` require the phone's
  bearer. PUT accepts exact `application/json` original bytes, with no
  encoding or transfer wrappers. A verified terminal receipt is 200.
  A pending durable stage returned by GET is 202. Same-scope changed
  allowlisted bytes under the same batch produce 409. Batch metadata is
  server-fixed to partial capture and capture ID equal to batch ID.
  Only matching normalized receipts advance delivery.
- Reader GET `/v1/archive/operator/receipts` or `/revisions` or
  `/relations` with `from` and `through` commit sequence. Receipt list
  optionally filters exact `batch_id` or `receipt_id`. Revision history
  optionally filters `metric` and a complete UTC interval
  (`measurement_start`, `measurement_end`). Current revision mode is
  `mode=current` with `from=1` and the complete interval, based on the
  verified historical snapshot. Source/deletion evidence and receipt
  membership remain distinct. Logical relation keys preserve repeated
  source sightings and nullable processing IDs.
- Exporter GET `/v1/archive/operator/export` uses the history relation
  query and returns canonical JSON with exact decimal text, unit,
  cutoff, view digest and row count. Load this authorized projection into
  a new purpose-specific SQLite file using
  `python -B -m integrations.mse_archive_service.load_export --input "$verified_export" --sha256 "$approved_response_sha256" --output "$new_copy"`.
  The input is the complete canonical HTTPS response body. The digest must
  be separately trusted. This downstream database has no writeback authority.
- Evidence GET `/v1/archive/operator/originals/{artifact_sha256}` requires
  a different credential and returns the verified exact original as bytes.
  Phone, reader and exporter grants cannot use this capability.
- Bounds include 128 KiB capture bytes, 128 capture records, depth 16,
  80-byte numeric tokens, at most 64 batches and 32 reviewed artifact
  digests in the stage, at most 64 commit positions per query, 1,024 view
  rows and a 2 MiB response cap. Socket inactivity timeout is five seconds.
  The caller must narrow an oversized view. Socket inactivity is not a
  full request deadline. Supported use is the isolated finite synthetic
  stage with bounded callers, not an availability claim.

Run local service tests in the source checkout using
`python -B -m unittest discover -s tests/integration/mse_archive_service -v`.
The tests create disposable loopback TLS with temporary test material using
OpenSSL. Validate remote TLS, private reachability, startup, receipt, and
operator export from the actual guest separately. Runtime smoke tests must
use a fresh explicitly allowed synthetic capture.
