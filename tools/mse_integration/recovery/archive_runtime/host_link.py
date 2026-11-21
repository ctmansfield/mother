from pathlib import Path
import hashlib, ipaddress, json, os, subprocess, sys, time, uuid
from xml.etree import ElementTree as E

P = json.loads(Path(sys.argv[1]).read_text())
name = "phoenix-mse-evidence-20261121"
net = name + "-isolated"
bridge = "virbr-msearc"
table = "phoenix_mse_archive_link"
root = Path("/var/lib/libvirt/images") / name


def run(*a, timeout=15):
    return subprocess.check_output(a, text=True, timeout=timeout).strip()


def v(*a):
    return run("virsh", "--connect", "qemu:///system", *a)


assert hashlib.sha256(Path("/etc/machine-id").read_bytes()).hexdigest() == P["host_pin"]
assert Path("/proc/sys/kernel/random/boot_id").read_text().strip() == P["boot"]
assert v("domuuid", name) == P["uuid"]
assert not E.fromstring(v("dumpxml", name, "--inactive")).findall("./devices/interface")
assert net not in v("net-list", "--all", "--name").split()
assert not (Path("/sys/class/net") / bridge).exists()
assert table not in run("nft", "list", "tables")
cidr = ipaddress.IPv4Network(P["bridge_cidr"])
assert cidr.is_private and cidr.prefixlen == 30
host_address, guest_address = map(str, cidr.hosts())
assert not any(
    ipaddress.ip_network(r["dst"], strict=False).overlaps(cidr)
    for r in json.loads(run("ip", "-j", "-4", "route", "show", "table", "all"))
    if r.get("dst", "default") != "default"
)
os.umask(0o077)
network_uuid = str(uuid.uuid4())
xml = f'<network><name>{net}</name><uuid>{network_uuid}</uuid><bridge name="{bridge}" stp="off" delay="0"/><dns enable="no"/><ip address="{host_address}" netmask="255.255.255.252"/></network>'
rule = f"""create table inet {table} {{ comment "{P['uuid']}"; }}
add chain inet {table} input {{ type filter hook input priority -30; policy accept; }}
add chain inet {table} forward {{ type filter hook forward priority -30; policy accept; }}
add rule inet {table} input iifname "{bridge}" ct state established,related counter accept
add rule inet {table} input iifname "{bridge}" counter drop
add rule inet {table} forward iifname "{bridge}" counter drop
add rule inet {table} forward oifname "{bridge}" counter drop
"""
for f, data in ((root / "archive-network.xml", xml), (root / "archive-link.nft", rule)):
    with f.open("x") as h:
        h.write(data)
        h.flush()
        os.fsync(h.fileno())
with (root / "archive-network-intent.json").open("x") as h:
    json.dump(
        dict(
            domain=P["uuid"],
            network=network_uuid,
            bridge=bridge,
            table=table,
            mac=P["mac"],
        ),
        h,
    )
    h.flush()
    os.fsync(h.fileno())
run("nft", "-c", "-f", str(root / "archive-link.nft"))
run("nft", "-f", str(root / "archive-link.nft"))
raw = json.loads(run("nft", "-j", "-a", "-s", "list", "table", "inet", table))[
    "nftables"
]
assert next(x["table"]["comment"] for x in raw if "table" in x) == P["uuid"]
rules = [x["rule"] for x in raw if "rule" in x]
assert [next(iter(x["expr"][-1])) for x in rules] == ["accept", "drop", "drop", "drop"]
assert [x["chain"] for x in rules] == ["input", "input", "forward", "forward"]
(root / "archive-link-readback.json").write_text(json.dumps(raw))
v("net-define", str(root / "archive-network.xml"))
v("net-start", net)
defined = E.fromstring(v("net-dumpxml", net))
assert defined.findtext("uuid") == network_uuid and defined.find("forward") is None
assert defined.find("./ip/dhcp") is None and defined.find("dns").get("enable") == "no"
assert defined.find("ip").get("address") == host_address
v("shutdown", name, "--mode", "agent")
for _ in range(70):
    if v("domstate", name) == "shut off":
        break
    time.sleep(1)
else:
    raise RuntimeError("Owned guest did not power off")
v(
    "attach-interface",
    name,
    "--type",
    "network",
    "--source",
    net,
    "--model",
    "virtio",
    "--mac",
    P["mac"],
    "--config",
)
domain = E.fromstring(v("dumpxml", name, "--inactive"))
(interface,) = domain.findall("./devices/interface")
assert (
    interface.find("source").get("network") == net
    and interface.find("mac").get("address") == P["mac"]
)
assert not any(
    domain.findall("./devices/" + tag) for tag in ("filesystem", "hostdev", "graphics")
)
v("start", name)
print(
    json.dumps(
        dict(
            network_uuid=network_uuid,
            bridge=bridge,
            host=host_address,
            guest=guest_address,
            forward="disabled",
            policy_rules=len(rules),
            route_open=False,
        )
    )
)
