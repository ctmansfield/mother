"""Synthetic ATLAS-v1 HTTPS conformance without phone, guest, or real records."""

from contextlib import closing, contextmanager
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
from integrations.mse_health_history.bp_witness import (
    CustodianVerifier,
    authenticate_and_sign,
)

START = "2026-11-22T00:00:00.000000Z"
END = "2026-11-22T02:00:00.000000Z"
SNAPSHOT = "2026-11-21T00:00:00.000000Z"
SAMPLE = "2025-10-10T12:34:00.000000Z"
ROUTE = "/v1/bp-history/enrollments/demo-enrollment/streams/correlation"
ROLES = dict(
    zip(("upload", "receipt", "export", "custodian"), (c * 43 for c in "ABCD"))
)


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
        self.openssl = os.environ.get("MSE_HISTORY_OPENSSL", "/usr/bin/openssl")
        self.signing = self.root / "signing.pem"
        public = self.root / "signing-public.pem"
        subprocess.run(
            [self.openssl, "genpkey", "-algorithm", "ED25519", "-out", self.signing],
            check=True,
        )
        self.signing.chmod(0o600)
        public.touch(mode=0o600)
        public.write_bytes(
            subprocess.check_output(
                [self.openssl, "pkey", "-in", self.signing, "-pubout"]
            )
        )
        self.verifier = CustodianVerifier(
            public, digest(public.read_bytes()), self.openssl
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
            "custodian_public_key_file": str(public),
            "custodian_public_sha256": digest(public.read_bytes()),
            "openssl_executable": self.openssl,
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
            self.state,
            self.config,
            self.sealer,
            b"p" * 32,
            clock=lambda: self.now,
            verify_custodian=self.verifier,
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

    def proof(self, body, seq=1, *, change_receipt_id=False):
        status, info = self.request("GET", f"/pages/{seq}/custody", "custodian")
        self.assertEqual(status, 200)
        statement = json.loads(info)
        if change_receipt_id:
            statement["typed_receipt_id"] = "f" * 64
        status, cipher = self.request("GET", f"/pages/{seq}/ciphertext", "custodian")
        self.assertEqual(status, 200)
        path = self.root / "download.age"
        if not path.exists():
            path.touch(mode=0o600)
        path.write_bytes(cipher)
        return authenticate_and_sign(
            statement,
            expected_binding={
                "archive_id": "demo-bp",
                "enrollment_id": "demo-enrollment",
                "source_instance": "demo-store",
                "feed": "correlation",
                "page_seq": seq,
                "plaintext_sha256": digest(body),
                "plaintext_length": len(body),
            },
            signing_key=self.signing,
            openssl=self.openssl,
            ciphertext=path,
            recipient_fingerprint=self.config["recipient_sha256"],
            age_executable=self.age,
            age_sha256=self.config["age_sha256"],
            identity_file=self.identity,
        )

    def test_https_pending_tamper_wrong_role_then_witnessed_receipt(self):
        self.serve(self.store)
        body = self.page()
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 202)
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body)[0], 202)
        self.assertEqual(self.request("PUT", "/pages/1", "upload", body + b" ")[0], 409)
        self.assertEqual(self.request("GET", "/pages/1", "receipt")[0], 202)
        self.assertEqual(self.request("GET", "/pages/1/ciphertext", "receipt")[0], 401)
        self.assertEqual(
            json.loads(self.request("GET", "/export?from=1&through=1", "export")[1])[
                "rows"
            ],
            [],
        )
        proof = self.proof(body)
        invalid = dict(proof, signature="A" * 86)
        self.assertEqual(
            self.request(
                "POST", "/pages/1/commit", "custodian", json.dumps(invalid).encode()
            )[0],
            400,
        )
        self.assertEqual(
            self.request(
                "POST", "/pages/1/commit", "receipt", json.dumps(proof).encode()
            )[0],
            401,
        )
        wrong_page = self.proof(body, change_receipt_id=True)
        self.assertEqual(
            self.request(
                "POST", "/pages/1/commit", "custodian", json.dumps(wrong_page).encode()
            )[0],
            409,
        )
        code, receipt = self.request(
            "POST", "/pages/1/commit", "custodian", json.dumps(proof).encode()
        )
        self.assertEqual(code, 200)
        decoded = json.loads(receipt)
        self.assertEqual(
            self.request(
                "POST", "/pages/1/commit", "custodian", json.dumps(proof).encode()
            ),
            (200, receipt),
        )
        self.assertEqual(
            decoded["schema_version"], "mse.historical-bp-page-receipt/0.1"
        )
        self.assertEqual(decoded["status"], "typed_and_cursor_durable")
        self.assertEqual(decoded["sha256"], digest(body))
        self.assertEqual(
            decoded["ciphertext_receipt"], proof["statement"]["ciphertext_receipt"]
        )
        self.assertEqual(self.request("GET", "/pages/1", "receipt"), (200, receipt))
        self.assertEqual(
            self.request("PUT", "/pages/1", "upload", body), (200, receipt)
        )
        export = self.request("GET", "/export?from=1&through=1", "export")[1]
        self.assertNotIn(b"fixture-private-origin", export)
        self.assertEqual(json.loads(export)["rows"][0]["fact"]["pairing"], "paired")
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
                "correlation", 1, proof["statement"], proof["signature"]
            )
        with self.assertRaises(KeyError):
            self.open().receipt("correlation", 1)
        self.assertEqual(self.open().export("correlation", 1, 1)["rows"], [])
        self.assertEqual(self.request("GET", "/pages/1", "receipt")[0], 404)
