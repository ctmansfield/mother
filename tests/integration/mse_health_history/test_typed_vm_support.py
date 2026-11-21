"""Run the authenticated synthetic native fixture through ATLAS r2 mTLS."""

from contextlib import closing
from hashlib import sha256
from http.client import RemoteDisconnected
from ipaddress import IPv4Network
import json
import sqlite3
import ssl
import subprocess
from threading import Thread
from unittest.mock import patch

import test_bp_transport

from integrations.mse_health_history.blood_pressure import protected_ref, source_time
from integrations.mse_health_history.typed_vm import (
    NORMALIZER,
    PROJECTION_REVISION,
    TypedStore,
    batch_receipt,
    build_batches,
    digest,
    encoded,
    project,
)
from integrations.mse_health_history.typed_vm_https import (
    Closed,
    TypedClient,
    TypedHandler,
    TypedServer,
)


def verify_guest(test, root, catalog, original, _receipt, start, end):
    start, end = map(source_time, (start, end))
    sender, guest = root / "mac-projection", root / "guest"
    sender.mkdir(mode=0o700)
    guest.mkdir(mode=0o700)
    mapping_key = b"m" * 32
    scope = {
        "store_id": "synthetic-guest",
        "enrollment_id": catalog.enrollment,
        "source_namespace_ref": protected_ref(
            mapping_key, "native-namespace", catalog.enrollment, catalog.source_instance
        ),
        "import_ref": "synthetic-import",
        "normalization_version": NORMALIZER,
    }
    bounds = (start, end)
    raw, terminal = project(catalog, original, scope, bounds, mapping_key=mapping_key)
    test.assertEqual(
        tuple(project(catalog, original, scope, bounds, mapping_key=mapping_key)),
        (raw, terminal),
    )
    source_manifest = json.loads(terminal)["manifest"]
    ops = json.loads(raw)["ops"]
    test.assertEqual([op["pairing"] for op in ops], ["paired", "unpaired"])
    for forbidden in (
        b"apple_health_export",
        b"opaque.gpx",
        b"source_ref",
        b"source_start",
        b"native_ref",
        original.encode(),
    ):
        test.assertNotIn(forbidden, raw + terminal)
    target = ops[0]["components"][0]["component_ref"]
    deletion = dict(
        op="delete",
        occurrence_ref="synthetic-tombstone",
        target_kind="component",
        target_ref=target,
    )
    surviving = dict(
        ops[0],
        logical_ref="distinct-equal-values",
        revision_ref="distinct-revision",
        occurrence_ref="distinct-locator",
        components=[
            dict(
                c,
                component_ref=f"other-component-{i}",
                component_occurrence_ref=f"other-locator-{i}",
            )
            for i, c in enumerate(ops[0]["components"], 1)
        ],
    )
    settings = {
        "artifact_ref": source_manifest["artifact_receipt_ref"],
        "inventory_ref": source_manifest["member_inventory_ref"],
        "observed": 5,
        "quarantined": 3,
    }
    vector = tuple(build_batches(scope, bounds, [*ops, deletion], **settings))
    raw, terminal = build_batches(
        scope, bounds, [*ops, deletion, surviving], **settings
    )
    expected_terminal = json.loads(batch_receipt(json.loads(terminal), terminal, 0, 0))

    projected = {
        part["role"]: part["component_occurrence_ref"] for part in ops[0]["components"]
    }

    def expected_child(ordinal):
        return protected_ref(
            mapping_key,
            "native-component-occurrence",
            scope["source_namespace_ref"],
            original,
            ops[0]["occurrence_ref"],
            ordinal,
        )

    test.assertEqual(
        projected, {"diastolic": expected_child(1), "systolic": expected_child(3)}
    )

    def open_store(filename="native.sqlite3"):
        return TypedStore(
            guest / filename,
            scope,
            bounds,
            source_manifest["artifact_receipt_ref"],
            source_manifest["member_inventory_ref"],
            max_batches=4,
            max_bytes=1024**2,
            admitted_deletions=[("component", target)],
        )

    store = open_store()
    store.initialize()
    test.assertRaises(FileExistsError, store.initialize)
    checks = 0

    def stop_after_insert():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise Closed("synthetic cutoff before commit")

    test.assertRaises(Closed, store.ingest, 1, vector[0], stop_after_insert)
    with closing(open_store().connect()) as db:
        test.assertEqual(db.execute("SELECT count(*) FROM ops").fetchone(), (0,))
    test.assertRaises(KeyError, store.receipt, 1)

    test.client_ca = sender / "ca.pem"
    test.client_ca_key = sender / "ca.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=Synthetic native transport CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE",
            "-keyout",
            test.client_ca_key,
            "-out",
            test.client_ca,
        ],
        check=True,
        capture_output=True,
    )
    server_cert, server_key = guest / "server.pem", guest / "server.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            server_key,
            "-out",
            server_cert,
        ],
        check=True,
        capture_output=True,
    )
    issue = test_bp_transport.BPTransportTests.make_client
    writer, receipt, consumer = [
        issue(test, "synthetic-native-" + role)
        for role in ("writer", "receipt", "consumer")
    ]
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(server_cert, server_key)
    server_context.load_verify_locations(cafile=test.client_ca)
    server_context.verify_mode = ssl.CERT_REQUIRED

    def pin(cert):
        return sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()

    now = start
    read_end = source_time("2030-01-01T00:00:00Z")
    purpose, snapshot_id = "mother-bp-review", "synthetic-snapshot"
    with patch(
        "integrations.mse_health_history.typed_vm_https.PRIVATE",
        (IPv4Network("127.0.0.1/32"),),
    ):
        server = TypedServer(
            ("127.0.0.1", 0),
            store,
            server_context,
            {
                "writer": (pin(writer[0]), end),
                "receipt": (pin(receipt[0]), read_end),
                purpose: (pin(consumer[0]), read_end),
            },
            start,
            end,
            clock=lambda: now,
            snapshots=[
                dict(
                    snapshot_id=snapshot_id,
                    purpose=purpose,
                    subject="synthetic-purpose-subject",
                    terminal_receipt=expected_terminal["receipt_id"],
                    start=start,
                    end=end,
                    projection_revision=PROJECTION_REVISION,
                    max_rows=10,
                    max_bytes=4096,
                )
            ],
        )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    test.addCleanup(server.server_close)
    test.addCleanup(thread.join, 5)
    test.addCleanup(server.shutdown)

    def client(credentials, **scope_overrides):
        ctx = ssl.create_default_context(cafile=server_cert)
        if credentials:
            ctx.load_cert_chain(*credentials)
        return TypedClient(
            "127.0.0.1", server.server_port, dict(scope, **scope_overrides), ctx
        )

    upload, readback, read = map(client, (writer, receipt, consumer))
    test.assertEqual(readback.receipt(1)[0], 404)
    test.assertEqual(read.put(1, raw)[0], 403)
    test.assertEqual(read.receipt(1)[0], 403)
    test.assertEqual(readback.snapshot(purpose, snapshot_id)[0], 403)
    test.assertEqual(upload.snapshot(purpose, snapshot_id)[0], 403)
    test.assertEqual(read.snapshot("coach-bp-review", snapshot_id)[0], 403)
    test.assertEqual(client(writer, import_ref="synthetic-other").put(1, raw)[0], 404)
    with test.assertRaises((ssl.SSLError, ConnectionError)):
        client(None).put(1, raw)
    test.assertEqual(upload.put(2, terminal)[0], 409)
    test.assertEqual(
        upload.request(
            "PUT",
            upload.batch_path + "1",
            raw,
            headers={
                "Content-Type": "application/json",
                "Content-Digest": "sha-256=:" + "A" * 43 + "=:",
            },
        )[0],
        400,
    )

    first_code, first = upload.put(1, raw)
    test.assertEqual(first_code, 201)
    test.assertEqual(first["batch_sha256"], digest(raw))
    test.assertIsNone(first["manifest_sha256"])
    test.assertEqual(upload.put(1, vector[0])[0], 409)
    test.assertEqual(read.snapshot(purpose, snapshot_id)[0], 404)
    test.assertEqual(upload.put(2, vector[1])[0], 409)
    bad = json.loads(terminal)
    bad["manifest"]["upsert_count"] += 1
    test.assertEqual(upload.put(2, encoded(bad))[0], 409)
    test.assertEqual(readback.receipt(2)[0], 404)

    reply = TypedHandler.reply

    def lose_committed_response(handler, status, body):
        if status != 201:
            return reply(handler, status, body)

    with patch.object(TypedHandler, "reply", lose_committed_response):
        with test.assertRaises(RemoteDisconnected):
            upload.put(2, terminal)
    reopened = open_store()
    server.store = reopened
    test.assertEqual(readback.receipt(2), (200, expected_terminal))
    readback.verify_receipt(terminal, expected_terminal)
    test.assertEqual(upload.put(2, terminal), (200, expected_terminal))
    now = end
    test.assertEqual(upload.put(1, raw)[0], 403)
    test.assertEqual(readback.receipt(1), (200, first))
    code, result = read.snapshot(purpose, snapshot_id)
    test.assertEqual(code, 200)
    test.assertEqual(
        result["rows"],
        [{"bucket": "2026-11-21T00:00Z", "systolic": "124.5", "diastolic": "81"}],
    )
    test.assertEqual(result["count"], 1)
    with closing(reopened.connect()) as db:
        with test.assertRaises(sqlite3.OperationalError):
            db.execute("DELETE FROM ops")
    # Cross the exact cutoff immediately before the real SQLite staging commit.
    now = start
    late = open_store("cutoff.sqlite3")
    late.initialize()
    server.store = late
    test.assertEqual(upload.put(1, raw)[0], 201)
    original_connect = late.connect

    class CommitAtEnd:
        def __init__(self, connection):
            self.connection = connection

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            return self.connection.__enter__()

        def __exit__(self, exc_type, exc, trace):
            nonlocal now
            now = end
            return self.connection.__exit__(exc_type, exc, trace)

    def cutoff_connect(*, write=False):
        connection = original_connect(write=write)
        return CommitAtEnd(connection) if write else connection

    with patch.object(late, "connect", cutoff_connect):
        test.assertEqual(upload.put(2, terminal), (503, {"error": "indeterminate"}))
    server.store = open_store("cutoff.sqlite3")
    with closing(server.store.connect()) as db:
        test.assertEqual(
            db.execute("SELECT observed_at FROM batches WHERE seq=2").fetchone(),
            (None,),
        )
    test.assertEqual(readback.receipt(2)[0], 503)
    test.assertEqual(read.snapshot(purpose, snapshot_id)[0], 503)
    test.assertEqual(upload.put(2, terminal)[0], 403)

    # Simulate a stop after staging, before the witness write, while still in lease.
    now = start
    crashed = open_store("crashed.sqlite3")
    crashed.initialize()
    server.store = crashed
    test.assertEqual(upload.put(1, raw)[0], 201)
    calls = 0

    def stop_before_witness():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic interruption after staging")
        return start

    with test.assertRaises(OSError):
        crashed.ingest(2, terminal, stop_before_witness)
    server.store = open_store("crashed.sqlite3")
    test.assertEqual(upload.put(2, terminal)[0], 503)
    test.assertEqual(readback.receipt(2)[0], 503)
    test.assertEqual(read.snapshot(purpose, snapshot_id)[0], 503)
    now = read_end
    test.assertEqual(readback.receipt(2)[0], 403)
    test.assertEqual(read.snapshot(purpose, snapshot_id)[0], 403)


