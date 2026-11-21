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

    def open_store():
        return TypedStore(
            guest / "native.sqlite3",
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
            store.ingest(seq, raw, lambda: None), (201, encoded(entry["receipt"]))
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
