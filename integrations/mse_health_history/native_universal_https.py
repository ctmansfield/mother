"""Private role-scoped HTTPS for a witnessed native universal import."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import closing
from hashlib import sha256
from http.server import HTTPServer
from ipaddress import IPv4Address
import json
import re
import ssl
from time import monotonic

from .typed_vm import Capacity, PIN, encoded, is_ref, require, valid_clock
from .typed_vm_https import Closed, TypedHandler, content_digest
from .vault_server import PRIVATE

PURPOSES = {"mother", "coach"}
SAFE_FIELDS = {
    "quantity": ("value", "source_unit"),
    "blood_pressure": (),
    "category": ("source_state",),
    "sleep_state": ("source_state",),
    "activity_date": ("local_date",),
    "workout": ("source_activity", "duration", "source_duration_unit"),
}
MAX_PROJECTION_BYTES = 512 * 1024


class UniversalServer(HTTPServer):
    def __init__(self, address, store, context, grants, policies, *, check_storage):
        host, port = address
        require(
            port not in (8446, 8447, 8448)
            and any(IPv4Address(host) in network for network in PRIVATE)
            and context.verify_mode == ssl.CERT_REQUIRED
            and context.minimum_version >= ssl.TLSVersion.TLSv1_2,
            "dedicated private universal mutual TLS required",
        )
        require(
            set(policies) <= PURPOSES
            and set(grants) == {"writer", "receipt", "source", *policies}
            and all(
                PIN.fullmatch(pin) and valid_clock(until) and until > store.starts
                for pin, until in grants.values()
            )
            and len({pin for pin, _ in grants.values()}) == len(grants)
            and grants["writer"][1] == store.ends,
            "invalid independent universal role grants",
        )
        subjects = set()
        for policy in policies.values():
            require(
                set(policy)
                == {
                    "subject",
                    "adapters",
                    "types",
                    "units",
                    "states",
                    "activities",
                    "from",
                    "before",
                    "timeless",
                    "limit",
                }
                and is_ref(policy["subject"])
                and policy["subject"] not in subjects
                and isinstance(policy["adapters"], list)
                and bool(policy["adapters"])
                and set(policy["adapters"]) <= SAFE_FIELDS.keys()
                and isinstance(policy["types"], list)
                and 1 <= len(policy["types"]) <= 128
                and all(is_ref(value) for value in policy["types"])
                and all(
                    isinstance(policy[key], list)
                    and len(policy[key]) <= 128
                    and all(
                        isinstance(value, str) and 0 < len(value) <= 128
                        for value in policy[key]
                    )
                    for key in ("units", "states", "activities")
                )
                and valid_clock(policy["from"])
                and valid_clock(policy["before"])
                and policy["from"] < policy["before"]
                and type(policy["timeless"]) is bool
                and type(policy["limit"]) is int
                and 1 <= policy["limit"] <= 128,
                "invalid universal purpose policy",
            )
            subjects.add(policy["subject"])
        self.store, self.context, self.grants = store, context, grants
        self.policies = json.loads(encoded(policies))
        self.check_storage = check_storage
        self.route = f"/v1/native-universal/imports/{store.manifest['import_ref']}"
        super().__init__(address, UniversalHandler)

    def handle_error(self, request, client_address):
        # Unexpected handler failures close the connection without a traceback.
        # The request and stored source records may contain sensitive data.
        pass

    def get_request(self):
        sock, peer = super().get_request()
        sock.settimeout(5)
        try:
            return self.context.wrap_socket(sock, server_side=True), peer
        except OSError:
            sock.close()
            raise

    def check_lease(self, role):
        self.check_storage()
        if not self.store.starts <= self.store.clock() < self.grants[role][1]:
            raise Closed("universal role lease closed")

    def features(self, purpose, cursor):
        policy = self.policies[purpose]
        self.store.receipt()
        scope = sha256(encoded([self.store.pin, purpose, policy])).hexdigest()
        after = ("", 0, 0)
        if cursor is not None:
            try:
                parsed = json.loads(
                    urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
            except (ValueError, RecursionError):
                raise ValueError("invalid universal cursor") from None
            require(
                isinstance(parsed, list)
                and len(parsed) == 4
                and parsed[0] == scope
                and isinstance(parsed[1], str)
                and (parsed[1] == "" or valid_clock(parsed[1]))
                and all(type(x) is int and 0 < x <= 90_000_000 for x in parsed[2:]),
                "universal cursor outside purpose scope",
            )
            after = tuple(parsed[1:])
        adapters = policy["adapters"]
        slots = ",".join("?" for _ in adapters)
        source_types = policy["types"]
        type_slots = ",".join("?" for _ in source_types)
        from_clock, before = policy["from"], policy["before"]
        with closing(self.store.connect()) as db:
            rows = db.execute(
                f"""WITH values_in_scope AS (
                    SELECT member,ordinal,source_type,adapter,typed,coalesce(
                        json_extract(typed,'$.clocks.endDate.utc'),
                        json_extract(typed,'$.clocks.startDate.utc'),
                        json_extract(typed,'$.clocks.event_end'), ''
                    ) AS clock FROM native_source_occurrences
                    WHERE artifact=? AND adapter IN ({slots}) AND source_type IN ({type_slots})
                )
                SELECT * FROM values_in_scope
                WHERE ((clock>=? AND clock<?) OR (clock='' AND ?))
                  AND (clock,member,ordinal)>(?,?,?)
                ORDER BY clock,member,ordinal LIMIT ?""",
                (
                    self.store.manifest["artifact"],
                    *adapters,
                    *source_types,
                    from_clock,
                    before,
                    policy["timeless"],
                    *after,
                    policy["limit"] + 1,
                ),
            ).fetchall()
        more = len(rows) > policy["limit"]
        items = []
        cursor_out = None
        for member, ordinal, source_type, adapter, body, clock in rows[
            : policy["limit"]
        ]:
            source = json.loads(body)
            fields = {key: source[key] for key in SAFE_FIELDS[adapter] if key in source}
            cursor_out = (
                urlsafe_b64encode(encoded([scope, clock, member, ordinal]))
                .decode()
                .rstrip("=")
            )
            if any(
                key in fields and fields[key] not in policy[allowlist]
                for key, allowlist in (
                    ("source_unit", "units"),
                    ("source_duration_unit", "units"),
                    ("source_state", "states"),
                    ("source_activity", "activities"),
                )
            ):
                continue
            if adapter == "blood_pressure":
                if source.get("pairing") != "paired":
                    continue
                values = {part["role"]: part["value"] for part in source["components"]}
                if set(values) != {"systolic", "diastolic"}:
                    continue
                fields = dict(values, unit="mmHg")
            items.append(
                {
                    "ref": sha256(encoded([scope, member, ordinal])).hexdigest(),
                    "kind": adapter,
                    "source_type": source_type,
                    "event_utc": clock or None,
                    "fields": fields,
                }
            )
        raw = encoded(
            {
                "schema_version": "mse.native-health-purpose-features/0.1",
                "purpose": purpose,
                "subject": policy["subject"],
                "rows": items,
                "next": cursor_out if more else None,
            }
        )
        if len(raw) > MAX_PROJECTION_BYTES:
            raise Capacity("universal purpose response byte bound")
        return raw


class UniversalHandler(TypedHandler):
    def reply(self, status, body):
        binary = getattr(self, "binary", False) and status == 200
        self.send_response(status)
        self.send_header(
            "Content-Type", "application/octet-stream" if binary else "application/json"
        )
        if binary:
            self.send_header("Content-Disposition", "attachment")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        root = re.escape(self.server.route)
        part = re.fullmatch(root + r"/parts/([1-9][0-9]{0,5})", self.path)
        if not part and self.path != self.server.route + "/terminal":
            self.error(404, "absent")
            return

        def receive():
            headers = self.headers
            sizes = headers.get_all("Content-Length", [])
            require(
                headers.get("Transfer-Encoding") is None
                and headers.get("Content-Encoding") is None
                and len(sizes) == 1
                and re.fullmatch(r"(?:0|[1-9][0-9]{0,8})", sizes[0]),
                "invalid universal framing",
            )
            size = int(sizes[0])
            if part is None:
                require(size == 0, "terminal body must be empty")
                return self.server.store.finish()
            if size > self.server.store.manifest["part_bytes"]:
                raise Capacity("native universal part cap")
            pins = headers.get_all("Content-Digest", [])
            previous = headers.get_all("X-Native-Predecessor", [])
            require(
                headers.get_all("Content-Type", []) == ["application/octet-stream"]
                and len(pins) == 1
                and len(previous) <= 1
                and (not previous or PIN.fullmatch(previous[0])),
                "invalid universal part envelope",
            )
            deadline = monotonic() + 10
            raw = bytearray()
            while len(raw) < size:
                wait = deadline - monotonic()
                if wait <= 0:
                    raise ValueError("universal part deadline")
                self.connection.settimeout(min(wait, 5))
                block = self.rfile.read1(size - len(raw))
                require(bool(block), "truncated universal part")
                raw.extend(block)
            require(content_digest(raw) == pins[0], "universal part digest mismatch")
            pin = sha256(raw).hexdigest()
            status = self.server.store.put(
                int(part[1]),
                bytes(raw),
                predecessor=previous[0] if previous else None,
                digest=pin,
            )
            return status, encoded(
                {"status": "staged", "part_seq": int(part[1]), "sha256": pin}
            )

        self.run_operation("writer", receive)

    def do_GET(self):
        root = re.escape(self.server.route)
        if self.path == self.server.route + "/receipt":
            self.run_operation("receipt", lambda: (200, self.server.store.receipt()))
            return
        if self.path == self.server.route + "/manifest":
            self.run_operation(
                "receipt", lambda: (200, encoded(self.server.store.accepted_manifest()))
            )
            return
        members = re.fullmatch(
            root + r"/source/members[?]after=([0-9]{1,6})", self.path
        )
        if members:
            self.run_operation(
                "source",
                lambda: (
                    200,
                    encoded(
                        {
                            "rows": self.server.store.restricted_members(
                                after=int(members[1])
                            )
                        }
                    ),
                ),
            )
            return
        source = re.fullmatch(
            root + r"/source[?]member=([0-9]{1,6})&ordinal=([0-9]{1,9})", self.path
        )
        if source:
            self.run_operation(
                "source",
                lambda: (
                    200,
                    encoded(
                        {
                            "rows": self.server.store.restricted_occurrences(
                                after=tuple(map(int, source.groups()))
                            )
                        }
                    ),
                ),
            )
            return
        tree = re.fullmatch(
            root + r"/source/([1-9][0-9]{0,5})/elements[?]after=([0-9]{1,9})", self.path
        )
        if tree:
            self.run_operation(
                "source",
                lambda: (
                    200,
                    encoded(
                        {
                            "rows": self.server.store.restricted_elements(
                                int(tree[1]), after=int(tree[2])
                            )
                        }
                    ),
                ),
            )
            return
        events = re.fullmatch(
            root
            + r"/source/([1-9][0-9]{0,5})/occurrences/([0-9]{1,9})[?]after=([0-9]{1,9})",
            self.path,
        )
        if events:
            self.run_operation(
                "source",
                lambda: (
                    200,
                    encoded(
                        {
                            "rows": self.server.store.restricted_events(
                                int(events[1]), int(events[2]), after=int(events[3])
                            )
                        }
                    ),
                ),
            )
            return
        payload = re.fullmatch(
            root
            + r"/source/([1-9][0-9]{0,5})/payload[?]sha256=([0-9a-f]{64})&offset=([0-9]{1,11})&length=([0-9]{1,8})",
            self.path,
        )
        if payload:
            self.binary = True
            self.run_operation(
                "source",
                lambda: (
                    200,
                    self.server.store.restricted_member_range(
                        int(payload[1]), payload[2], int(payload[3]), int(payload[4])
                    ),
                ),
            )
            return
        projection = re.fullmatch(
            root + r"/purposes/(mother|coach)(?:[?]after=([A-Za-z0-9_-]{1,300}))?",
            self.path,
        )
        if projection:
            self.run_operation(
                projection[1], lambda: (200, self.server.features(*projection.groups()))
            )
            return
        self.error(404, "absent")
