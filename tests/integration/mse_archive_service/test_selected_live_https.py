"""Qualify the prospective selected endpoint using fabricated HealthKit records."""

from contextlib import closing, contextmanager
from dataclasses import replace
from hashlib import sha256
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
from unittest.mock import patch

from integrations.mse_archive_service.selected import (
    MAX_BYTES,
    Pilot,
    PilotClosed,
    SelectedArchive,
)
from integrations.mse_archive_service.selected_server import (
    SelectedServer,
    load_config,
    main,
)
from integrations.mse_archive_service.server import tls_context
from mother.physiology.contracts import canonical_json

START = "2026-11-21T00:00:00.000000Z"
BEFORE = "2026-11-20T23:59:59.999999Z"
NOW = "2026-11-21T01:00:00.000000Z"
END = "2026-11-23T00:00:00.000000Z"
LATER = "2026-11-24T00:00:00.000000Z"
ROLES = dict(
    zip(
        ("phone", "reader", "exporter", "evidence"),
        ("A" * 43, "B" * 43, "C" * 43, "D" * 43),
    )
)
VECTORS = Path("docs/mse/integration/selected-healthkit/synthetic-vectors.json")
BATCH = "/v2/archive/batches/"
OP = "/v2/archive/operator/"


class SelectedLiveTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "selected"
        self.state.mkdir(mode=0o700)
        self.now = NOW
        self.pilot = Pilot("pilot-fixture", START, END, True, 32, 32 * 1024**2)
        self.batch = json.loads(VECTORS.read_bytes())["batch"]
        self.scope = dict(self.batch["scope"], subject_id="pilot-fabricated-subject")
        self.records = [
            row for row in self.batch["records"] if row["operation"] == "upsert"
        ]
        self.config = {
            "grants": {
                role: {
                    "sha256": sha256(token.encode()).hexdigest(),
                    "expires_at": END if role == "phone" else LATER,
                }
                for role, token in ROLES.items()
            }
        }

    def archive(self, pilot=None, cls=SelectedArchive):
        return cls(
            self.state,
            archive_id="pilot-fabricated-archive",
            scope=self.scope,
            pilot=self.pilot if pilot is None else pilot,
            clock=lambda: self.now,
        )

    def body(self, name, records=None, scope=None):
        data = dict(
            self.batch,
            batch_id=name,
            scope=self.scope if scope is None else scope,
            records=self.records if records is None else records,
        )
        return (canonical_json(data) + "\n").encode()

    def start(self, archive):
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
            timeout=10,
        )
        self.context = ssl.create_default_context(cafile=cert)
        self.server = SelectedServer(
            ("127.0.0.1", 0),
            archive=archive,
            config=self.config,
            context=tls_context(cert, key),
        )
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
        self,
        method,
        path,
        role=None,
        body=None,
        *,
        host="localhost",
        context=None,
        headers=None,
    ):
        request_headers = dict(headers or {})
        if body is not None:
            request_headers.setdefault("Content-Type", "application/json")
        if role is not None:
            request_headers["Authorization"] = "Bearer " + ROLES[role]
        with closing(
            http.client.HTTPSConnection(
                host,
                self.server.server_port,
                context=context or self.context,
                timeout=3,
            )
        ) as client:
            client.request(method, path, body, request_headers)
            response = client.getresponse()
            return response.status, response.read()

    def test_tls_scope_role_delivery_and_retention(self):
        archive = self.archive()
        archive.initialize()
        archive.prepare_release()
        self.start(archive)
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request("GET", BATCH + "initial", "phone", host="127.0.0.1")
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request(
                "GET", BATCH + "initial", "phone", context=ssl.create_default_context()
            )
        body = self.body("initial")
        self.assertEqual(self.request("PUT", BATCH + "initial", "reader", body)[0], 401)
        wrong_scope = self.body(
            "initial", scope=dict(self.scope, source_instance="other")
        )
        self.assertEqual(
            self.request("PUT", BATCH + "initial", "phone", wrong_scope)[0], 400
        )
        self.assertEqual(
            self.request("PUT", BATCH + "initial", "phone", b"x" * (MAX_BYTES + 1))[0],
            413,
        )
        self.assertEqual(
            self.request(
                "PUT",
                BATCH + "initial",
                "phone",
                body,
                headers={"Content-Encoding": "gzip"},
            )[0],
            415,
        )
        self.assertEqual(
            self.request(
                "PUT",
                BATCH + "initial",
                "phone",
                body.replace(b'"scope":', b'"scope":{},"scope":', 1),
            )[0],
            400,
        )
        status, raw_receipt = self.request("PUT", BATCH + "initial", "phone", body)
        self.assertEqual(status, 200)
        receipt = json.loads(raw_receipt)
        self.assertEqual(receipt["artifact_sha256"], sha256(body).hexdigest())
        self.assertEqual(
            self.request("PUT", BATCH + "initial", "phone", body), (200, raw_receipt)
        )
        self.assertEqual(
            self.request("PUT", BATCH + "initial", "phone", body + b" ")[0], 409
        )
        self.assertEqual(
            self.request("GET", OP + "originals/initial", "reader")[0], 401
        )
        self.assertEqual(
            self.request("GET", OP + "originals/initial", "evidence"), (200, body)
        )
        export = OP + "export?from=1&through=1"
        self.assertEqual(self.request("GET", export, "phone")[0], 401)
        self.assertEqual(self.request("GET", export, "reader")[0], 401)
        self.now = END
        self.assertEqual(
            self.request("PUT", BATCH + "late", "phone", self.body("late"))[0], 401
        )
        self.assertEqual(self.request("GET", BATCH + "initial", "phone")[0], 401)
        self.assertEqual(
            self.request("GET", OP + "receipts/initial", "reader"), (200, raw_receipt)
        )
        status, data = self.request("GET", export, "exporter")
        self.assertEqual(status, 200)
        self.assertEqual(
            [row["record"] for row in json.loads(data)["view"]["rows"]], self.records
        )
        reopened = self.archive()
        reopened.check_startup()
        self.assertEqual(reopened.get("initial"), receipt)
        self.assertEqual(reopened.original("initial"), body)
        with self.assertRaises(KeyError):
            reopened.get("late")

    def test_staged_start_bounds_tombstones_and_immutable_window(self):
        staged = self.archive(replace(self.pilot, start=None, end=None, enabled=False))
        staged.initialize()
        with self.assertRaises(PilotClosed):
            staged.put("staged", self.body("staged"))
        archive = self.archive()
        archive.prepare_release()
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.archive(
                replace(self.pilot, start=NOW, end="2026-11-23T01:00:00.000000Z")
            ).prepare_release()
        point = dict(
            self.records[0],
            event_start=START,
            event_end=START,
            collector_received_at=START,
        )
        self.now = BEFORE
        with self.assertRaises(PilotClosed):
            archive.put("point", self.body("point", [point]))
        self.now = START
        with self.assertRaisesRegex(ValueError, "interval"):
            archive.put("old", self.body("old", [dict(point, event_start=BEFORE)]))
        with self.assertRaisesRegex(ValueError, "interval"):
            archive.put("future", self.body("future", [dict(point, event_end=END)]))
        deletion = {
            key: point[key] for key in ("metric", "native_id", "collector_received_at")
        }
        deletion["operation"] = "delete"
        with self.assertRaisesRegex(ValueError, "pilot-observed"):
            archive.put("unknown", self.body("unknown", [deletion]))
        archive.put("point", self.body("point", [point]))
        self.now = NOW
        with self.assertRaisesRegex(ValueError, "interval"):
            archive.put(
                "not-yet-observed",
                self.body("not-yet-observed", [dict(point, event_end=NOW)]),
            )
        archive.put("delete", self.body("delete", [deletion]))
        current = json.loads(archive.export(1, 2, current=True))["view"]
        self.assertEqual(current["rows"], [])
        self.now = END
        with self.assertRaises(PilotClosed):
            archive.put("post", self.body("post", [point]))
        self.assertTrue(archive.mark_cutoff())
        self.now = NOW
        with self.assertRaises(PilotClosed):
            self.archive().put("rollback-clock", self.body("rollback-clock", [point]))
        self.assertEqual(self.archive().get("point")["status"], "normalized")

    def test_inflight_durable_after_cutoff_is_never_published(self):
        owner = self

        class LateCommit(SelectedArchive):
            @contextmanager
            def _connection(self, *, write=False):
                with super()._connection(write=write) as db:
                    yield db
                if write:
                    owner.now = END

        archive = self.archive()
        archive.initialize()
        archive.prepare_release()
        late = self.archive(cls=LateCommit)
        with self.assertRaises(PilotClosed):
            late.put("late-durable", self.body("late-durable"))
        with self.assertRaises(KeyError):
            self.archive().get("late-durable")
        self.assertEqual(json.loads(archive.export(1, 1))["view"]["rows"], [])
        with sqlite3.connect(archive.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM batches").fetchone(), (1,)
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM pilot_publication").fetchone(), (0,)
            )

    def test_capacity_rate_and_expiry(self):
        archive = self.archive(replace(self.pilot, max_commits=1))
        archive.initialize()
        archive.prepare_release()
        self.start(archive)
        first = self.body("one")
        self.assertEqual(self.request("PUT", BATCH + "one", "phone", first)[0], 200)
        self.assertEqual(
            self.request("PUT", BATCH + "two", "phone", self.body("two"))[0], 503
        )
        for _ in range(60):
            self.server.permit("reader")
        self.assertEqual(self.request("GET", OP + "receipts/one", "reader")[0], 429)
        self.now = LATER
        self.assertEqual(self.request("GET", OP + "receipts/one", "reader")[0], 401)

    def test_cli_accepts_explicit_private_port_and_refuses_wildcard(self):
        config = self.root / "config.json"
        config.touch(mode=0o600)
        config.write_text(
            json.dumps(
                dict(
                    self.config,
                    archive_id="pilot-fabricated-archive",
                    scope=self.scope,
                    pilot=vars(
                        replace(self.pilot, start=None, end=None, enabled=False)
                    ),
                    expected_guest_ipv4="192.168.78.2",
                )
            )
        )
        self.assertFalse(load_config(config)["pilot"].enabled)
        common = ["server", "--config", str(config), "--root", str(self.state)]
        self.addCleanup(os.umask, os.umask(0o077))
        with patch("sys.argv", [*common, "init"]):
            self.assertEqual(main(), 0)
        with (
            patch(
                "sys.argv",
                [
                    *common,
                    "serve",
                    "--bind",
                    "192.168.78.2",
                    "--port",
                    "8446",
                    "--cert",
                    "cert",
                    "--key",
                    "key",
                ],
            ),
            patch("integrations.mse_archive_service.selected_server.tls_context"),
            patch(
                "integrations.mse_archive_service.selected_server.SelectedServer"
            ) as server,
        ):
            self.assertEqual(main(), 0)
            self.assertEqual(server.call_args.args[0], ("192.168.78.2", 8446))
        with (
            patch(
                "sys.argv", [*common, "serve", "--bind", "0.0.0.0", "--port", "8446"]
            ),
            patch("sys.stderr"),
        ):
            self.assertEqual(main(), 1)
