"""Finite private mutual TLS transport for synthetic ATLAS r2 qualification."""

from base64 import b64encode
from contextlib import closing
from hashlib import sha256
from hmac import compare_digest
from http.client import HTTPSConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from ipaddress import IPv4Address
import json
import re
import sqlite3
import ssl

from .bp_server import Clock
from .typed_vm import (
    Capacity,
    Conflict,
    MAX_BYTES,
    MAX_ROWS,
    PIN,
    PROJECTION_REVISION,
    PURPOSES,
    ScopeDenied,
    batch_receipt,
    encoded,
    is_ref,
    require,
    valid_clock,
)
from .vault_server import PRIVATE

DESCRIPTOR = {
    "snapshot_id",
    "terminal_receipt",
    "purpose",
    "subject",
    "start",
    "end",
    "projection_revision",
    "max_rows",
    "max_bytes",
}


class Closed(ValueError):
    pass


def content_digest(raw):
    return "sha-256=:" + b64encode(sha256(raw).digest()).decode("ascii") + ":"


def routes(scope):
    root = f"/v1/native-bp/stores/{scope['store_id']}"
    return root, (
        f"{root}/enrollments/{scope['enrollment_id']}/imports/{scope['import_ref']}/batches/"
    )


class TypedServer(HTTPServer):
    def __init__(
        self, address, store, context, grants, start, end, *, snapshots, clock=None
    ):
        host, port = address
        require(
            port not in (8446, 8447, 8448)
            and any(IPv4Address(host) in network for network in PRIVATE)
            and context.verify_mode == ssl.CERT_REQUIRED
            and context.minimum_version >= ssl.TLSVersion.TLSv1_2,
            "dedicated private mutual TLS listener required",
        )
        descriptors = {}
        subjects = {}
        for desc in snapshots:
            require(
                set(desc) == DESCRIPTOR
                and desc["purpose"] in PURPOSES
                and is_ref(desc["snapshot_id"])
                and desc["projection_revision"] == PROJECTION_REVISION
                and is_ref(desc["subject"])
                and PIN.fullmatch(desc["terminal_receipt"])
                and type(desc["max_rows"]) is int
                and 1 <= desc["max_rows"] <= MAX_ROWS
                and type(desc["max_bytes"]) is int
                and 1 <= desc["max_bytes"] <= MAX_BYTES
                and valid_clock(desc["start"])
                and valid_clock(desc["end"])
                and store.bounds[0] <= desc["start"] < desc["end"] <= store.bounds[1],
                "invalid purpose snapshot descriptor",
            )
            key = (desc["purpose"], desc["snapshot_id"])
            require(key not in descriptors, "duplicate snapshot identity")
            if subjects.setdefault(desc["subject"], desc["purpose"]) != desc["purpose"]:
                raise ValueError("snapshot subject reused across purposes")
            descriptors[key] = dict(desc)
        require(
            set(grants)
            == {"writer", "receipt", *(purpose for purpose, _ in descriptors)}
            and all(
                PIN.fullmatch(pin) and valid_clock(until) and start < until
                for pin, until in grants.values()
            )
            and len({pin for pin, _ in grants.values()}) == len(grants)
            and valid_clock(start)
            and valid_clock(end)
            and start < end
            and grants["writer"][1] <= end,
            "invalid independent scoped grants or lease",
        )
        self.context, self.store = context, store
        self.grants, self.snapshots = dict(grants), descriptors
        self.start = start
        self.clock = clock if clock is not None else Clock()
        root, batch = routes(store.scope)
        self.batch_route = re.compile(re.escape(batch) + r"([1-9][0-9]{0,8})")
        self.snapshot_route = re.compile(
            re.escape(root)
            + r"/purposes/([A-Za-z0-9_-]{1,96})/snapshots/([A-Za-z0-9_-]{1,96})"
        )
        super().__init__(address, TypedHandler)

    def get_request(self):
        sock, peer = super().get_request()
        sock.settimeout(5)
        try:
            return self.context.wrap_socket(sock, server_side=True), peer
        except OSError:
            sock.close()
            raise

    def check_lease(self, role):
        if not self.start <= self.clock() < self.grants[role][1]:
            raise Closed("role lease closed")


class TypedHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, value):
        self.reply(status, encoded({"error": value}))

    def run_operation(self, role, operation):
        peer = self.connection.getpeercert(binary_form=True)
        pin = sha256(peer).hexdigest() if peer else ""
        current = self.server.grants.get(role)
        if current is None or not compare_digest(current[0], pin):
            known = any(
                compare_digest(other, pin) for other, _ in self.server.grants.values()
            )
            self.error(403 if known else 401, "denied")
            return
        try:
            self.server.check_lease(role)
            result = operation()
        except (Closed, ScopeDenied):
            result = 403, encoded({"error": "denied"})
        except Conflict:
            result = 409, encoded({"error": "conflict"})
        except Capacity:
            result = 413, encoded({"error": "capacity"})
        except KeyError:
            result = 404, encoded({"error": "absent"})
        except (TypeError, ValueError, OverflowError):
            result = 400, encoded({"error": "invalid"})
        except (OSError, sqlite3.Error):
            result = 503, encoded({"error": "indeterminate"})
        self.reply(*result)

    def do_PUT(self):
        match = self.server.batch_route.fullmatch(self.path)
        if not match:
            self.error(404, "absent")
            return

        def ingest():
            sizes = self.headers.get_all("Content-Length", [])
            pins = self.headers.get_all("Content-Digest", [])
            require(
                self.headers.get("Transfer-Encoding") is None
                and self.headers.get("Content-Encoding") is None
                and self.headers.get_all("Content-Type", []) == ["application/json"]
                and len(sizes) == 1
                and re.fullmatch(r"[1-9][0-9]{0,8}", sizes[0])
                and len(pins) == 1
                and re.fullmatch(r"sha-256=:[A-Za-z0-9+/]{43}=:", pins[0]),
                "invalid native batch framing",
            )
            size = int(sizes[0])
            if size > MAX_BYTES:
                raise Capacity("native batch byte cap")
            raw = self.rfile.read(size)
            require(
                len(raw) == size and compare_digest(content_digest(raw), pins[0]),
                "native batch digest mismatch",
            )
            return self.server.store.ingest(
                int(match[1]),
                raw,
                lambda: self.server.check_lease("writer"),
            )

        self.run_operation("writer", ingest)

    def do_GET(self):
        batch = self.server.batch_route.fullmatch(self.path)
        if batch:
            self.run_operation(
                "receipt", lambda: (200, self.server.store.receipt(int(batch[1])))
            )
            return
        snapshot = self.server.snapshot_route.fullmatch(self.path)
        if snapshot:
            self.run_operation(
                snapshot[1],
                lambda: (
                    200,
                    self.server.store.snapshot(
                        self.server.snapshots[snapshot.groups()]
                    ),
                ),
            )
            return
        self.error(404, "absent")


class TypedClient:
    def __init__(self, host, port, scope, context):
        require(
            context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED,
            "guest hostname and CA verification required",
        )
        self.host, self.port, self.context = host, port, context
        self.root, self.batch_path = routes(scope)

    def request(self, method, path, raw=None, *, headers=None):
        connection = HTTPSConnection(
            self.host, self.port, context=self.context, timeout=8
        )
        try:
            connection.request(method, path, raw, headers or {})
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            require(len(body) <= MAX_BYTES, "guest response cap")
            return response.status, json.loads(body)
        finally:
            connection.close()

    def put(self, seq, raw):
        status, result = self.request(
            "PUT",
            self.batch_path + str(seq),
            raw,
            headers={
                "Content-Type": "application/json",
                "Content-Digest": content_digest(raw),
            },
        )
        if status in (200, 201):
            self.verify_receipt(raw, result)
        return status, result

    @staticmethod
    def verify_receipt(raw, result):
        batch = json.loads(raw)
        upserts = sum(op["op"] == "upsert" for op in batch["ops"])
        expected = batch_receipt(batch, raw, upserts, len(batch["ops"]) - upserts)
        require(
            encoded(result) == expected, "guest receipt does not match submitted batch"
        )

    def receipt(self, seq):
        return self.request("GET", self.batch_path + str(seq))

    def snapshot(self, purpose, snapshot_id):
        require(purpose in PURPOSES and is_ref(snapshot_id), "invalid snapshot path")
        return self.request(
            "GET", f"{self.root}/purposes/{purpose}/snapshots/{snapshot_id}"
        )


def main():
    """Start only when explicitly invoked with a private synthetic guest config."""
    import argparse
    import os

    from .native_runner import private_bytes
    from .typed_vm import TypedStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "serve"))
    parser.add_argument("config")
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(private_bytes(args.config, 64 * 1024))
    if set(config) != {
        "bind",
        "port",
        "db",
        "scope",
        "bounds",
        "artifact",
        "inventory",
        "max_batches",
        "max_bytes",
        "admitted_deletions",
        "certificate",
        "key",
        "client_ca",
        "grants",
        "start",
        "end",
        "snapshots",
    }:
        parser.error("guest configuration fields mismatch")
    store = TypedStore(
        config["db"],
        config["scope"],
        config["bounds"],
        config["artifact"],
        config["inventory"],
        max_batches=config["max_batches"],
        max_bytes=config["max_bytes"],
        admitted_deletions=config["admitted_deletions"],
    )
    if args.mode == "init":
        store.initialize()
        return
    with closing(store.connect()):
        pass
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config["certificate"], config["key"])
    context.load_verify_locations(cafile=config["client_ca"])
    context.verify_mode = ssl.CERT_REQUIRED
    with TypedServer(
        (config["bind"], config["port"]),
        store,
        context,
        config["grants"],
        config["start"],
        config["end"],
        snapshots=config["snapshots"],
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