def verify_shared_vector(test, root):
    from pathlib import Path

    from integrations.mse_health_history import typed_vm

    vector = json.loads(
        Path(typed_vm.__file__).with_name("native-bp-r2-vectors.json").read_bytes()
    )
    batches = vector["batches"]
    manifest = json.loads(batches[-1]["canonical_utf8"])["manifest"]
    store = TypedStore(
        root / "vector.sqlite3",
        vector["scope"],
        vector["bounds"],
        manifest["artifact_receipt_ref"],
        manifest["member_inventory_ref"],
        max_batches=2,
        max_bytes=1024**2,
        admitted_deletions=vector["admitted_deletions"],
    )
    store.initialize()
    for seq, entry in enumerate(batches, 1):
        raw = entry["canonical_utf8"].encode()
        test.assertEqual(
            store.ingest(seq, raw, lambda: vector["bounds"][0]),
            (201, encoded(entry["receipt"])),
        )
    descriptor = {
        "terminal_receipt": batches[-1]["receipt"]["receipt_id"],
        "snapshot_id": "vector",
        "purpose": "mother-bp-review",
        "subject": "vector-subject",
        "start": vector["bounds"][0],
        "end": vector["bounds"][1],
        "max_rows": 1,
        "max_bytes": 4096,
    }
    test.assertEqual(
        json.loads(store.snapshot(descriptor))["count"],
        vector["expected_consumer_pairs"],
    )


