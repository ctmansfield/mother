"""Opaque ciphertext transport, resume and role boundaries with synthetic bytes."""

from contextlib import closing
from dataclasses import replace
from hashlib import sha256
import http.client
import json
from pathlib import Path
from shutil import disk_usage
import socket
import ssl
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest

from integrations.mse_health_history.vault import (
    CiphertextVault,
    Enrollment,
    VaultCapacity,
    VaultClosed,
    utc,
)
from integrations.mse_health_history.vault_server import Server

NOW = "2026-11-21T00:00:00.000000Z"
END = "2026-11-21T01:00:00.000000Z"
LATER = "2026-11-21T02:00:00.000000Z"
TOKENS = dict(zip(("upload", "receipt", "ciphertext"), (c * 43 for c in "ABC")))
ROUTE = "/v1/history/imports/test-import"


class VaultTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "vault"
        self.state.mkdir(mode=0o700)
        self.now = NOW
        self.body = b"fabricated-opaque-ciphertext"
        self.enrollment = Enrollment(
            "synthetic-vault",
            "test-import",
            "e" * 64,
            sha256(self.body).hexdigest(),
            len(self.body),
            END,
            12 * 1024**3,
            16 * 1024**3,
            True,
        )
        self.vault = self.open_vault()
        self.vault.initialize()

    def open_vault(self, enrollment=None, free=50 * 1024**3):
        return CiphertextVault(
            self.state,
            self.enrollment if enrollment is None else enrollment,
            clock=lambda: utc(self.now),
            disk_usage=lambda _: disk_usage(".")._replace(free=free),
        )

    def upload(self, vault, offset, body):
        return vault.put(offset, len(self.body), body, sha256(body).hexdigest())

    def start(self):
        cert, key = self.root / "cert.pem", self.root / "key.pem"
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
            timeout=10,
        )
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.minimum_version = ssl.TLSVersion.TLSv1_2
        server_context.load_cert_chain(cert, key)
        self.context = ssl.create_default_context(cafile=cert)
        grants = {
            role: {
                "sha256": sha256(token.encode()).hexdigest(),
                "expires_at": utc(END if role == "upload" else LATER),
            }
            for role, token in TOKENS.items()
        }
        self.server = Server(("127.0.0.1", 0), self.vault, grants, server_context)
        thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02}
        )
        thread.start()

        def stop():
            self.server.shutdown()
            thread.join(2)
            self.server.server_close()

        self.addCleanup(stop)

    def request(
        self, method, path, role, *, body=None, offset=0, host="localhost", context=None
    ):
        headers = {"Authorization": "Bearer " + TOKENS[role]}
        if body is not None:
            headers.update(
                {
                    "Content-Type": "application/octet-stream",
                    "Content-Range": f"bytes {offset}-{offset+len(body)-1}/{len(self.body)}",
                    "X-Chunk-SHA256": sha256(body).hexdigest(),
                }
            )
        with closing(
            http.client.HTTPSConnection(
                host,
                self.server.server_port,
                context=context or self.context,
                timeout=3,
            )
        ) as client:
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            return response.status, response.read()

    def test_interruption_restart_exact_replay_and_authorized_readback(self):
        self.start()
        prefix = self.body[:10]
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=prefix)[0], 202)
        tail = self.body[10:]
        # Interrupt a second framed request before the complete chunk is received.
        with socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=3
        ) as raw:
            with self.context.wrap_socket(
                raw, server_hostname="localhost"
            ) as interrupted:
                interrupted.sendall(
                    (
                        f"PUT {ROUTE} HTTP/1.1\r\nHost: localhost\r\n"
                        f"Authorization: Bearer {TOKENS['upload']}\r\n"
                        f"Content-Type: application/octet-stream\r\n"
                        f"Content-Length: {len(tail)}\r\n"
                        f"Content-Range: bytes 10-{len(self.body)-1}/{len(self.body)}\r\n"
                        f"X-Chunk-SHA256: {sha256(tail).hexdigest()}\r\n\r\n"
                    ).encode()
                    + tail[:1]
                )
        self.assertEqual(
            json.loads(self.request("GET", ROUTE + "/progress", "upload")[1])[
                "next_offset"
            ],
            10,
        )
        self.assertEqual(self.request("GET", ROUTE, "receipt")[0], 404)
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=prefix)[0], 202)
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=b"x" * 10)[0], 409)
        self.assertEqual(
            self.request("PUT", ROUTE, "upload", body=tail[1:], offset=11)[0], 409
        )
        reopened = self.open_vault()
        reopened.check_startup()
        finished = self.upload(reopened, 10, tail)
        self.assertEqual(finished["status"], "opaque_ciphertext_durable")
        self.assertEqual(self.upload(reopened, 0, prefix), finished)
        self.assertEqual(json.loads(self.request("GET", ROUTE, "receipt")[1]), finished)
        self.assertEqual(
            self.request("GET", ROUTE + "/ciphertext?offset=0", "receipt")[0], 401
        )
        self.assertEqual(
            self.request("GET", ROUTE + "/ciphertext?offset=0", "ciphertext"),
            (200, self.body),
        )
        self.now = END
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=prefix)[0], 401)
        self.assertEqual(self.request("GET", ROUTE, "receipt")[0], 200)

    def test_trust_capacity_cutoff_and_final_digest_conflict(self):
        self.start()
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", ROUTE, "receipt", host="127.0.0.1")
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", ROUTE, "receipt", context=ssl.create_default_context())
        with self.assertRaises(VaultCapacity):
            self.upload(
                self.open_vault(free=self.enrollment.reserve_bytes), 0, self.body
            )
        with self.assertRaises(VaultClosed):
            self.upload(
                self.open_vault(replace(self.enrollment, enabled=False)), 0, self.body
            )
        self.assertEqual(
            self.request("PUT", ROUTE, "upload", body=b"x" * len(self.body))[0], 409
        )
        self.assertFalse(self.vault.progress()["complete"])
        self.assertFalse(self.vault.committed.exists())
        self.now = END
        with self.assertRaises(VaultClosed):
            self.upload(self.vault, 0, self.body)

    def test_reopened_prepublication_original_can_reconcile_only_before_cutoff(self):
        self.vault.original.write_bytes(self.body)
        self.vault.original.chmod(0o600)
        reopened = self.open_vault()
        with self.assertRaises(KeyError):
            reopened.receipt()
        self.now = END
        with self.assertRaises(VaultClosed):
            self.upload(reopened, 0, self.body)
        with self.assertRaises(KeyError):
            reopened.retrieve(0)
        self.assertEqual(self.vault.original.read_bytes(), self.body)

    def test_cutoff_after_receipt_fsync_keeps_object_and_receipt_sealed(self):
        self.start()
        original_sync = self.vault._sync_dir

        def sync():
            original_sync()
            if self.vault.committed.exists() and not self.vault.witness.exists():
                self.now = END

        self.vault._sync_dir = sync
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=self.body)[0], 403)
        reopened = self.open_vault()
        reopened.check_startup()
        self.assertEqual(reopened.original.read_bytes(), self.body)
        self.assertFalse(reopened.progress()["complete"])
        self.assertEqual(self.request("GET", ROUTE, "receipt")[0], 404)
        self.assertEqual(
            self.request("GET", ROUTE + "/ciphertext?offset=0", "ciphertext")[0], 404
        )
        with self.assertRaises(VaultClosed):
            self.upload(reopened, 0, self.body)

    def test_crash_before_witness_does_not_infer_receipt_on_reopen(self):
        original_sync = self.vault._sync_dir

        def sync():
            original_sync()
            if self.vault.committed.exists() and not self.vault.witness.exists():
                raise OSError("synthetic crash before cutoff observation")

        self.vault._sync_dir = sync
        with self.assertRaises(OSError):
            self.upload(self.vault, 0, self.body)
        reopened = self.open_vault()
        reopened.check_startup()
        with self.assertRaises(KeyError):
            reopened.receipt()
        with self.assertRaises(KeyError):
            reopened.retrieve(0)
        # An explicit in-window exact retry can rehash and reverify the
        # durable files. Startup alone must never synthesize a witness.
        self.assertEqual(self.upload(reopened, 0, self.body), reopened.receipt())

    def test_witness_fsync_crossing_cutoff_returns_already_verified_receipt(self):
        self.start()
        original_sync = self.vault._sync_dir

        def sync():
            original_sync()
            if self.vault.witness.exists():
                self.now = END

        self.vault._sync_dir = sync
        code, receipt = self.request("PUT", ROUTE, "upload", body=self.body)
        self.assertEqual(code, 200)
        reopened = self.open_vault()
        reopened.check_startup()
        self.assertEqual(reopened.receipt(), json.loads(receipt))
        self.assertEqual(reopened.retrieve(0), self.body)
        self.assertEqual(self.request("PUT", ROUTE, "upload", body=self.body)[0], 401)
