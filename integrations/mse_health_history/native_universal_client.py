"""Manual transport of a protected native universal spool, with separate readback."""

import argparse
from hashlib import sha256
from http.client import HTTPSConnection
from hmac import compare_digest
import json
from pathlib import Path
import ssl
import sys

from integrations.healthbridge.capture import _unique_object

from .files import private_path
from .native_runner import private_bytes
from .native_universal_transfer import PART_BYTES, SCHEMA
from .typed_vm import PIN, encoded, is_ref, require
from .typed_vm_https import content_digest


class ManualTransfer:
    def __init__(self, config):
        require(
            set(config)
            == {
                "host",
                "port",
                "spool",
                "manifest",
                "manifest_sha256",
                "guest_ca",
                "writer",
                "receipt",
            }
            and type(config["port"]) is int
            and 1024 <= config["port"] <= 65535
            and config["port"] not in (8446, 8447, 8448)
            and isinstance(config["host"], str)
            and 1 <= len(config["host"]) <= 253
            and not any(value in config["host"] for value in ("/", ":", "@", "\\"))
            and all(
                isinstance(config[role], list) and len(config[role]) == 2
                for role in ("writer", "receipt")
            )
            and config["writer"] != config["receipt"],
            "invalid universal sender configuration",
        )
        self.config = config
        self.manifest = json.loads(
            private_bytes(config["manifest"], 128 * 1024),
            object_pairs_hook=_unique_object,
        )
        self.pin = sha256(encoded(self.manifest)).hexdigest()
        require(
            PIN.fullmatch(config["manifest_sha256"])
            and compare_digest(self.pin, config["manifest_sha256"])
            and self.manifest["schema_version"] == SCHEMA
            and is_ref(self.manifest["import_ref"])
            and self.manifest["part_bytes"] == PART_BYTES
            and type(self.manifest["wire_bytes"]) is int
            and 0 < self.manifest["wire_bytes"] <= 16 * 1024**3
            and self.manifest["parts"]
            == (self.manifest["wire_bytes"] + PART_BYTES - 1) // PART_BYTES,
            "universal sender manifest mismatch",
        )
        self.path = Path(config["spool"]).absolute()
        private_path(self.path, directory=False)
        self.route = "/v1/native-universal/imports/" + self.manifest["import_ref"]

    def verify_spool(self, stream):
        total = 0
        digest = sha256()
        while part := stream.read(PART_BYTES):
            total += len(part)
            require(
                total <= self.manifest["wire_bytes"], "universal spool length exceeded"
            )
            digest.update(part)
        require(
            total == self.manifest["wire_bytes"]
            and digest.hexdigest() == self.manifest["wire_sha256"],
            "universal spool does not match reviewed bytes",
        )
        stream.seek(0)

    def request(self, role, method, suffix, data=None, headers=None):
        certificate, key = self.config[role]
        private_path(Path(key).absolute(), directory=False)
        context = ssl.create_default_context(cafile=self.config["guest_ca"])
        context.load_cert_chain(certificate, key)
        client = HTTPSConnection(
            self.config["host"], self.config["port"], context=context, timeout=12
        )
        try:
            client.request(method, self.route + suffix, data, headers=headers or {})
            response = client.getresponse()
            body = response.read(16_385)
            require(len(body) <= 16_384, "universal sender response exceeds bound")
            return response.status, json.loads(body)
        finally:
            client.close()

    def transfer(self):
        with self.path.open("rb") as stream:
            self.verify_spool(stream)
            predecessor = None
            for seq in range(1, self.manifest["parts"] + 1):
                raw = stream.read(PART_BYTES)
                digest = sha256(raw).hexdigest()
                headers = {
                    "Content-Type": "application/octet-stream",
                    "Content-Digest": content_digest(raw),
                }
                if predecessor is not None:
                    headers["X-Native-Predecessor"] = predecessor
                status, body = self.request(
                    "writer", "PUT", f"/parts/{seq}", raw, headers
                )
                require(
                    status in (200, 201)
                    and body == {"status": "staged", "part_seq": seq, "sha256": digest},
                    "universal staged part response mismatch",
                )
                predecessor = digest
            status, terminal = self.request("writer", "PUT", "/terminal", b"")
            require(status in (200, 201), "universal terminal not verified")
            return self.verify_receipt(terminal)

    def verify_receipt(self, terminal=None):
        status, receipt = self.request("receipt", "GET", "/receipt")
        record = {
            "schema_version": SCHEMA,
            "status": "witnessed",
            "manifest_sha256": self.pin,
            "import_ref": self.manifest["import_ref"],
        }
        expected = dict(record, receipt_id=sha256(encoded(record)).hexdigest())
        require(
            status == 200
            and receipt == expected
            and (terminal is None or terminal == expected),
            "universal receipt reconciliation failed",
        )
        return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "execute-manual", "readback"))
    parser.add_argument("config")
    parser.add_argument("--trusted-sender-sha256", required=True)
    args = parser.parse_args()
    try:
        raw = private_bytes(args.config, 64 * 1024)
        require(
            PIN.fullmatch(args.trusted_sender_sha256)
            and compare_digest(sha256(raw).hexdigest(), args.trusted_sender_sha256),
            "universal sender admission pin mismatch",
        )
        client = ManualTransfer(json.loads(raw, object_pairs_hook=_unique_object))
        if args.mode == "preflight":
            with client.path.open("rb") as stream:
                client.verify_spool(stream)
            print("UNIVERSAL_SPOOL_PREFLIGHT_PASS")
        elif args.mode == "readback":
            client.verify_receipt()
            print("UNIVERSAL_RECEIPT_REOPENED")
        else:
            client.transfer()
            print("UNIVERSAL_RECEIPT_REOPENED")
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        print("UNIVERSAL_REFUSED_OR_RECONCILE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
