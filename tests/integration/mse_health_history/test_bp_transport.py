"""Synthetic ATLAS-v1 HTTPS conformance without phone, guest, or real records."""

from contextlib import closing, contextmanager
import http.client
import json
import os
from pathlib import Path
import sqlite3
import ssl
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from integrations.mse_health_history.bp_server import BPServer, read_config
from integrations.mse_health_history.bp_transport import BPStore, Sealer, digest
from integrations.mse_health_history.vault import VaultClosed, VaultConflict

START = "2026-11-22T00:00:00.000000Z"
END = "2026-11-22T02:00:00.000000Z"
SNAPSHOT = "2026-11-21T00:00:00.000000Z"
SAMPLE = "2025-10-10T12:34:00.000000Z"
ROUTE = "/v1/bp-history/enrollments/demo-enrollment/streams/demo-correlation"
ROLES = dict(zip(("upload", "receipt", "export"), (c * 43 for c in "ABC")))


@unittest.skipUnless(
    os.environ.get("MSE_HISTORY_AGE_BIN"), "requires verified synthetic age executable"
)
class BPTransportTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "store"
        self.state.mkdir(mode=0o700)
        self.now = START
        self.age = Path(os.environ["MSE_HISTORY_AGE_BIN"]).resolve()
        self.identity = self.root / "custodian"
        keygen = self.age.with_name("age-keygen")
        subprocess.run(
            [keygen, "-pq", "-o", self.identity], check=True, capture_output=True
        )
        recipient = self.root / "public"
        recipient.touch(mode=0o600)
        recipient.write_bytes(subprocess.check_output([keygen, "-y", self.identity]))
        raw = {
            "bind": "192.168.78.2",
            "archive_id": "demo-bp",
            "enrollment_id": "demo-enrollment",
            "source_instance": "demo-store",
            "streams": {
                "bp_correlation": "demo-correlation",
                "systolic": "demo-systolic",
                "diastolic": "demo-diastolic",
            },
            "snapshot": {"sample_start_at": None, "sample_end_before": SNAPSHOT},
            "transport_starts_at": START,
            "transport_ends_at": END,
            "enabled": True,
            "max_pages": 8,
            "max_bytes": 2 * 1024**2,
            "reserve_bytes": 32 * 1024**2,
            "age_executable": str(self.age),
            "age_sha256": digest(self.age.read_bytes()),
            "recipient_file": str(recipient),
            "recipient_sha256": digest(recipient.read_bytes()),
            "provenance_key_file": "not-used-in-host-test",
            "grants": {
                r: {
                    "sha256": digest(t.encode()),
                    "expires_at": END if r == "upload" else "2026-11-22T03:00:00Z",
                }
                for r, t in ROLES.items()
            },
        }
        config = self.root / "config.json"
        config.touch(mode=0o600)
        config.write_text(json.dumps(raw))
        self.config = read_config(config)
        self.sealer = Sealer(
            self.age, raw["age_sha256"], recipient, raw["recipient_sha256"]
        )
        self.store = self.open()
        self.store.initialize()

    def open(self, cls=BPStore):
        return cls(
            self.state, self.config, self.sealer, b"p" * 32, clock=lambda: self.now
        )

    @staticmethod
    def page(
        seq=1,
        prior=None,
        token="A",
        *,
        terminal=False,
        sample=SAMPLE,
        stream="demo-correlation",
    ):
        def lineage(n):
            return {
                "uuid": f"00000000-0000-4000-8000-{n:012d}",
                "start": sample,
                "end": sample,
                "source_bundle": "fixture-private-origin",
                "source_version": None,
                "sync_id": None,
                "sync_version": None,
            }

        return json.dumps(
            {
                "schema": "bp-history-page-v1",
                "enrollment_id": "demo-enrollment",
                "stream_id": stream,
                "page_seq": seq,
                "cursor_in": prior,
                "cursor_out": token * 43,
                "upserts": (
                    []
                    if terminal
                    else [
                        {
                            "lineage": lineage(1),
                            "unexpected_component_ids": [],
                            "components": [
                                {
                                    "feed": "systolic",
                                    "lineage": lineage(2),
                                    "mmhg": "121.25",
                                },
                                {
                                    "feed": "diastolic",
                                    "lineage": lineage(3),
                                    "mmhg": "78",
                                },
                            ],
                        }
                    ]
                ),
                "deletions": [],
                "scan_complete": terminal,
            },
            separators=(",", ":"),
        ).encode()

    def serve(self, store):
        cert, key = self.root / "cert", self.root / "key"
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
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        self.ca = ssl.create_default_context(cafile=cert)
        self.server = BPServer(("127.0.0.1", 0), store, tls)
        thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        thread.start()

        def stop():
            self.server.shutdown()
            thread.join(2)
            self.server.server_close()

        self.addCleanup(stop)

    def request(self, method, suffix, role, payload=None, *, host="localhost"):
        with closing(
            http.client.HTTPSConnection(
                host, self.server.server_port, context=self.ca, timeout=4
            )
        ) as client:
            headers = {"Authorization": "Bearer " + ROLES[role]}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            client.request(method, ROUTE + suffix, payload, headers)
            reply = client.getresponse()
            return reply.status, reply.read()

    def test_exact_https_receipt_replay_export_and_off_guest_decryption(self):
        self.serve(self.store)
        body = self.page()
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", "/pages/1", "receipt", host="127.0.0.1")
        self.assertEqual(self.request("PUT", "/pages/1", "receipt", body)[0], 401)
        self.assertEqual(
            self.request("PUT", "/pages/1", "upload", self.page(sample=SNAPSHOT))[0],
            400,
        )
        self.assertEqual(
            self.request("PUT", "/pages/2", "upload", self.page(2))[0], 409
        )
        code, receipt = self.request("PUT", "/pages/1", "upload", body)
        self.assertEqual(code, 201)
        self.assertEqual(json.loads(receipt)["page_sha256"], digest(body))
        self.assertEqual(json.loads(receipt)["schema"], "bp-history-receipt-v1")
        self.assertEqual(
            self.request("PUT", "/pages/1", "upload", body), (200, receipt)
        )
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body + b" ")[0], 409)
        self.assertEqual(self.request("GET", "/pages/1", "upload")[0], 401)
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), (200, receipt))
        self.assertEqual(
            self.request("GET", "/export?from=1&through=1", "receipt")[0], 401
        )
        status, export = self.request("GET", "/export?from=1&through=1", "export")
        self.assertEqual(status, 200)
        self.assertNotIn(b"fixture-private-origin", export)
        self.assertEqual(json.loads(export)["rows"][0]["fact"]["pairing"], "paired")
        terminal = self.page(2, "A" * 43, "B", terminal=True)
        self.assertEqual(self.request("PUT", "/pages/2", "upload", terminal)[0], 201)
        self.assertEqual(
            self.request("PUT", "/pages/3", "upload", self.page(3, "B" * 43, "C"))[0],
            409,
        )
        self.now = END
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 401)
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), (200, receipt))
        with closing(sqlite3.connect(self.store.db)) as db:
            cipher = db.execute(
                "SELECT ciphertext FROM pages WHERE stream='demo-correlation' AND seq=1"
            ).fetchone()[0]
        self.assertNotIn(body, self.store.db.read_bytes())
        self.assertEqual(
            subprocess.run(
                [self.age, "-d", "-i", self.identity],
                input=cipher,
                check=True,
                capture_output=True,
            ).stdout,
            body,
        )
        self.assertEqual(
            self.open().receipt("demo-correlation", 1), json.loads(receipt)
        )

    def test_late_data_commit_leaves_ciphertext_sealed_and_receipt_hidden(self):
        owner = self

        class Late(BPStore):
            @contextmanager
            def connect(self, *, write=False):
                with super().connect(write=write) as db:
                    yield db
                if write:
                    owner.now = END

        with self.assertRaises(VaultClosed):
            self.open(Late).put("demo-correlation", 1, self.page())
        reopened = self.open()
        with self.assertRaises(KeyError):
            reopened.receipt("demo-correlation", 1)
        self.assertEqual(reopened.export("demo-correlation", 1, 1)["rows"], [])
        with closing(sqlite3.connect(self.store.db)) as db:
            self.assertTrue(
                db.execute("SELECT ciphertext FROM pages")
                .fetchone()[0]
                .startswith(b"age-encryption.org/v1")
            )

    def test_three_terminal_streams_hold_independent_sequences_and_unique_tokens(self):
        self.now = "2026-11-21T23:59:59.999999Z"
        with self.assertRaises(VaultClosed):
            self.store.put("demo-correlation", 1, self.page(terminal=True))
        self.now = START
        for stream, token in (
            ("demo-correlation", "A"),
            ("demo-systolic", "B"),
            ("demo-diastolic", "C"),
        ):
            if stream != "demo-correlation":
                with self.assertRaises(VaultConflict):
                    self.store.put(stream, 1, self.page(stream=stream, terminal=True))
            first = self.page(stream=stream, token=token, terminal=True)
            if stream == "demo-correlation":
                vector = json.loads(
                    Path(
                        "integrations/mse_health_history/bp-http-vectors.json"
                    ).read_bytes()
                )
                first = vector["exact_put_utf8"].encode()
                self.assertEqual(
                    self.store.put(stream, 1, first), (201, vector["expected_receipt"])
                )
            else:
                self.assertEqual(self.store.put(stream, 1, first)[0], 201)
            self.assertEqual(self.store.put(stream, 1, first)[0], 200)
            self.assertTrue(self.open().receipt(stream, 1)["scan_complete"])

    def test_witness_persisted_after_pre_cutoff_observation_is_reconcilable(self):
        owner = self

        class LateReply(BPStore):
            writes = 0

            @contextmanager
            def connect(self, *, write=False):
                with super().connect(write=write) as db:
                    yield db
                if write:
                    self.writes += 1
                    if self.writes == 2:
                        owner.now = END

        body = self.page(terminal=True)
        code, receipt = self.open(LateReply).put("demo-correlation", 1, body)
        self.assertEqual(code, 201)
        self.assertEqual(self.open().receipt("demo-correlation", 1), receipt)
        with self.assertRaises(VaultClosed):
            self.open().put("demo-correlation", 1, body)
