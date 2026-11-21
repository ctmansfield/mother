"""Private HTTPS typed BP history service for one finite enrollment."""

import argparse
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
from time import monotonic

from .blood_pressure import source_time
from .bp_transport import BPStore, FEEDS, MAX_BYTES, MAX_PAGES, Sealer, _key
from .files import private_path
from .vault import DIGEST, VaultCapacity, VaultClosed, VaultConflict
from .vault_server import Handler, PRIVATE, Server, _unique

ROLES = {"upload", "receipt", "export"}
LABEL = r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}"
PAGE = re.compile(
    rf"/v1/bp-history/enrollments/({LABEL})/streams/({LABEL})/pages/([1-9][0-9]{{0,8}})"
)
EXPORT = re.compile(
    rf"/v1/bp-history/enrollments/({LABEL})/streams/({LABEL})/export\?from=([1-9][0-9]{{0,8}})&through=([1-9][0-9]{{0,8}})"
)


def _normalize_clock(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?Z", value
    ):
        raise ValueError("BP config requires UTC")
    return source_time(value)


class Clock:
    def __init__(self):
        self.observed = datetime.now(timezone.utc)
        self.tick = monotonic()

    def instant(self):
        at = datetime.now(timezone.utc)
        tick = monotonic()
        elapsed = self.observed + timedelta(seconds=tick - self.tick)
        if at > elapsed:
            self.observed, self.tick = at, tick
        return max(at, elapsed)

    def __call__(self):
        return self.instant().isoformat(timespec="microseconds").replace("+00:00", "Z")


def read_config(path):
    path = Path(path).absolute()
    private_path(path, directory=False)
    with path.open("rb") as stream:
        raw = stream.read(16_385)
    if len(raw) > 16_384:
        raise ValueError("BP config exceeds bound")
    config = json.loads(raw, object_pairs_hook=_unique)
    fields = (
        "bind archive_id enrollment_id source_instance streams snapshot "
        "transport_starts_at transport_ends_at enabled max_pages max_bytes reserve_bytes grants "
        "age_executable age_sha256 recipient_file recipient_sha256 provenance_key_file"
    )
    if not isinstance(config, dict) or set(config) != set(fields.split()):
        raise ValueError("BP config fields mismatch")
    if not isinstance(config["bind"], str) or not any(
        IPv4Address(config["bind"]) in n for n in PRIVATE
    ):
        raise ValueError("BP bind requires exact private guest address")
    if not all(
        _key(config[key]) for key in ("archive_id", "enrollment_id", "source_instance")
    ):
        raise ValueError("invalid BP enrollment identity")
    streams = config["streams"]
    if (
        not isinstance(streams, dict)
        or set(streams) != set(FEEDS)
        or not all(map(_key, streams.values()))
        or len(set(streams.values())) != 3
    ):
        raise ValueError("BP enrollment requires three distinct streams")
    snapshot = config["snapshot"]
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "sample_start_at",
        "sample_end_before",
    }:
        raise ValueError("invalid BP snapshot")
    snapshot["sample_end_before"] = _normalize_clock(snapshot["sample_end_before"])
    if snapshot["sample_start_at"] is not None:
        snapshot["sample_start_at"] = _normalize_clock(snapshot["sample_start_at"])
        if snapshot["sample_start_at"] >= snapshot["sample_end_before"]:
            raise ValueError("invalid BP sample interval")
    for field in ("transport_starts_at", "transport_ends_at"):
        config[field] = _normalize_clock(config[field])
    if (
        config["transport_starts_at"] >= config["transport_ends_at"]
        or type(config["enabled"]) is not bool
    ):
        raise ValueError("invalid BP transport interval")
    for field, lo, hi in (
        ("max_pages", 1, MAX_PAGES),
        ("max_bytes", MAX_BYTES, 8 * 1024**3),
        ("reserve_bytes", 32 * 1024**2, 1024**4),
    ):
        if type(config[field]) is not int or not lo <= config[field] <= hi:
            raise ValueError("invalid BP quota")
    grants = config["grants"]
    if not isinstance(grants, dict) or set(grants) != ROLES:
        raise ValueError("BP requires independent roles")
    for item in grants.values():
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "expires_at"}
            or not isinstance(item["sha256"], str)
            or not DIGEST.fullmatch(item["sha256"])
        ):
            raise ValueError("invalid BP grant")
        item["expires_at"] = _normalize_clock(item["expires_at"])
    if (
        len({item["sha256"] for item in grants.values()}) != len(ROLES)
        or grants["upload"]["expires_at"] > config["transport_ends_at"]
    ):
        raise ValueError("invalid BP grant independence or lease")
    return config


