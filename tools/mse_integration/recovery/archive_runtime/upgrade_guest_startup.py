"""Change only startup dependencies on an exact pinned archive unit."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

UNIT = Path("/etc/systemd/system/phoenix-mse-archive.service")
OLD_DEPS = b"After=network-online.target\nWants=network-online.target\n"
NEW_DEPS = b"After=systemd-networkd.service\nRequires=systemd-networkd.service\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_sha256")
    parser.add_argument("interface")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,15}", args.interface):
        raise ValueError("Expected a single archive interface")

    info = UNIT.lstat()
    if info.st_uid != 0 or not stat.S_ISREG(info.st_mode):
        raise ValueError("Expected the installed root-owned archive unit")
    old = UNIT.read_bytes()
    if hashlib.sha256(old).hexdigest() != args.old_sha256:
        raise ValueError("Installed archive unit differs from the reviewed predecessor")
    if old.count(OLD_DEPS) != 1 or old.count(b"\nExecStart=") != 1:
        raise ValueError("Unexpected archive service dependencies or command")
    wait = (
        "/usr/lib/systemd/systemd-networkd-wait-online "
        f"--interface={args.interface}:routable --ipv4 --timeout=20"
    )
    new = old.replace(OLD_DEPS, NEW_DEPS).replace(
        b"\nExecStart=", f"\nExecStartPre={wait}\nExecStart=".encode()
    )
    with tempfile.TemporaryDirectory(dir=UNIT.parent) as temp:
        candidate = Path(temp) / UNIT.name
        candidate.write_bytes(new)
        candidate.chmod(stat.S_IMODE(info.st_mode))
        subprocess.run(["systemd-analyze", "verify", str(candidate)], check=True)
        if args.apply:
            if UNIT.read_bytes() != old:
                raise RuntimeError("Installed archive unit changed during verification")
            os.replace(candidate, UNIT)
            subprocess.run(["systemctl", "daemon-reload"], check=True)
            if UNIT.read_bytes() != new:
                raise RuntimeError("Installed archive unit does not match the reviewed update")
    print(hashlib.sha256(new).hexdigest())


if __name__ == "__main__":
    main()
