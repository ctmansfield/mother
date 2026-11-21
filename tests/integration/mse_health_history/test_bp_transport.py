"""Synthetic ATLAS-v1 HTTPS conformance without phone, guest, or real records."""

from contextlib import closing, contextmanager
import base64
import http.client
import json
import os
from pathlib import Path
import ssl
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from integrations.mse_health_history.bp_server import BPServer, read_config
from integrations.mse_health_history.bp_transport import BPStore, Sealer, digest
from integrations.mse_health_history.vault import VaultClosed
from integrations.mse_health_history.bp_witness import verify_and_prepare

START = "2026-11-22T00:00:00.000000Z"
END = "2026-11-22T02:00:00.000000Z"
SNAPSHOT = "2026-11-21T00:00:00.000000Z"
SAMPLE = "2025-10-10T12:34:00.000000Z"
ROUTE = "/v1/bp-history/enrollments/demo-enrollment/streams/correlation"
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
        self.client_ca = self.root / "client-ca.pem"
        self.client_ca_key = self.root / "client-ca.key"
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
                "/CN=BP synthetic client CA",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-keyout",
                str(self.client_ca_key),
                "-out",
                str(self.client_ca),
            ],
            check=True,
            capture_output=True,
        )
        self.custodian = self.make_client("custodian")
        self.wrong_client = self.make_client("wrong-client")
        self.custodian_pin = digest(
            ssl.PEM_cert_to_DER_cert(self.custodian[0].read_text())
        )
        raw = {
            "bind": "192.168.78.2",
            "archive_id": "demo-bp",
            "enrollment_id": "demo-enrollment",
            "source_instance": "demo-store",
            "streams": {
                "correlation": "correlation",
                "systolic": "systolic",
                "diastolic": "diastolic",
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
            "custodian_ca_file": str(self.client_ca),
            "custodian_cert_sha256": self.custodian_pin,
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

    def make_client(self, name):
        cert, key, csr = (
            self.root / (name + suffix) for suffix in (".pem", ".key", ".csr")
        )
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=" + name,
                "-keyout",
                str(key),
                "-out",
                str(csr),
            ],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(csr),
                "-CA",
                str(self.client_ca),
                "-CAkey",
                str(self.client_ca_key),
                "-CAcreateserial",
                "-days",
                "1",
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        return cert, key

    def open(self, cls=BPStore):
        return cls(
            self.state,
            self.config,
            self.sealer,
            b"p" * 32,
            clock=lambda: self.now,
        )

    @staticmethod
    def page(
        seq=1,
        prior=None,
        token="A",
        *,
        terminal=False,
        sample=SAMPLE,
        stream="correlation",
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
                "schema_version": "mse.historical-bp-page/0.1",
                "enrollment": "demo-enrollment",
                "source_instance": "demo-store",
                "through": SNAPSHOT,
                "feed": stream,
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
                "deleted_ids": [],
                "exhausted": terminal,
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
        tls.load_verify_locations(cafile=self.client_ca)
        tls.verify_mode = ssl.CERT_OPTIONAL
        self.server_cert = cert
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

    def request(
        self, method, suffix, role, payload=None, *, host="localhost", client_cert=None
    ):
        context = self.ca
        if client_cert:
            context = ssl.create_default_context(cafile=self.server_cert)
            context.load_cert_chain(*client_cert)
        with closing(
            http.client.HTTPSConnection(
                host, self.server.server_port, context=context, timeout=4
            )
        ) as client:
            headers = {"Authorization": "Bearer " + ROLES[role]} if role else {}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            client.request(method, ROUTE + suffix, payload, headers)
            reply = client.getresponse()
            return reply.status, reply.read()

    def proof(self, body):
        status, info = self.request(
            "GET", "/pages/1/custody", None, client_cert=self.custodian
        )
        self.assertEqual(status, 200)
        envelope = json.loads(info)
        path = self.root / "download.age"
        path.touch(mode=0o600)
        path.write_bytes(base64.b64decode(envelope["ciphertext_base64"], validate=True))
        expected = {
            "archive_id": "demo-bp",
            "enrollment": "demo-enrollment",
            "source_instance": "demo-store",
            "through": SNAPSHOT,
            "stream_id": "correlation",
            "feed": "correlation",
            "page_seq": 1,
            "sha256": digest(body),
            "byte_length": len(body),
        }
        return verify_and_prepare(
            envelope,
            expected=expected,
            ciphertext_path=path,
            recipient_fingerprint=self.config["recipient_sha256"],
            age_executable=self.age,
            age_sha256=self.config["age_sha256"],
            identity_file=self.identity,
        )

    def test_https_pending_certificate_binding_then_witnessed_receipt(self):
        self.serve(self.store)
        body = self.page()
        mismatch = json.dumps(
            dict(json.loads(body), through="2026-11-20T00:00:00.000000Z")
        ).encode()
        self.assertEqual(self.request("PUT", "/pages/1", "upload", mismatch)[0], 409)
        pending = self.request("PUT", "/pages/1", "upload", body)
        self.assertEqual(pending[0], 202)
        self.assertEqual(json.loads(pending[1])["status"], "awaiting_custodian_witness")
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body), pending)
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body + b" ")[0], 409)
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), pending)
        self.assertEqual(self.request("GET", "/pages/1/custody", "receipt")[0], 403)
        self.assertEqual(
            self.request(
                "GET", "/pages/1/custody", None, client_cert=self.wrong_client
            )[0],
            403,
        )
        self.assertEqual(
            json.loads(self.request("GET", "/export?from=1&through=1", "export")[1])[
                "rows"
            ],
            [],
        )
        proof = self.proof(body)
        wrong = json.dumps(
            dict(json.loads(proof), recipient_fingerprint="0" * 64)
        ).encode()
        self.assertEqual(
            self.request(
                "PUT", "/pages/1/custody", None, wrong, client_cert=self.custodian
            )[0],
            409,
        )
        self.assertEqual(
            self.request(
                "PUT", "/pages/1/custody", None, proof, client_cert=self.wrong_client
            )[0],
            403,
        )
        code, receipt = self.request(
            "PUT", "/pages/1/custody", None, proof, client_cert=self.custodian
        )
        self.assertEqual(code, 200)
        decoded = json.loads(receipt)
        self.assertEqual(decoded["status"], "typed_and_cursor_durable")
        self.assertEqual(decoded["sha256"], digest(body))
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), (200, receipt))
        self.assertEqual(
            self.request("PUT", "/pages/1", "upload", body), (200, receipt)
        )
        self.assertEqual(
            self.request(
                "PUT", "/pages/1/custody", None, proof, client_cert=self.custodian
            ),
            (200, receipt),
        )
        self.assertEqual(
            json.loads(self.request("GET", "/export?from=1&through=1", "export")[1])[
                "rows"
            ][0]["fact"]["pairing"],
            "paired",
        )
        self.assertNotIn(body, self.store.db.read_bytes())
        self.now = END
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), (200, receipt))

    def test_cutoff_after_sealed_custody_write_stays_hidden(self):
        owner = self

        class Late(BPStore):
            @contextmanager
            def connect(self, *, write=False):
                with super().connect(write=write) as db:
                    yield db
                if write:
                    owner.now = END

        with self.assertRaises(VaultClosed):
            self.open(Late).put("correlation", 1, self.page())
        with self.assertRaises(KeyError):
            self.open().custody("correlation", 1)
        with self.assertRaises(KeyError):
            self.open().receipt("correlation", 1)
        self.assertEqual(self.open().export("correlation", 1, 1)["rows"], [])

    def test_cutoff_after_custodian_proof_keeps_typed_receipt_hidden(self):
        self.serve(self.store)
        body = self.page()
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 202)
        proof = self.proof(body)
        owner = self

        class Late(BPStore):
            @contextmanager
            def connect(self, *, write=False):
                with super().connect(write=write) as db:
                    yield db
                if write:
                    owner.now = END

        with self.assertRaises(VaultClosed):
            self.open(Late).commit(
                "correlation", 1, json.loads(proof), self.custodian_pin, proof
            )
        with self.assertRaises(KeyError):
            self.open().receipt("correlation", 1)
        self.assertEqual(self.open().export("correlation", 1, 1)["rows"], [])
        self.assertEqual(self.request("GET", "/pages/1", "receipt")[0], 403)

    def test_crash_after_proof_commit_is_indeterminate_across_reopen(self):
        class CrashAfterProof(BPStore):
            @contextmanager
            def connect(self, *, write=False):
                with super().connect(write=write) as db:
                    yield db
                if write:
                    raise OSError("synthetic crash before publication observation")

        self.serve(self.store)
        body = self.page()
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 202)
        proof = self.proof(body)
        self.server.store = self.open(CrashAfterProof)
        self.assertEqual(
            self.request(
                "PUT", "/pages/1/custody", None, proof, client_cert=self.custodian
            )[0],
            503,
        )
        self.server.store = self.open()
        headers = {"client_cert": self.custodian}
        indeterminate = (503, b'{"error":"indeterminate"}')
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), indeterminate)
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body), indeterminate)
        self.assertEqual(
            self.request("GET", "/pages/1/custody", None, **headers), indeterminate
        )
        self.assertEqual(
            self.request("PUT", "/pages/1/custody", None, proof, **headers),
            indeterminate,
        )
        with self.assertRaises(KeyError):
            self.open().receipt("correlation", 1)
        self.assertEqual(self.open().export("correlation", 1, 1)["rows"], [])
        with self.open().connect() as db:
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM pages WHERE witness IS NULL AND custodian_proof IS NOT NULL"
                ).fetchone(),
                (1,),
            )
        self.now = END
        for method, path, role, payload, options in (
            ("GET", "/pages/1", "receipt", None, {}),
            ("PUT", "/pages/1", "upload", body, {}),
            ("GET", "/pages/1/custody", None, None, headers),
            ("PUT", "/pages/1/custody", None, proof, headers),
        ):
            self.assertEqual(
                self.request(method, path, role, payload, **options)[0], 403
            )

    def test_lost_final_response_reopens_same_durable_receipt_and_rows(self):
        self.serve(self.store)
        body = self.page()
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 202)
        proof = self.proof(body)
        base = self.server.RequestHandlerClass

        class LoseResponse(base):
            def reply(self, code, content):
                if (
                    code == 200
                    and self.command == "PUT"
                    and self.path.endswith("/custody")
                ):
                    self.close_connection = True
                    return
                super().reply(code, content)

        self.server.RequestHandlerClass = LoseResponse
        with self.assertRaises(http.client.RemoteDisconnected):
            self.request(
                "PUT", "/pages/1/custody", None, proof, client_cert=self.custodian
            )
        self.server.RequestHandlerClass = base
        self.server.store = self.open()
        committed = self.request("GET", "/pages/1", "receipt")
        self.assertEqual(committed[0], 200)
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body), committed)
        self.assertEqual(
            self.request(
                "PUT", "/pages/1/custody", None, proof, client_cert=self.custodian
            ),
            committed,
        )
        self.assertEqual(len(self.open().export("correlation", 1, 1)["rows"]), 1)
        with self.open().connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pages").fetchone(), (1,))
        self.now = END
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), committed)
