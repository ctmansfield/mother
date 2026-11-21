"""Shared synthetic HTTPS exercise for the authenticated native fixture."""

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

from integrations.mse_health_history.blood_pressure import source_time
from integrations.mse_health_history.typed_vm import TypedStore, encoded, project
from integrations.mse_health_history.typed_vm_https import (
    Closed,
    TypedClient,
    TypedHandler,
    TypedServer,
)


def verify_guest(test, root, catalog, original, receipt, start, end):
    start, end = map(source_time, (start, end))
    sender = root / "mac-projection"
    guest = root / "guest"
    sender.mkdir(mode=0o700)
    guest.mkdir(mode=0o700)
    raw = project(catalog, original)
    test.assertEqual(project(catalog, original), raw)
    test.assertEqual(len(json.loads(raw)["rows"]), 1)
    for forbidden in (
        b"apple_health_export",
        b"opaque.gpx",
        b"source_ref",
        b"source_start",
        b"native_ref",
        original.encode(),
    ):
        test.assertNotIn(forbidden, raw)
    scope = (catalog.enrollment, catalog.source_instance, receipt)
    store = TypedStore(guest / "native.sqlite3", *scope)
    store.initialize()
    test.assertRaises(FileExistsError, store.initialize)

    def stop_after_insert():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise Closed("synthetic cutoff before commit")

    checks = 0
    test.assertRaises(Closed, store.ingest, raw, stop_after_insert)
    with closing(store.connect()) as db:
        test.assertEqual(db.execute("SELECT count(*) FROM bp").fetchone(), (0,))
    test.assertRaises(KeyError, store.receipt)

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
    writer = test_bp_transport.BPTransportTests.make_client(
        test, "synthetic-native-writer"
    )
    reader = test_bp_transport.BPTransportTests.make_client(
        test, "synthetic-native-reader"
    )
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(server_cert, server_key)
    server_context.load_verify_locations(cafile=test.client_ca)
    server_context.verify_mode = ssl.CERT_REQUIRED

    def pin(cert):
        return sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()

    now = start
    read_end = source_time("2030-01-01T00:00:00Z")
    with patch(
        "integrations.mse_health_history.typed_vm_https.PRIVATE",
        (IPv4Network("127.0.0.1/32"),),
    ):
        server = TypedServer(
            ("127.0.0.1", 0),
            store,
            server_context,
            {"writer": (pin(writer[0]), end), "reader": (pin(reader[0]), read_end)},
            start,
            end,
            snapshot=(start, end),
            clock=lambda: now,
        )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    test.addCleanup(server.server_close)
    test.addCleanup(thread.join, 5)
    test.addCleanup(server.shutdown)

    def client(credentials, enrollment=scope[0]):
        ctx = ssl.create_default_context(cafile=server_cert)
        if credentials:
            ctx.load_cert_chain(*credentials)
        return TypedClient("127.0.0.1", server.server_port, enrollment, ctx)

    upload, read = client(writer), client(reader)
    test.assertEqual(read.receipt()[0], 404)
    test.assertEqual(read.put(raw)[0], 403)
    test.assertEqual(upload.read(start, end)[0], 403)
    test.assertEqual(client(writer, "synthetic-other").put(raw)[0], 404)
    with test.assertRaises((ssl.SSLError, ConnectionError)):
        client(None).put(raw)
    malformed = json.loads(raw)
    malformed["rows"][0]["raw_path"] = "refuse-me"
    test.assertEqual(upload.put(encoded(malformed))[0], 400)

    reply = TypedHandler.reply

    def lose_committed_response(handler, status, body):
        if status != 201:
            return reply(handler, status, body)

    with patch.object(TypedHandler, "reply", lose_committed_response):
        with test.assertRaises(RemoteDisconnected):
            upload.put(raw)
    reopened = TypedStore(store.path, *scope)
    server.store = reopened
    status, expected = read.receipt()
    test.assertEqual(status, 200)
    read.verify_receipt(raw, expected)
    test.assertEqual(upload.put(raw), (200, expected))
    changed = json.loads(raw)
    changed["rows"][0]["systolic"] = "125"
    test.assertEqual(upload.put(encoded(changed))[0], 409)
    now = end
    test.assertEqual(upload.put(raw)[0], 403)
    test.assertEqual(read.receipt(), (200, expected))
    read.verify_receipt(raw, expected)
    status, result = read.read(start, end)
    test.assertEqual(status, 200)
    test.assertEqual(result["rows"][0]["systolic"], "124.5")
    test.assertEqual(len(result["rows"]), 1)
    test.assertEqual(read.read(start, read_end)[0], 400)
    with closing(reopened.connect()) as db:
        with test.assertRaises(sqlite3.OperationalError):
            db.execute("DELETE FROM bp")
    now = read_end
    test.assertEqual(read.receipt()[0], 403)
