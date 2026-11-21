"""Explicitly admitted native BP guest service. Deployment belongs to the operator."""

import argparse
from contextlib import closing
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path
import shutil
import sqlite3
import ssl
import sys

from integrations.healthbridge.capture import _unique_object

from .bp_server import Clock
from .files import private_path
from .native_runner import private_bytes
from .typed_vm import MAX_BYTES, PIN, SYNTHETIC, Capacity, _TypedStore, require
from .typed_vm_https import TypedServer

SCHEMA = "mse.native-bp-real-guest-admission/0.1"
FIELDS = {
    "schema_version",
    "mode",
    "encrypted_device_uuid",
    "reserve_bytes",
    "server_certificate_sha256",
    "client_ca_sha256",
    "catalog_bytes",
    "guest",
}
GUEST_FIELDS = {
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
}


def load_admission(path, trusted_pin):
    """Authenticate exact policy bytes against a separately trusted operator pin."""
    require(PIN.fullmatch(trusted_pin), "trusted guest admission digest required")
    raw = private_bytes(path, 64 * 1024)
    require(
        compare_digest(sha256(raw).hexdigest(), trusted_pin),
        "guest admission digest mismatch",
    )
    policy = json.loads(raw, object_pairs_hook=_unique_object)
    require(
        isinstance(policy, dict)
        and set(policy) == FIELDS
        and policy["schema_version"] == SCHEMA
        and policy["mode"] == "admitted-native-bp-import",
        "invalid real guest admission",
    )
    guest = policy["guest"]
    require(
        isinstance(guest, dict)
        and set(guest) == GUEST_FIELDS
        and not SYNTHETIC.fullmatch(guest["scope"]["enrollment_id"])
        and type(guest["port"]) is int
        and 1024 <= guest["port"] <= 65535
        and guest["port"] not in (8446, 8447, 8448)
        and type(guest["max_bytes"]) is int
        and 1 <= guest["max_bytes"] <= 512 * MAX_BYTES
        and type(policy["catalog_bytes"]) is int
        and 16 * MAX_BYTES <= policy["catalog_bytes"] <= 2 * 1024 * MAX_BYTES
        and guest["max_bytes"] <= policy["catalog_bytes"]
        and type(policy["reserve_bytes"]) is int
        and 256 * MAX_BYTES <= policy["reserve_bytes"] <= 16 * 1024 * MAX_BYTES
        and policy["encrypted_device_uuid"].startswith("CRYPT-LUKS2-")
        and all(
            PIN.fullmatch(policy[k])
            for k in ("server_certificate_sha256", "client_ca_sha256")
        ),
        "invalid real guest scope or storage limits",
    )
    return policy


def check_storage(policy, *, preflight=False, check_reserve=True):
    """Verify this database's filesystem is on the approved Linux dm-crypt mapping."""
    require(sys.platform == "linux", "admitted guest requires Linux")
    root = Path(policy["guest"]["db"]).parent
    private_path(root, directory=True)
    device = root.stat().st_dev
    dm_uuid = Path(f"/sys/dev/block/{os.major(device)}:{os.minor(device)}/dm/uuid")
    require(
        dm_uuid.read_text().strip() == policy["encrypted_device_uuid"],
        "guest device binding failed",
    )
    # Allow for SQLite layout and rollback journal in addition to the exact wire quota.
    extra = 2 * policy["catalog_bytes"] if preflight else 0
    if check_reserve and shutil.disk_usage(root).free < policy["reserve_bytes"] + extra:
        raise Capacity("guest free space below admitted reserve")


class AdmittedServer(TypedServer):
    def __init__(
        self, address, store, context, policy, *, clock=None, bind_and_activate=True
    ):
        self.policy = policy
        guest = policy["guest"]
        super().__init__(
            address,
            store,
            context,
            guest["grants"],
            guest["start"],
            guest["end"],
            snapshots=guest["snapshots"],
            clock=clock,
            bind_and_activate=bind_and_activate,
        )

    def check_lease(self, role):
        super().check_lease(role)
        check_storage(self.policy, check_reserve=role == "writer")
        return super().check_lease(role)


def admitted_store(policy, trusted_pin):
    guest = policy["guest"]
    return _TypedStore(
        guest["db"],
        guest["scope"],
        guest["bounds"],
        guest["artifact"],
        guest["inventory"],
        max_batches=guest["max_batches"],
        max_bytes=guest["max_bytes"],
        admitted_deletions=guest["admitted_deletions"],
        admission_pin=trusted_pin,
        database_bytes=policy["catalog_bytes"],
    )


def tls_context(policy):
    guest = policy["guest"]
    for field, pin in (
        ("certificate", policy["server_certificate_sha256"]),
        ("client_ca", policy["client_ca_sha256"]),
    ):
        exact = private_bytes(guest[field], 64 * 1024)
        require(
            compare_digest(sha256(exact).hexdigest(), pin),
            "guest TLS source pin mismatch",
        )
    private_path(Path(guest["key"]).absolute(), directory=False)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(guest["certificate"], guest["key"])
    context.load_verify_locations(cafile=guest["client_ca"])
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "serve"))
    parser.add_argument("admission")
    parser.add_argument("--trusted-admission-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        pin = args.trusted_admission_sha256
        policy = load_admission(args.admission, pin)
        guest = policy["guest"]
        check_storage(policy, preflight=True)
        store = admitted_store(policy, pin)
        clock = Clock()
        if args.mode == "init":
            require(
                guest["start"] <= clock() < guest["grants"]["writer"][1],
                "guest initialization lease closed",
            )
            # Validate the mTLS grants, address and descriptor before opening a database.
            require(
                not any(store.path.parent.iterdir()),
                "fresh dedicated guest root required",
            )
            with AdmittedServer(
                (guest["bind"], guest["port"]),
                store,
                tls_context(policy),
                policy,
                clock=clock,
                bind_and_activate=False,
            ):
                store.initialize()
            return 0
        with closing(store.connect()):
            pass
        with AdmittedServer(
            (guest["bind"], guest["port"]),
            store,
            tls_context(policy),
            policy,
            clock=clock,
        ) as server:
            server.serve_forever()
    except (AttributeError, KeyError, OSError, ValueError, TypeError, sqlite3.Error):
        print("Admitted native guest refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
