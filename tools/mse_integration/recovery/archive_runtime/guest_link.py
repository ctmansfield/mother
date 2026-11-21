from pathlib import Path
import ipaddress
import json
import os
import sys

mac = sys.argv[1]
address = ipaddress.IPv4Interface(sys.argv[2])
assert address.ip.is_private and address.network.prefixlen == 30
root = Path("/etc/systemd/network")
p = root / "05-phoenix-mse-archive.network"
if p.exists():
    raise ValueError("Archive network configuration already exists")
os.umask(0o022)
with p.open("x") as f:
    f.write(
        "[Match]\nMACAddress="
        + mac
        + "\n\n[Link]\nRequiredForOnline=no\n\n[Network]\nAddress="
        + str(address)
        + "\nDHCP=no\nLinkLocalAddressing=no\nIPv6AcceptRA=no\n"
    )
print(json.dumps(dict(address=str(address), default_gateway=False)))
