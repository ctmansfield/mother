from hashlib import sha256
from datetime import datetime, timezone, timedelta
import http.client
import json
from pathlib import Path
import ssl
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch

from integrations.mse_archive_service.server import (
    ArchiveServer,
    main,
    tls_context,
)
from integrations.mse_archive_service.store import PrivateArchive
from integrations.mse_archive_service.load_export import load
from integrations.mse_ingest import Scope
from mother.physiology.contracts import canonical_json

TOKENS = {
    role: char * 43
    for role, char in zip(("phone", "reader", "exporter", "evidence"), "ABCD")
}
FIXTURES = Path("tests/fixtures/mse_integration/source-compatible")


class PrivateHTTPSTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.original = (FIXTURES / "baseline.json").read_bytes()
        self.changed = (FIXTURES / "late.json").read_bytes()
        self.digest = sha256(self.original).hexdigest()
        self.scope = Scope(
            "synthetic-archive-test", "healthkit", "synthetic-store", "healtharchive"
        )
        self.config = {
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "token_sha256": {
                role: sha256(token.encode()).hexdigest()
                for role, token in TOKENS.items()
            },
            "allowed_artifact_sha256": [self.digest, sha256(self.changed).hexdigest()],
        }
        self.archive = self.open_archive()
        self.archive.initialize()
        self.archive.check_startup()
        self.cert, self.key = self.root / "cert.pem", self.root / "key.pem"
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
                "-keyout",
                str(self.key),
                "-out",
                str(self.cert),
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        self.client_context = ssl.create_default_context(cafile=self.cert)

    def open_archive(self):
        return PrivateArchive(
            self.root / "store", archive_id="trial-archive", scope=self.scope
        )

    def launch(self, archive):
        self.server = ArchiveServer(
            ("127.0.0.1", 0),
            archive=archive,
            config=self.config,
            context=tls_context(self.cert, self.key),
        )
        self.thread = Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.02}
        )
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        if self.thread.is_alive():
            self.server.shutdown()
            self.thread.join(2)
            self.server.server_close()

    def request(
        self, method, path, role=None, body=None, *, context=None, host="localhost"
    ):
        client = http.client.HTTPSConnection(
            host,
            self.server.server_port,
            context=context or self.client_context,
            timeout=3,
        )
        headers = {"Content-Type": "application/json"} if body is not None else {}
        if role is not None:
            headers["Authorization"] = "Bearer " + TOKENS[role]
        try:
            client.request(method, path, body=body, headers=headers)
            response = client.getresponse()
            self.assertEqual(response.getheader("Cache-Control"), "no-store")
            payload = response.read()
            return response.status, (
                json.loads(payload)
                if response.getheader("Content-Type") == "application/json"
                else payload
            )
        finally:
            client.close()

    def test_receipt_restart_permissions_and_operator_lineage(self):
        self.launch(self.archive)
        endpoint = "/v1/archive/batches/test-batch"
        self.assertEqual(self.request("GET", endpoint, "phone")[0], 404)
        status, receipt = self.request("PUT", endpoint, "phone", self.original)
        self.assertEqual(status, 200)
        self.assertEqual(receipt["status"], "normalized")
        self.assertEqual(receipt["artifact_sha256"], self.digest)
        self.assertEqual(receipt["scope"], self.scope.fields())
        self.assertEqual(
            self.request("PUT", endpoint, "phone", self.original), (200, receipt)
        )
        self.assertEqual(self.request("PUT", endpoint, "phone", self.changed)[0], 409)
        self.assertEqual(self.request("PUT", endpoint, "phone", b"{}")[0], 400)
        self.assertEqual(self.request("PUT", endpoint, "reader", self.original)[0], 404)
        self.stop()
        reopened = self.open_archive()
        reopened.check_startup()
        self.launch(reopened)
        self.assertEqual(self.request("GET", endpoint, "phone"), (200, receipt))
        query = f"?from=1&through={receipt['commit_sequence']}"
        for kind, role in (
            ("receipts", "reader"),
            ("revisions", "reader"),
            ("export", "exporter"),
        ):
            path = "/v1/archive/operator/" + kind + query
            self.assertEqual(self.request("GET", path, "phone")[0], 404)
            status, content = self.request("GET", path, role)
            self.assertEqual(status, 200)
            if kind == "export":
                self.assertEqual(
                    content["view_sha256"],
                    sha256(canonical_json(content["view"]).encode()).hexdigest(),
                )
                self.assertEqual(content["row_count"], len(content["view"]["rows"]))
            if kind == "revisions":
                self.assertTrue(
                    any(
                        row["source_revision"]["operation"] == "delete"
                        for row in content["rows"]
                    )
                )
        original_endpoint = "/v1/archive/operator/originals/" + self.digest
        self.assertEqual(self.request("GET", original_endpoint, "reader")[0], 404)
        self.assertEqual(
            self.request("GET", original_endpoint, "evidence"), (200, self.original)
        )

    def test_tls_trust_hostname_and_plaintext_refusal(self):
        self.launch(self.archive)
        endpoint = "/v1/archive/batches/test-batch"
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", endpoint, "phone", context=ssl.create_default_context())
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", endpoint, "phone", host="127.0.0.1")
        client = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3
        )
        try:
            with self.assertRaises((OSError, http.client.RemoteDisconnected)):
                client.request("GET", endpoint)
                client.getresponse()
        finally:
            client.close()

    def test_join_and_portable_transfer_preserve_exact_relations(self):
        self.launch(self.archive)
        receipts = []
        for name in ("first", "second"):
            status, receipt = self.request(
                "PUT",
                "/v1/archive/batches/" + name,
                "phone",
                self.original,
            )
            self.assertEqual(status, 200)
            receipts.append(receipt)
        query = f"?from=1&through={receipts[-1]['commit_sequence']}"
        status, joined = self.request(
            "GET", "/v1/archive/operator/relations" + query, "reader"
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            set(row["receipt_id"] for row in joined["rows"]),
            {receipt["receipt_id"] for receipt in receipts},
        )
        self.assertEqual(len(joined["rows"]), 10)
        first_ids = {
            row["source_revision_id"]
            for row in joined["rows"]
            if row["receipt_id"] == receipts[0]["receipt_id"]
        }
        second_ids = {
            row["source_revision_id"]
            for row in joined["rows"]
            if row["receipt_id"] == receipts[1]["receipt_id"]
        }
        self.assertEqual(first_ids, second_ids)
        self.assertTrue(
            any(row["processing_revision_id"] is None for row in joined["rows"])
        )
        self.assertTrue(
            any(
                row["source_revision"]["operation"] == "delete"
                for row in joined["rows"]
            )
        )
        status, exported = self.request(
            "GET", "/v1/archive/operator/export" + query, "exporter"
        )
        self.assertEqual(status, 200)
        self.assertEqual(exported["view"], joined)
        self.assertEqual(
            self.request("GET", "/v1/archive/operator/export" + query, "reader")[0], 404
        )
        self.assertEqual(
            self.request(
                "GET", "/v1/archive/operator/originals/" + self.digest, "exporter"
            )[0],
            404,
        )
        data = canonical_json(exported).encode()
        output = self.root / "downstream.sqlite3"
        load(data, output, expected_sha256=sha256(data).hexdigest())
        with sqlite3.connect(output) as db:
            actual = db.execute(
                "SELECT receipt_id,source_revision_id,processing_key,decimal_value,unit "
                "FROM receipt_revisions"
            ).fetchall()
        expected = []
        for row in joined["rows"]:
            observation = row["source_revision"].get("observation", {})
            expected.append(
                (
                    row["receipt_id"],
                    row["source_revision_id"],
                    row["processing_revision_id"] or "",
                    observation.get("value"),
                    observation.get("unit"),
                )
            )
        self.assertCountEqual(actual, expected)
        self.assertIn(("41.5", "ms"), {(row[-2], row[-1]) for row in actual})

    def test_startup_refuses_identity_drift_and_reinitialization(self):
        with self.assertRaisesRegex(ValueError, "fresh"):
            self.archive.initialize()
        other = PrivateArchive(
            self.root / "store", archive_id="different", scope=self.scope
        )
        with self.assertRaisesRegex(ValueError, "mismatch"):
            other.check_startup()

    def test_cli_bind_requires_exact_private_address(self):
        config_path = self.root / "config.json"
        config_path.touch(mode=0o600)
        config = {
            **self.config,
            "archive_id": "trial-archive",
            "scope": vars(self.scope),
            "expires_at": self.config["expires_at"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        command = [
            "server",
            "serve",
            "--config",
            str(config_path),
            "--root",
            str(self.root / "store"),
            "--port",
            "8443",
            "--cert",
            str(self.cert),
            "--key",
            str(self.key),
        ]
        for expected, bind, allowed in (
            (None, "100.64.0.2", True),
            (None, "192.168.80.2", False),
            ("192.168.80.2", "192.168.80.2", True),
            ("192.168.80.2", "192.168.80.3", False),
            ("192.168.80.2", "100.64.0.2", False),
            ("192.168.80.2", "0.0.0.0", False),
            ("192.168.80.2", "127.0.0.1", False),
            ("192.168.80.2", "::", False),
            ("0.0.0.0", "0.0.0.0", False),
            ("8.8.8.8", "8.8.8.8", False),
            ("100.64.0.2", "100.64.0.2", False),
            (123, "192.168.80.2", False),
        ):
            with self.subTest(expected=expected, bind=bind):
                settings = dict(config)
                if expected is not None:
                    settings["expected_guest_ipv4"] = expected
                config_path.write_text(json.dumps(settings))
                with (
                    patch("sys.argv", [*command, "--bind", bind]),
                    patch("sys.stderr"),
                    patch(
                        "integrations.mse_archive_service.server.ArchiveServer"
                    ) as server,
                ):
                    self.assertEqual(main(), None if allowed else 1)
                    if allowed:
                        self.assertEqual(server.call_args.args[0], (bind, 8443))
                    else:
                        server.assert_not_called()