def verify_projection_window(test, root):
    from copy import deepcopy
    from unittest.mock import Mock

    lower = "2026-11-21T00:00:00.000000Z"
    before_lower = "2026-11-20T23:59:59.999999Z"
    before = "2026-11-21T23:59:59.999999Z"
    upper = "2026-11-22T00:00:00.000000Z"
    after = "2026-11-22T00:00:00.000001Z"
    bounds = (lower, upper)
    original = "e" * 64
    key = b"m" * 32
    catalog = Mock(enrollment="synthetic-window", source_instance="synthetic-store")
    scope = {
        "store_id": "synthetic-guest",
        "enrollment_id": catalog.enrollment,
        "source_namespace_ref": protected_ref(
            key, "native-namespace", catalog.enrollment, catalog.source_instance
        ),
        "import_ref": "synthetic-window",
        "normalization_version": NORMALIZER,
    }

    def clocks(start, end):
        return {"event_start": start, "event_end": end}

    def sighting(ordinal, root_clock, child_clock):
        return {
            "member": 1,
            "ordinal": ordinal,
            "revision": f"revision-{ordinal}",
            "fact": {
                "identity": f"occurrence-{ordinal}",
                "pairing": "paired",
                "clocks": clocks(*root_clock),
                "components": [
                    {
                        "role": "systolic",
                        "value": "124.5",
                        "native_ref": None,
                        "clocks": clocks(*child_clock),
                    },
                    {
                        "role": "diastolic",
                        "value": "81",
                        "native_ref": None,
                        "clocks": clocks(lower, lower),
                    },
                ],
            },
        }

    in_range = (lower, lower)
    cases = [
        (in_range, in_range),
        ((before, before), (before, before)),
        ((lower, upper), in_range),
        ((lower, after), in_range),
        ((before, after), in_range),
        (in_range, (lower, upper)),
        (in_range, (lower, after)),
        (in_range, (before, after)),
        (in_range, (before_lower, lower)),
        ((before_lower, lower), in_range),
    ]
    all_sightings = [
        sighting(n, root_clock, child_clock)
        for n, (root_clock, child_clock) in enumerate(cases, 1)
    ]
    preserved = deepcopy(all_sightings)
    catalog.blood_pressure_lineage.return_value = all_sightings
    catalog.blood_pressure_component_lineage.return_value = [
        (1, "systolic"),
        (3, "diastolic"),
    ]
    catalog.members.return_value = []
    receipt = {
        "schema_version": "mse.historical-original-receipt/0.1",
        "protection": "custodian_verified_ciphertext",
        "receipt_id": "synthetic-artifact",
        "observed_top_level_rows": 12,
        "normalized_bp_top_level_rows": 10,
        "unnormalized_top_level_rows": 2,
        "bp_invalid_top_level_rows": 1,
    }
    catalog.receipt.return_value = receipt
    private_ledger = []
    raw, final = project(
        catalog,
        original,
        scope,
        bounds,
        mapping_key=key,
        record_accounting=private_ledger.append,
    )
    ops = json.loads(raw)["ops"]
    manifest = json.loads(final)["manifest"]
    test.assertEqual(
        [(op["event_end"], op["pairing"], len(op["components"])) for op in ops],
        [
            (lower, "paired", 2),
            (before, "paired", 2),
        ],
    )
    test.assertEqual(
        private_ledger,
        [
            {
                "source_occurrence_count": 12,
                "normalized_bp_count": 10,
                "unnormalized_count": 2,
                "parser_quarantined_bp_count": 1,
                "snapshot_excluded_count": 8,
                "emitted_upsert_count": 2,
            }
        ],
    )
    test.assertEqual(
        (
            manifest["source_occurrence_count"],
            manifest["quarantined_count"],
            manifest["upsert_count"],
        ),
        (12, 1, 2),
    )
    test.assertNotIn("snapshot_excluded_count", manifest)
    test.assertEqual(all_sightings, preserved)
    test.assertEqual(catalog.blood_pressure_component_lineage.call_count, 2)
    test.assertEqual(
        tuple(project(catalog, original, scope, bounds, mapping_key=key)), (raw, final)
    )

    store = TypedStore(
        root / "window.sqlite3",
        scope,
        bounds,
        manifest["artifact_receipt_ref"],
        manifest["member_inventory_ref"],
        max_batches=2,
        max_bytes=1024**2,
    )
    store.initialize()
    slipped = json.loads(raw)
    slipped["ops"][0]["components"][0]["event_end"] = upper
    with test.assertRaises(ValueError):
        store.ingest(1, encoded(slipped), lambda: lower)
    with test.assertRaises(KeyError):
        store.receipt(1)
    test.assertEqual(store.ingest(1, raw, lambda: lower)[0], 201)
    test.assertEqual(store.ingest(2, final, lambda: lower)[0], 201)

    catalog.blood_pressure_lineage.return_value = all_sightings[2:]
    catalog.receipt.return_value = dict(
        receipt, observed_top_level_rows=10, normalized_bp_top_level_rows=8
    )
    (empty,) = project(
        catalog,
        original,
        scope,
        bounds,
        mapping_key=key,
        record_accounting=private_ledger.append,
    )
    empty_batch = json.loads(empty)
    test.assertTrue(empty_batch["final"])
    test.assertEqual(empty_batch["batch_seq"], 1)
    test.assertEqual(empty_batch["manifest"]["upsert_count"], 0)
    test.assertEqual(private_ledger[-1]["snapshot_excluded_count"], 8)


