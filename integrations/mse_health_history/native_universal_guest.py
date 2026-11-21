"""Admitted operator entry point for native universal guest storage."""

import argparse
from contextlib import closing
from hashlib import sha256
from hmac import compare_digest
import json
import os
import sqlite3
import sys

from integrations.healthbridge.capture import _unique_object

from .bp_server import Clock
from .native_runner import private_bytes
from .native_universal_https import UniversalServer
from .native_universal_transfer import UniversalStore
from .typed_vm import PIN, encoded, require
from .typed_vm_admitted import check_storage, tls_context

POLICY_SCHEMA = "mse.native-health-universal-guest-admission/0.1"


def open_service(policy, pin):
    guest = policy["guest"]
    clock = Clock()
    manifest = policy["manifest"]
    store = UniversalStore(
        guest["db"],
        manifest,
        trusted_manifest_sha256=sha256(encoded(manifest)).hexdigest(),
        starts=guest["start"],
        ends=guest["grants"]["writer"][1],
        clock=clock,
        database_bytes=policy["catalog_bytes"],
        policy_sha256=pin,
        admission_check=lambda: check_storage(policy),
    )
    return store, tls_context(policy)


def load_policy(path, pin):
    raw = private_bytes(path, 128 * 1024)
    require(
        PIN.fullmatch(pin) and compare_digest(sha256(raw).hexdigest(), pin),
        "universal admission pin mismatch",
    )
    policy = json.loads(raw, object_pairs_hook=_unique_object)
    require(
        set(policy)
        == {
            "schema_version",
            "guest",
            "manifest",
            "encrypted_device_uuid",
            "catalog_bytes",
            "reserve_bytes",
            "server_certificate_sha256",
            "client_ca_sha256",
        }
        and policy["schema_version"] == POLICY_SCHEMA
        and policy["encrypted_device_uuid"].startswith("CRYPT-LUKS2-")
        and type(policy["catalog_bytes"]) is int
        and 64 * 1024**2 <= policy["catalog_bytes"] <= 32 * 1024**3
        and type(policy["reserve_bytes"]) is int
        and 256 * 1024**2 <= policy["reserve_bytes"] <= 16 * 1024**3
        and all(
            PIN.fullmatch(policy[key])
            for key in ("server_certificate_sha256", "client_ca_sha256")
        ),
        "invalid universal guest policy",
    )
    guest = policy["guest"]
    require(
        set(guest)
        == {
            "bind",
            "port",
            "db",
            "certificate",
            "key",
            "client_ca",
            "grants",
            "purposes",
            "start",
            "max_bytes",
        }
        and type(guest["port"]) is int
        and 1024 <= guest["port"] <= 65535
        and type(guest["max_bytes"]) is int
        and guest["max_bytes"] == policy["manifest"]["wire_bytes"],
        "invalid universal guest configuration",
    )
    return policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("init", "serve"))
    parser.add_argument("admission")
    parser.add_argument("--trusted-admission-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        pin = args.trusted_admission_sha256
        policy = load_policy(args.admission, pin)
        guest = policy["guest"]
        check_storage(policy, preflight=True)
        store, context = open_service(policy, pin)
        if args.mode == "init":
            store.writable()
            require(
                not any(store.path.parent.iterdir()), "fresh universal store required"
            )
            store.initialize()
            return 0
        with closing(store.connect()):
            pass
        with UniversalServer(
            (guest["bind"], guest["port"]),
            store,
            context,
            guest["grants"],
            guest["purposes"],
            check_storage=lambda: check_storage(policy, check_reserve=False),
        ) as server:
            server.serve_forever()
    except (AttributeError, KeyError, OSError, ValueError, TypeError, sqlite3.Error):
        print("Admitted universal guest refused", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
