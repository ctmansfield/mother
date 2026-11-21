"""TLS-only selected HealthKit pilot endpoint and explicit lifecycle."""

import argparse
from collections import deque
from hashlib import sha256
import hmac
from http.server import HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from datetime import timedelta
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from integrations.healthbridge.capture import _unique_object
from integrations.mse_ingest import BatchConflict

from .selected import (
    BATCH_PATH,
    DIGEST,
    MAX_BYTES,
    Pilot,
    PilotClosed,
    SelectedArchive,
    _clock,
    parse_clock,
)
from .server import (
    ArchiveServer,
    BEARER,
    GUEST_NETWORKS,
    Handler,
    ROLES,
    tls_context,
    validate_bind,
)
from .store import CapacityExceeded

OPERATOR = re.compile(
    r"/v2/archive/operator/(receipts|originals)/([A-Za-z0-9][A-Za-z0-9._:-]{0,127})"
)
READ_ROUTES = {
    "/v2/archive/operator/rows": "reader",
    "/v2/archive/operator/export": "exporter",
}


def load_config(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > 16_384
    ):
        raise ValueError("selected configuration must be a private file")
    value = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    required = {"archive_id", "scope", "pilot", "grants", "expected_guest_ipv4"}
    if not isinstance(value, dict) or not required <= value.keys() <= (
        required | {"allowed_artifact_sha256"}
    ):
        raise ValueError("invalid selected configuration")
    address = (
        ipaddress.IPv4Address(value["expected_guest_ipv4"])
        if isinstance(value["expected_guest_ipv4"], str)
        else None
    )
    if address is None or not any(address in network for network in GUEST_NETWORKS):
        raise ValueError("selected listener requires an assigned private IPv4")
    if not isinstance(value["pilot"], dict):
        raise ValueError("invalid selected pilot")
    value["pilot"] = pilot = Pilot(**value["pilot"])
    grants = value["grants"]
    if not isinstance(grants, dict) or set(grants) != set(ROLES):
        raise ValueError("selected roles must be distinct")
    for item in grants.values():
        if (
            not isinstance(item, dict)
            or set(item) != {"sha256", "expires_at"}
            or not isinstance(item["sha256"], str)
            or not DIGEST.fullmatch(item["sha256"])
        ):
            raise ValueError("invalid selected grant")
        parse_clock(item["expires_at"])
    if len({item["sha256"] for item in grants.values()}) != len(ROLES):
        raise ValueError("selected hashes must be distinct")
    if pilot.enabled and grants["phone"]["expires_at"] < pilot.end:
        raise ValueError("selected phone grant does not cover the pilot")
    if "allowed_artifact_sha256" in value and not isinstance(
        value["allowed_artifact_sha256"], list
    ):
        raise ValueError("invalid selected synthetic allowlist")
    return value


class PilotClock:
    """Use monotonic elapsed time to keep a backward UTC shift fail-closed."""

    def __init__(self):
        self.start_monotonic = monotonic()
        self.start_utc = parse_clock(_clock())

    def __call__(self):
        wall = parse_clock(_clock())
        tick = monotonic()
        elapsed = self.start_utc + timedelta(seconds=tick - self.start_monotonic)
        if wall > elapsed:
            self.start_utc = wall
            self.start_monotonic = tick
        return (
            max(wall, elapsed).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )


class SelectedServer(ArchiveServer):
    def __init__(self, address, *, archive, config, context):
        self.archive = archive
        self.config = config
        self.context = context
        self.recent = {role: deque() for role in ROLES}
        self.cutoff_latched = False
        HTTPServer.__init__(self, address, SelectedHandler)

    def service_actions(self):
        if not self.cutoff_latched:
            try:
                self.cutoff_latched = self.archive.mark_cutoff()
            except (ValueError, OSError, sqlite3.Error):
                # A failed latch cannot authorize traffic. The wall/monotonic gate still applies.
                pass

    def permit(self, role):
        now = monotonic()
        recent = self.recent[role]
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 60:
            return False
        recent.append(now)
        return True


