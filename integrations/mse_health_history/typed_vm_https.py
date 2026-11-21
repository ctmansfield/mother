"""Finite private mutual TLS transport for synthetic native BP qualification."""

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
from urllib.parse import unquote, urlencode

from .bp_server import Clock
from .blood_pressure import source_time
from .typed_vm import Conflict, MAX_BYTES, PIN, PURPOSE, encoded
from .vault_server import PRIVATE


class Closed(ValueError):
    pass


class TypedServer(HTTPServer):
    def __init__(
        self, address, store, context, grants, start, end, *, snapshot, clock=None
    ):
        host, port = address
        if (
            port in (8446, 8447, 8448)
            or not any(IPv4Address(host) in network for network in PRIVATE)
            or context.verify_mode != ssl.CERT_REQUIRED
            or context.minimum_version < ssl.TLSVersion.TLSv1_2
        ):
            raise ValueError("dedicated private mutual TLS listener required")
        if (
            set(grants) != {"writer", "reader"}
            or not all(PIN.fullmatch(pin) for pin, _ in grants.values())
            or len({pin for pin, _ in grants.values()}) != 2
            or not source_time(start) == start < end == source_time(end)
            or any(
                source_time(until) != until or until <= start
                for _, until in grants.values()
            )
            or grants["writer"][1] > end
        ):
            raise ValueError("invalid independent scoped grants or lease")
        sample_start, sample_end = snapshot
        if (
            not source_time(sample_start)
            == sample_start
            < sample_end
            == source_time(sample_end)
        ):
            raise ValueError("invalid qualified snapshot interval")
        self.snapshot = snapshot
        self.context = context
        self.store = store
        self.grants = dict(grants)
        self.start, self.end = start, end
        self.clock = clock if clock is not None else Clock()
        self.route = f"/v1/native-typed/{store.scope[0]}/{PURPOSE}"
        super().__init__(address, TypedHandler)

    def get_request(self):
        sock, peer = super().get_request()
        sock.settimeout(5)
        try:
            return self.context.wrap_socket(sock, server_side=True), peer
        except OSError:
            sock.close()
            raise

    def writable(self):
        if not self.start <= self.clock() < self.grants["writer"][1]:
            raise Closed("write lease closed")


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

    def run_operation(self, role, operation):
        pin, until = self.server.grants[role]
        peer = self.connection.getpeercert(binary_form=True)
        if not peer or not compare_digest(sha256(peer).hexdigest(), pin):
            self.reply(403, encoded({"error": "denied"}))
            return
        try:
            now = self.server.clock()
            if not self.server.start <= now < until:
                raise Closed("role lease closed")
            result = operation()
        except Closed:
            result = 403, encoded({"error": "closed"})
        except Conflict:
            result = 409, encoded({"error": "conflict"})
        except KeyError:
            result = 404, encoded({"error": "absent"})
        except (TypeError, ValueError, OverflowError):
            result = 400, encoded({"error": "invalid"})
        except (OSError, sqlite3.Error):
            result = 503, encoded({"error": "indeterminate"})
        self.reply(*result)

    def do_PUT(self):
        if self.path != self.server.route + "/projection":
            self.reply(404, encoded({"error": "absent"}))
            return

        def ingest():
            self.server.writable()
            sizes = self.headers.get_all("Content-Length", [])
            if (
                self.headers.get("Transfer-Encoding") is not None
                or self.headers.get("Content-Encoding") is not None
                or self.headers.get_all("Content-Type", []) != ["application/json"]
                or len(sizes) != 1
                or not re.fullmatch(r"[1-9][0-9]{0,6}", sizes[0])
                or int(sizes[0]) > MAX_BYTES
            ):
                raise ValueError("invalid projection framing")
            size = int(sizes[0])
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("incomplete projection")
            return self.server.store.ingest(raw, self.server.writable)

        self.run_operation("writer", ingest)

    def do_GET(self):
        if self.path == self.server.route + "/receipt":
            self.run_operation("reader", lambda: (200, self.server.store.receipt()))
            return
        match = re.fullmatch(
            re.escape(self.server.route)
            + r"/bp\?start=([\w%.-]{1,80})&end=([\w%.-]{1,80})",
            self.path,
            re.ASCII,
        )
        if not match:
            self.reply(404, encoded({"error": "absent"}))
            return

        def read():
            start, end = map(unquote, match.groups())
            if not self.server.snapshot[0] <= start < end <= self.server.snapshot[1]:
                raise ValueError("snapshot outside grant")
            return 200, self.server.store.read(start, end)

        self.run_operation("reader", read)


class TypedClient:
    def __init__(self, host, port, enrollment, context):
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("guest hostname and CA verification required")
        self.host, self.port, self.context = host, port, context
        self.route = f"/v1/native-typed/{enrollment}/{PURPOSE}"

    def request(self, method, suffix, raw=None):
        connection = HTTPSConnection(
            self.host, self.port, context=self.context, timeout=8
        )
        try:
            headers = {"Content-Type": "application/json"} if raw is not None else {}
            connection.request(method, self.route + suffix, raw, headers)
            response = connection.getresponse()
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("guest response exceeds bound")
            return response.status, json.loads(body)
        finally:
            connection.close()

    def put(self, raw):
        status, result = self.request("PUT", "/projection", raw)
        if status in (200, 201):
            self.verify_receipt(raw, result)
        return status, result

    @staticmethod
    def verify_receipt(raw, result):
        manifest = json.loads(raw)
        expected = {
            **{
                k: manifest[k]
                for k in (
                    "schema",
                    "purpose",
                    "enrollment",
                    "source_instance",
                    "artifact_receipt",
                )
            },
            "projection_sha256": sha256(raw).hexdigest(),
            "bytes": len(raw),
            "bp_pairs": len(manifest["rows"]),
        }
        if result != dict(expected, receipt_id=sha256(encoded(expected)).hexdigest()):
            raise ValueError("guest receipt does not match this projection")

    def receipt(self):
        return self.request("GET", "/receipt")

    def read(self, start, end):
        return self.request("GET", "/bp?" + urlencode({"start": start, "end": end}))


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
    config = json.loads(private_bytes(args.config, 16_384))
    if set(config) != {
        "bind",
        "port",
        "db",
        "enrollment",
        "source_instance",
        "artifact_receipt",
        "certificate",
        "key",
        "client_ca",
        "grants",
        "start",
        "end",
        "snapshot",
    }:
        parser.error("guest configuration fields mismatch")
    store = TypedStore(
        config["db"],
        config["enrollment"],
        config["source_instance"],
        config["artifact_receipt"],
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
        snapshot=config["snapshot"],
    ) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