def verify_admitted_guest(test, root, catalog, original, start, end, exact_batches):
    """Exercise the admitted entry point with fabricated data and loopback mTLS."""
    from pathlib import Path
    from socket import socket
    from unittest.mock import Mock

    from integrations.mse_health_history import typed_vm_admitted as admitted

    root.mkdir(mode=0o700)
    database_dir = root / "pure-synthetic-guest"
    database_dir.mkdir(mode=0o700)
    tls_dir = root / "tls"
    tls_dir.mkdir(mode=0o700)
    bounds = tuple(map(source_time, (start, end)))
    scope = {
        "store_id": "fabricated-admitted-guest",
        "enrollment_id": catalog.enrollment,
        "source_namespace_ref": protected_ref(
            b"m" * 32, "native-namespace", catalog.enrollment, catalog.source_instance
        ),
        "import_ref": "fabricated-exact-import",
        "normalization_version": NORMALIZER,
    }
    raw, final = exact_batches
    test.assertEqual(
        tuple(project(catalog, original, scope, bounds, mapping_key=b"m" * 32)),
        (raw, final),
    )
    manifest = json.loads(final)["manifest"]
    expected = json.loads(batch_receipt(json.loads(final), final, 0, 0))
    purpose = "mother-bp-review"

    def issue(role, *flags):
        cert, key = tls_dir / f"{role}.pem", tls_dir / f"{role}.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                f"/CN=Fabricated {role}",
                "-keyout",
                key,
                "-out",
                cert,
                *flags,
            ],
            check=True,
            capture_output=True,
        )
        cert.chmod(0o600)
        key.chmod(0o600)
        return cert, key

    server_cert, server_key = issue("server", "-addext", "subjectAltName=IP:127.0.0.1")
    roles = {
        r: issue(r, "-addext", "basicConstraints=critical,CA:TRUE")
        for r in ("writer", "receipt", purpose)
    }
    ca = tls_dir / "fabricated-ca.pem"
    ca.write_bytes(b"".join(cert.read_bytes() for cert, _ in roles.values()))
    ca.chmod(0o600)
    with socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    read_end = source_time("2030-01-01T00:00:00Z")
    guest = {
        "bind": "127.0.0.1",
        "port": port,
        "db": str(database_dir / "receipt.sqlite3"),
        "scope": scope,
        "bounds": bounds,
        "artifact": manifest["artifact_receipt_ref"],
        "inventory": manifest["member_inventory_ref"],
        "max_batches": 4,
        "max_bytes": 1024**2,
        "admitted_deletions": [],
        "certificate": str(server_cert),
        "key": str(server_key),
        "client_ca": str(ca),
        "start": bounds[0],
        "end": bounds[1],
        "grants": {
            role: [
                digest(ssl.PEM_cert_to_DER_cert(cert.read_text())),
                bounds[1] if role == "writer" else read_end,
            ]
            for role, (cert, _) in roles.items()
        },
        "snapshots": [
            {
                "snapshot_id": "fabricated-admitted-snapshot",
                "purpose": purpose,
                "subject": "fabricated-purpose-subject",
                "terminal_receipt": expected["receipt_id"],
                "projection_revision": PROJECTION_REVISION,
                "start": bounds[0],
                "end": bounds[1],
                "max_rows": 4,
                "max_bytes": 4096,
            }
        ],
    }
    document = {
        "schema_version": admitted.SCHEMA,
        "mode": "admitted-native-bp-import",
        "encrypted_device_uuid": "CRYPT-LUKS2-fabricated-mapping",
        "reserve_bytes": 256 * 1024**2,
        "catalog_bytes": 16 * 1024**2,
        "server_certificate_sha256": digest(server_cert.read_bytes()),
        "client_ca_sha256": digest(ca.read_bytes()),
        "guest": guest,
    }
    policy_file = root / "fabricated-admission.json"
    original_policy = encoded(document)
    policy_file.write_bytes(original_policy)
    policy_file.chmod(0o600)
    policy_pin = digest(original_policy)
    with test.assertRaisesRegex(ValueError, "digest mismatch"):
        admitted.load_admission(policy_file, "0" * 64)
    policy = admitted.load_admission(policy_file, policy_pin)
    with test.assertRaisesRegex(ValueError, "synthetic guest enrollment required"):
        TypedStore(
            guest["db"],
            scope,
            bounds,
            guest["artifact"],
            guest["inventory"],
            max_batches=4,
            max_bytes=1024**2,
        )
    test.assertFalse(Path(guest["db"]).exists())
    with (
        patch.object(admitted.sys, "platform", "linux"),
        patch.object(Path, "read_text", return_value="CRYPT-LUKS2-wrong"),
        test.assertRaisesRegex(ValueError, "device binding failed"),
    ):
        admitted.check_storage(policy)

    now = bounds[0]
    context = admitted.tls_context(policy)
    preflight = Mock()
    with (
        patch(
            "integrations.mse_health_history.typed_vm_https.PRIVATE",
            (IPv4Network("127.0.0.1/32"),),
        ),
        patch.object(admitted, "check_storage", preflight),
    ):
        store = admitted.admitted_store(policy, policy_pin)
        store.initialize()
        with admitted.AdmittedServer(
            (guest["bind"], port), store, context, policy, clock=lambda: now
        ) as server:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connections = {}
                for role, (cert, key) in roles.items():
                    ctx = ssl.create_default_context(cafile=server_cert)
                    ctx.load_cert_chain(cert, key)
                    connections[role] = TypedClient(guest["bind"], port, scope, ctx)
                writer, reader, consumer = (
                    connections[r] for r in ("writer", "receipt", purpose)
                )
                snap = guest["snapshots"][0]["snapshot_id"]
                test.assertEqual(consumer.put(1, raw)[0], 403)
                test.assertEqual(writer.put(1, raw)[0], 201)
                test.assertEqual(consumer.snapshot(purpose, snap)[0], 404)
                test.assertEqual(writer.put(2, final), (201, expected))
                server.store = admitted.admitted_store(policy, policy_pin)
                test.assertEqual(reader.receipt(2), (200, expected))
                test.assertEqual(writer.snapshot(purpose, snap)[0], 403)
                status, projected = consumer.snapshot(purpose, snap)
                test.assertEqual((status, projected["count"]), (200, 1))
                now = bounds[1]
                test.assertEqual(writer.put(2, final)[0], 403)
                test.assertEqual(reader.receipt(2), (200, expected))
            finally:
                server.shutdown()
                thread.join(5)
    test.assertGreater(preflight.call_count, 1)
    with test.assertRaisesRegex(ValueError, "scope unavailable"):
        admitted.admitted_store(policy, "0" * 64).connect()