class SelectedHandler(Handler):
    def grant(self, required):
        values = self.headers.get_all("Authorization", [])
        token = BEARER.fullmatch(values[0]) if len(values) == 1 else None
        if token is None:
            self.reply(401, {"error": "unauthorized"})
            return False
        digest = sha256(token[1].encode("ascii")).hexdigest()
        item = self.server.config["grants"][required]
        if (
            not hmac.compare_digest(item["sha256"], digest)
            or self.server.archive.clock() >= item["expires_at"]
        ):
            self.reply(401, {"error": "unauthorized"})
            return False
        if not self.server.permit(required):
            self.send_response(429)
            self.send_header("Retry-After", "60")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False
        return True

    def action(self, operation, media_type="application/json"):
        try:
            result = operation()
        except PilotClosed:
            self.reply(403, {"error": "pilot_closed"})
        except BatchConflict:
            self.reply(409, {"error": "batch_conflict"})
        except CapacityExceeded:
            self.reply(503, {"error": "capacity_limit"})
        except KeyError:
            self.reply(404, {"error": "not_found"})
        except (sqlite3.Error, OSError):
            self.reply(503, {"error": "unavailable"})
        except (ValueError, OverflowError):
            self.reply(400, {"error": "invalid_request"})
        else:
            self.reply(200, result, media_type)

    def do_PUT(self):
        match = BATCH_PATH.fullmatch(self.path)
        if match is None:
            self.reply(404, {"error": "not_found"})
            return
        if not self.grant("phone"):
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
        if length > MAX_BYTES:
            self.reply(413, {"error": "body_limit"})
            return

        def submit():
            self.server.archive.check_write_window()
            deadline = monotonic() + 5
            original = bytearray()
            while len(original) < length:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise ValueError("selected body deadline elapsed")
                self.connection.settimeout(remaining)
                chunk = self.rfile.read1(min(length - len(original), 16_384))
                if not chunk:
                    raise ValueError("incomplete selected body")
                original.extend(chunk)
            self.connection.settimeout(5)
            return self.server.archive.put(match[1], bytes(original))

        self.action(submit)

    def do_GET(self):
        try:
            target = urlsplit(self.path)
        except ValueError:
            self.reply(400, {"error": "invalid_request"})
            return
        if target.scheme or target.netloc or target.fragment:
            self.reply(400, {"error": "invalid_request"})
            return
        batch = BATCH_PATH.fullmatch(target.path)
        operator = OPERATOR.fullmatch(target.path)
        role = READ_ROUTES.get(target.path)
        if batch and not target.query:
            if self.grant("phone"):

                def phone_receipt():
                    self.server.archive.check_write_window()
                    return self.server.archive.get(batch[1])

                self.action(phone_receipt)
        elif operator and not target.query:
            if operator[1] == "receipts":
                if self.grant("reader"):
                    self.action(lambda: self.server.archive.get(operator[2]))
            elif self.grant("evidence"):
                self.action(
                    lambda: self.server.archive.original(operator[2]),
                    "application/octet-stream",
                )
        elif role:
            if self.grant(role):
                self.action(lambda: self.read_view(target.query))
        else:
            self.reply(404, {"error": "not_found"})

    def read_view(self, query):
        fields = parse_qs(query, strict_parsing=True, max_num_fields=5)
        if not {"from", "through"} <= fields.keys() <= {
            "from",
            "through",
            "mode",
            "event_start",
            "event_end",
        } or any(len(item) != 1 for item in fields.values()):
            raise ValueError("invalid selected query")
        mode = fields.get("mode", ["history"])[0]
        if mode not in {"history", "current"}:
            raise ValueError("invalid selected query mode")
        event = None
        if "event_start" in fields or "event_end" in fields:
            event = (fields["event_start"][0], fields["event_end"][0])
        return self.server.archive.export(
            int(fields["from"][0]),
            int(fields["through"][0]),
            current=mode == "current",
            event_window=event,
        )


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
    os.umask(0o077)
    try:
        config = load_config(args.config)
        archive = SelectedArchive(
            args.root,
            archive_id=config["archive_id"],
            scope=config["scope"],
            allowed_artifact_sha256=config.get("allowed_artifact_sha256"),
            pilot=config["pilot"],
            clock=PilotClock(),
        )
        if args.operation == "init":
            archive.initialize()
            return 0
        validate_bind(args.bind, config)
        if (
            args.port is None
            or not 1024 <= args.port <= 65535
            or not args.cert
            or not args.key
        ):
            raise ValueError("explicit private bind, port and TLS are required")
        context = tls_context(args.cert, args.key)
        with SelectedServer(
            (args.bind, args.port), archive=archive, config=config, context=context
        ) as server:
            archive.prepare_release()
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (OSError, TypeError, ValueError, sqlite3.Error):
        print("selected archive startup refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
