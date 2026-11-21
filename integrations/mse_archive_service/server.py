"""A finite, TLS-only synthetic submission and operator interface."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
import ssl
import sys
from urllib.parse import parse_qs, urlsplit

from integrations.mse_ingest import BatchConflict, RecoveryError, Scope
from mother.physiology.contracts import canonical_json

from .store import CapacityExceeded, PrivateArchive, UnknownBatch

ROLES = ("phone", "reader", "exporter", "evidence")
HEX = re.compile(r"[0-9a-f]{64}")
BEARER = re.compile(r"Bearer ([A-Za-z0-9_-]{43})")
BATCH = re.compile(r"/v1/archive/batches/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})")
ORIGINAL = re.compile(r"/v1/archive/operator/originals/([0-9a-f]{64})")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
LIMIT = 128 * 1024
RESPONSE_LIMIT = 2 * 1024 * 1024
OPERATOR = {
    "/v1/archive/operator/receipts": ("reader", "archive_receipts_v1"),
    "/v1/archive/operator/revisions": ("reader", "archive_revisions_v1"),
    "/v1/archive/operator/export": ("exporter", "archive_receipt_revisions_v1"),
    "/v1/archive/operator/relations": ("reader", "archive_receipt_revisions_v1"),
}


def load_configuration(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError("configuration must be private")
    value = json.loads(path.read_bytes())
    required = {
        "archive_id",
        "scope",
        "token_sha256",
        "allowed_artifact_sha256",
        "expires_at",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("invalid configuration")
    if not isinstance(value["archive_id"], str) or not TOKEN.fullmatch(
        value["archive_id"]
    ):
        raise ValueError("invalid archive identity")
    scope = value["scope"]
    if (
        not isinstance(scope, dict)
        or set(scope)
        != {"subject_id", "source_system", "source_instance", "collection"}
        or any(
            not isinstance(item, str) or not TOKEN.fullmatch(item)
            for item in scope.values()
        )
        or not scope["subject_id"].startswith("synthetic-")
        or (scope["source_system"], scope["collection"])
        != ("healthkit", "healtharchive")
    ):
        raise ValueError("invalid synthetic scope")
    tokens = value["token_sha256"]
    if (
        not isinstance(tokens, dict)
        or set(tokens) != set(ROLES)
        or any(
            not isinstance(item, str) or not HEX.fullmatch(item)
            for item in tokens.values()
        )
        or len(set(tokens.values())) != len(ROLES)
    ):
        raise ValueError("invalid distinct role digests")
    artifacts = value["allowed_artifact_sha256"]
    if (
        not isinstance(artifacts, list)
        or not 1 <= len(artifacts) <= 32
        or any(
            not isinstance(item, str) or not HEX.fullmatch(item) for item in artifacts
        )
        or len(set(artifacts)) != len(artifacts)
    ):
        raise ValueError("invalid synthetic artifact allowlist")
    expiry = value["expires_at"]
    if not isinstance(expiry, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", expiry
    ):
        raise ValueError("invalid stage expiry")
    value["expires_at"] = datetime.strptime(expiry, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )
    if value["expires_at"] <= datetime.now(timezone.utc):
        raise ValueError("stage expired")
    return value


def tls_context(cert, key):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=cert, keyfile=key)
    return context


class ArchiveServer(HTTPServer):
    def __init__(self, address, *, archive, config, context):
        self.archive = archive
        self.config = config
        self.context = context
        super().__init__(address, Handler)

    def get_request(self):
        connection, address = super().get_request()
        try:
            connection.settimeout(5)
            return self.context.wrap_socket(connection, server_side=True), address
        except OSError:
            connection.close()
            raise

    def handle_error(self, request, client_address):
        # HTTP requests, protected paths, connection details and payloads
        # are deliberately excluded from standard request logs.
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, {"error": "invalid_request"})

    def reply(self, status, payload, media_type="application/json"):
        body = (
            payload
            if isinstance(payload, bytes)
            else canonical_json(payload).encode("utf-8")
        )
        if len(body) > RESPONSE_LIMIT:
            status, body = 413, b'{"error":"view_too_large"}'
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def grant(self, required):
        if datetime.now(timezone.utc) >= self.server.config["expires_at"]:
            self.reply(401, {"error": "unauthorized"})
            return False
        values = self.headers.get_all("Authorization", [])
        token = BEARER.fullmatch(values[0]) if len(values) == 1 else None
        if token and token[1].isascii():
            digest = sha256(token[1].encode("ascii")).hexdigest()
            role = next(
                (
                    name
                    for name in ROLES
                    if hmac.compare_digest(
                        self.server.config["token_sha256"][name], digest
                    )
                ),
                None,
            )
            if role == required:
                return True
            if role is not None:
                self.reply(404, {"error": "not_found"})
                return False
        self.reply(401, {"error": "unauthorized"})
        return False

    def execute(self, action):
        try:
            status, result = action()
        except UnknownBatch:
            status, result = 404, {"error": "not_found"}
        except BatchConflict:
            status, result = 409, {"error": "batch_conflict"}
        except CapacityExceeded:
            status, result = 413, {"error": "capacity_limit"}
        except (sqlite3.Error, RecoveryError, OSError):
            status, result = 503, {"error": "unavailable"}
        except (ValueError, KeyError):
            status, result = 400, {"error": "invalid_request"}
        self.reply(
            status,
            result,
            (
                "application/octet-stream"
                if isinstance(result, bytes)
                else "application/json"
            ),
        )

    @staticmethod
    def result(receipt):
        return (202 if receipt["status"] == "durably_received" else 200), receipt

    def do_PUT(self):
        if not self.grant("phone"):
            return
        match = BATCH.fullmatch(self.path)
        if match is None:
            self.reply(404, {"error": "not_found"})
            return
        if (
            self.headers.get_all("Content-Type") != ["application/json"]
            or self.headers.get_all("Content-Encoding")
            or self.headers.get_all("Transfer-Encoding")
        ):
            self.reply(415, {"error": "unsupported_media"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,8}", lengths[0]):
            self.reply(400, {"error": "invalid_request"})
            return
        length = int(lengths[0])
        if length > LIMIT:
            self.reply(413, {"error": "body_limit"})
            return
        try:
            original = self.rfile.read(length)
        except OSError:
            self.reply(400, {"error": "invalid_request"})
            return
        if len(original) != length:
            self.reply(400, {"error": "invalid_request"})
            return
        if (
            sha256(original).hexdigest()
            not in self.server.config["allowed_artifact_sha256"]
        ):
            self.reply(400, {"error": "synthetic_artifact_required"})
            return
        self.execute(
            lambda: self.result(self.server.archive.submit(match[1], original))
        )

    def do_GET(self):
        target = urlsplit(self.path)
        if target.scheme or target.netloc or target.fragment:
            self.reply(400, {"error": "invalid_request"})
            return
        batch = BATCH.fullmatch(target.path)
        original = ORIGINAL.fullmatch(target.path)
        if batch and not target.query:
            if self.grant("phone"):
                self.execute(lambda: self.result(self.server.archive.receipt(batch[1])))
        elif original and not target.query:
            if self.grant("evidence"):
                self.execute(lambda: (200, self.server.archive.original(original[1])))
        elif target.path in OPERATOR:
            role, view = OPERATOR[target.path]
            if self.grant(role):
                self.execute(lambda: (200, self.operator(target.query, view, role)))
        else:
            self.reply(404, {"error": "not_found"})

    def operator(self, query, view, role):
        values = parse_qs(query, strict_parsing=True, max_num_fields=8)
        optional = {
            "metric",
            "mode",
            "measurement_start",
            "measurement_end",
            "batch_id",
            "receipt_id",
        }
        if (
            not {"from", "through"} <= set(values)
            or set(values) - optional - {"from", "through"}
            or any(len(parts) != 1 or len(parts[0]) > 128 for parts in values.values())
            or any(
                not re.fullmatch(r"[1-9][0-9]{0,2}", values[name][0])
                for name in ("from", "through")
            )
        ):
            raise ValueError("invalid query")
        if (
            "batch_id" in values
            and not TOKEN.fullmatch(values["batch_id"][0])
            or "receipt_id" in values
            and not HEX.fullmatch(values["receipt_id"][0])
        ):
            raise ValueError("invalid receipt lookup")
        filters = {name: values[name][0] for name in optional if name in values}
        table = self.server.archive.read_view(
            view, int(values["from"][0]), int(values["through"][0]), **filters
        )
        if role != "exporter":
            return table
        return {
            "schema_version": "archive_export_v1",
            "purpose": "authorized_synthetic_transfer",
            "row_count": len(table["rows"]),
            "view_sha256": sha256(canonical_json(table).encode("utf-8")).hexdigest(),
            "view": table,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "serve"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bind")
    parser.add_argument("--port", type=int)
    parser.add_argument("--cert", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "serve" and not args.root.is_dir():
            raise ValueError("archive root must already exist")
        config = load_configuration(args.config)
        archive = PrivateArchive(
            args.root, archive_id=config["archive_id"], scope=Scope(**config["scope"])
        )
        if args.operation == "init":
            archive.initialize()
            print("synthetic archive initialized")
            return 0
        if not all((args.bind, args.port, args.cert, args.key)):
            raise ValueError("private bind and TLS configuration required")
        if ipaddress.ip_address(args.bind) not in ipaddress.ip_network("100.64.0.0/10"):
            raise ValueError("explicit tailnet IPv4 bind required")
        archive.check_startup()
        context = tls_context(args.cert, args.key)
        with ArchiveServer(
            (args.bind, args.port), archive=archive, config=config, context=context
        ) as server:
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError, sqlite3.Error, RecoveryError):
        print("private archive startup failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
