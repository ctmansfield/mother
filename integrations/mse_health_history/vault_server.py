"""Private HTTPS bulk ciphertext receiver for one pinned history enrollment."""

import argparse
from hashlib import sha256
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, HTTPServer
from ipaddress import IPv4Address, IPv4Network
import json
import os
from pathlib import Path
import re
import ssl
import sys
from time import monotonic

from mother.physiology.contracts import canonical_json

from .files import private_path
from .vault import (
    CHUNK,
    DIGEST,
    CiphertextVault,
    Enrollment,
    VaultCapacity,
    VaultClosed,
    VaultConflict,
    utc,
)

ROLES = ("upload", "receipt", "ciphertext")
BEARER = re.compile(r"Bearer ([A-Za-z0-9_-]{43})")
RANGE = re.compile(
    r"bytes (0|[1-9][0-9]{0,10})-(0|[1-9][0-9]{0,10})/([1-9][0-9]{0,10})"
)
OFFSET = re.compile(r"offset=(0|[1-9][0-9]{0,10})")
PRIVATE = tuple(map(IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate history config key")
        result[key] = value
    return result


def read_config(path):
    path = Path(path).absolute()
    private_path(path, directory=False)
    with path.open("rb") as stream:
        raw = stream.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("history config byte bound exceeded")
    value = json.loads(raw, object_pairs_hook=_unique)
    if not isinstance(value, dict) or set(value) != {"bind", "enrollment", "grants"}:
        raise ValueError("invalid history vault config")
    if not isinstance(value["bind"], str) or not any(
        IPv4Address(value["bind"]) in network for network in PRIVATE
    ):
        raise ValueError("history vault requires assigned private IPv4")
    value["enrollment"] = Enrollment(**value["enrollment"])
    grants = value["grants"]
    if not isinstance(grants, dict) or set(grants) != set(ROLES):
        raise ValueError("history vault requires separate grants")
    for item in grants.values():
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "expires_at"}
            or not isinstance(item["sha256"], str)
            or not DIGEST.fullmatch(item["sha256"])
        ):
            raise ValueError("invalid history vault grant")
        item["expires_at"] = utc(item["expires_at"])
    if len({item["sha256"] for item in grants.values()}) != len(ROLES):
        raise ValueError("history vault grants must be independent")
    if grants["upload"]["expires_at"] > utc(value["enrollment"].cutoff):
        raise ValueError("history upload grant must expire at or before cutoff")
    return value


class Server(HTTPServer):
    def __init__(self, address, vault, grants, context):
        self.vault, self.grants, self.context = vault, grants, context
        super().__init__(address, Handler)

    def get_request(self):
        sock, address = super().get_request()
        try:
            sock.settimeout(5)
            return self.context.wrap_socket(sock, server_side=True), address
        except OSError:
            sock.close()
            raise

    def handle_error(self, request, client_address):
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_error(self, code, *_args, **_kwargs):
        self.reply(code, {"error": "invalid_request"})

    def reply(self, code, content):
        binary = isinstance(content, bytes)
        data = content if binary else canonical_json(content).encode()
        self.send_response(code)
        self.send_header(
            "Content-Type", "application/octet-stream" if binary else "application/json"
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if binary:
            self.send_header("X-Chunk-SHA256", sha256(data).hexdigest())
        self.end_headers()
        self.wfile.write(data)

    @property
    def route(self):
        return "/v1/history/imports/" + self.server.vault.enrollment.import_id

    def grant(self, role):
        fields = self.headers.get_all("Authorization", [])
        token = BEARER.fullmatch(fields[0]) if len(fields) == 1 else None
        pin = self.server.grants[role]
        if (
            token
            and self.server.vault.clock() < pin["expires_at"]
            and compare_digest(sha256(token[1].encode()).hexdigest(), pin["sha256"])
        ):
            return True
        self.reply(401, {"error": "unauthorized"})
        return False

    def action(self, apply):
        try:
            result = apply()
        except VaultClosed:
            self.reply(403, {"error": "intake_closed"})
        except VaultConflict:
            self.reply(409, {"error": "chunk_conflict"})
        except (VaultCapacity, OSError):
            self.reply(503, {"error": "unavailable"})
        except KeyError:
            self.reply(404, {"error": "not_found"})
        except ValueError:
            self.reply(400, {"error": "invalid_request"})
        else:
            partial = isinstance(result, dict) and result.get("complete") is False
            self.reply(202 if partial else 200, result)

    def do_GET(self):
        if self.path == self.route:
            if self.grant("receipt"):
                self.action(self.server.vault.receipt)
        elif self.path == self.route + "/progress":
            if self.grant("upload"):
                self.action(self.server.vault.progress)
        elif self.path.startswith(self.route + "/ciphertext?"):
            if self.grant("ciphertext"):
                offset = OFFSET.fullmatch(self.path.split("?", 1)[1])
                if offset:
                    self.action(lambda: self.server.vault.retrieve(int(offset[1])))
                else:
                    self.reply(400, {"error": "invalid_request"})
        else:
            self.reply(404, {"error": "not_found"})

    def do_PUT(self):
        if self.path != self.route:
            self.reply(404, {"error": "not_found"})
            return
        if not self.grant("upload"):
            return
        media = self.headers.get_all("Content-Type")
        if (
            media != ["application/octet-stream"]
            or self.headers.get_all("Content-Encoding")
            or self.headers.get_all("Transfer-Encoding")
        ):
            self.reply(415, {"error": "unsupported_media"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        ranges = self.headers.get_all("Content-Range", [])
        hashes = self.headers.get_all("X-Chunk-SHA256", [])
        span = RANGE.fullmatch(ranges[0]) if len(ranges) == 1 else None
        if (
            len(lengths) != 1
            or not re.fullmatch(r"[1-9][0-9]{0,7}", lengths[0])
            or span is None
            or len(hashes) != 1
            or not DIGEST.fullmatch(hashes[0])
        ):
            self.reply(400, {"error": "invalid_request"})
            return
        length = int(lengths[0])
        start, last, total = map(int, span.groups())
        if length > CHUNK:
            self.reply(413, {"error": "chunk_limit"})
            return
        if (
            last - start + 1 != length
            or last >= total
            or total != self.server.vault.enrollment.expected_length
        ):
            self.reply(400, {"error": "invalid_request"})
            return

        def ingest():
            self.server.vault.writable()
            deadline = monotonic() + 30
            body = bytearray()
            while len(body) < length:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ValueError("history chunk deadline elapsed")
                self.connection.settimeout(min(5, remaining))
                part = self.rfile.read1(min(length - len(body), 65_536))
                if not part:
                    raise ValueError("history chunk incomplete")
                body.extend(part)
            self.connection.settimeout(5)
            return self.server.vault.put(start, total, bytes(body), hashes[0])

        self.action(ingest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "serve"))
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        config = read_config(args.config)
        vault = CiphertextVault(args.root, config["enrollment"])
        if args.operation == "init":
            vault.initialize()
        else:
            if (
                args.bind != config["bind"]
                or args.port is None
                or not 1024 <= args.port <= 65535
            ):
                raise ValueError("history vault bind and port required")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(args.cert, args.key)
            vault.check_startup()
            with Server(
                (args.bind, args.port), vault, config["grants"], context
            ) as server:
                server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, TypeError, ValueError):
        print("history vault startup refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