class BPServer(Server):
    def __init__(self, address, store, context):
        self.store = store
        self.context = context
        self.grants = store.config["grants"]
        HTTPServer.__init__(self, address, BPHandler)


class BPHandler(Handler):
    def grant(self, role):
        from hashlib import sha256
        from hmac import compare_digest
        from .vault_server import BEARER

        headers = self.headers.get_all("Authorization", [])
        match = BEARER.fullmatch(headers[0]) if len(headers) == 1 else None
        grant = self.server.grants[role]
        if (
            match
            and self.server.store.clock() < grant["expires_at"]
            and compare_digest(sha256(match[1].encode()).hexdigest(), grant["sha256"])
        ):
            return True
        self.reply(401, {"error": "unauthorized"})
        return False

    def _scope(self, target):
        config = self.server.store.config
        if (
            target[1] != config["enrollment_id"]
            or target[2] not in config["streams"].values()
        ):
            self.reply(403, {"error": "scope_denied"})
            return False
        return True

    def _apply(self, apply):
        try:
            code, body = apply()
        except VaultClosed:
            code, body = 403, {"error": "transport_closed"}
        except VaultConflict:
            code, body = 409, {"error": "checkpoint_conflict"}
        except VaultCapacity:
            code, body = 413, {"error": "limit"}
        except KeyError:
            code, body = 404, {"error": "not_found"}
        except (sqlite3.Error, OSError):
            code, body = 503, {"error": "indeterminate"}
        except (ValueError, OverflowError):
            code, body = 400, {"error": "invalid_page"}
        self.reply(code, body)

    def do_PUT(self):
        match = PAGE.fullmatch(self.path)
        if not match:
            self.reply(404, {"error": "not_found"})
            return
        if not self.grant("upload") or not self._scope(match):
            return
        if (
            self.headers.get_all("Content-Type") != ["application/json"]
            or self.headers.get_all("Content-Encoding")
            or self.headers.get_all("Transfer-Encoding")
        ):
            self.reply(400, {"error": "invalid_media"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[1-9][0-9]{0,8}", lengths[0]):
            self.reply(400, {"error": "invalid_length"})
            return
        size = int(lengths[0])
        if size > MAX_BYTES:
            self.reply(413, {"error": "limit"})
            return

        def put():
            self.server.store.writable()
            data = bytearray()
            deadline = monotonic() + 10
            while len(data) < size:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ValueError("BP body deadline")
                self.connection.settimeout(min(5, remaining))
                chunk = self.rfile.read1(min(size - len(data), 65_536))
                if not chunk:
                    raise ValueError("BP truncated body")
                data.extend(chunk)
            self.connection.settimeout(5)
            return self.server.store.put(match[2], int(match[3]), bytes(data))

        self._apply(put)

    def do_GET(self):
        match = PAGE.fullmatch(self.path)
        export = EXPORT.fullmatch(self.path)
        if match:
            if self.grant("receipt") and self._scope(match):
                self._apply(
                    lambda: (200, self.server.store.receipt(match[2], int(match[3])))
                )
        elif export:
            if self.grant("export") and self._scope(export):
                self._apply(
                    lambda: (
                        200,
                        self.server.store.export(
                            export[2], int(export[3]), int(export[4])
                        ),
                    )
                )
        else:
            self.reply(404, {"error": "not_found"})


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
        key = Path(config["provenance_key_file"]).absolute()
        private_path(key, directory=False)
        if key.stat().st_size != 32:
            raise ValueError("BP provenance key must have 32 bytes")
        sealer = Sealer(
            config["age_executable"],
            config["age_sha256"],
            config["recipient_file"],
            config["recipient_sha256"],
        )
        store = BPStore(args.root, config, sealer, key.read_bytes(), clock=Clock())
        if args.operation == "init":
            store.initialize()
        else:
            if args.bind != config["bind"] or args.port != 8448:
                raise ValueError("BP service requires assigned bind and its port")
            with store.connect() as db:
                if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise ValueError("BP history integrity failed")
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(args.cert, args.key)
            with BPServer((args.bind, args.port), store, context) as server:
                server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, TypeError, sqlite3.Error):
        print("BP history startup refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
