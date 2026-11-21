"""Preflight or define an isolated archive clone from a confirmed cold qcow2 seed."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import uuid
from xml.etree import ElementTree as ET

NAME = "phoenix-mse-evidence-20261121"
NETWORK = NAME + "-isolated"
PARENT = Path("/var/lib/libvirt/images")
VM_DIR = PARENT / NAME
VIRSH = ("virsh", "--connect", "qemu:///system")
GIB = 1024**3


def run(*args, timeout=20):
    return subprocess.check_output(args, text=True, timeout=timeout)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    hashed = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


def hardware(args):
    return {
        "name": NAME,
        "domain_uuid": str(args.uuid),
        "vcpu": 4,
        "memory_mib": 8192,
        "system_disk_virtual_gib": 64,
        "first_boot_network": "none",
        "planned_network": NETWORK,
        "reserved_mac": args.mac,
        "host_device_passthrough": False,
        "public_listener": False,
        "system_disk": str(VM_DIR / "system.qcow2"),
    }


def render_domain(args):
    domain = ET.Element("domain", type="kvm")
    for name, value in (
        ("name", NAME),
        ("uuid", str(args.uuid)),
        ("memory", "8388608"),
        ("currentMemory", "8388608"),
        ("vcpu", "4"),
    ):
        ET.SubElement(domain, name).text = value
    os_config = ET.SubElement(domain, "os")
    ET.SubElement(os_config, "type", arch="x86_64", machine="pc-q35-8.2").text = "hvm"
    ET.SubElement(os_config, "boot", dev="hd")
    ET.SubElement(domain, "on_poweroff").text = "destroy"
    ET.SubElement(domain, "on_reboot").text = "restart"
    ET.SubElement(domain, "on_crash").text = "destroy"
    devices = ET.SubElement(domain, "devices")
    disk = ET.SubElement(devices, "disk", type="file", device="disk")
    ET.SubElement(disk, "driver", name="qemu", type="qcow2", cache="none")
    ET.SubElement(disk, "source", file=str(VM_DIR / "system.qcow2"))
    ET.SubElement(disk, "target", dev="vda", bus="virtio")
    ET.SubElement(disk, "serial").text = "PHX_MSE_20261121"
    ET.SubElement(devices, "controller", type="virtio-serial", index="0")
    channel = ET.SubElement(devices, "channel", type="unix")
    ET.SubElement(channel, "target", type="virtio", name="org.qemu.guest_agent.0")
    ET.SubElement(devices, "memballoon", model="none")
    return ET.tostring(domain, encoding="unicode")


def preflight(args):
    check(digest(Path("/etc/machine-id")) == args.host_pin, "Host identity changed")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    check(boot == str(args.boot), "Host boot changed")
    names = run(*VIRSH, "list", "--all", "--name").split()
    networks = run(*VIRSH, "net-list", "--all", "--name").split()
    check(NAME not in names and NETWORK not in networks, "Owned target already exists")
    check(not VM_DIR.exists() and not VM_DIR.is_symlink(), "Target directory exists")
    check(
        run("findmnt", "-n", "-o", "FSTYPE", "--target", str(PARENT)).strip() == "ext4",
        "Archive disk parent is not on the verified local filesystem type",
    )
    check(shutil.disk_usage(PARENT).free >= 150 * GIB, "Insufficient local free space")
    available = next(
        int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    check(available >= 24 * 1024 * 1024, "Insufficient available host memory")
    check(int(run("nproc").strip()) >= 8, "Insufficient host CPUs")
    seed = args.seed
    check(
        seed.is_absolute() and seed.resolve() == seed and PARENT in seed.parents,
        "Seed path is not canonical approved libvirt storage",
    )
    info = seed.lstat()
    check(
        stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
        "Seed is not a standalone file",
    )
    for name in names:
        xml = ET.fromstring(run(*VIRSH, "dumpxml", name, "--inactive"))
        live = ET.fromstring(run(*VIRSH, "dumpxml", name))
        for definition in (xml, live):
            check(
                definition.findtext("uuid") != str(args.uuid),
                "Domain UUID already exists",
            )
            check(
                not any(
                    m.get("address") == args.mac
                    for m in definition.findall("./devices/interface/mac")
                ),
                "Reserved MAC already exists",
            )
            check(
                not any(
                    d.get("file") == str(seed)
                    for d in definition.findall("./devices/disk/source")
                ),
                "Seed is already attached to a domain",
            )
    chain = json.loads(
        run("qemu-img", "info", "--output=json", "--backing-chain", str(seed))
    )
    check(
        len(chain) == 1
        and chain[0]["format"] == "qcow2"
        and chain[0]["virtual-size"] == 64 * GIB,
        "Unexpected seed format or backing chain",
    )
    check(digest(seed) == args.seed_sha256, "Cold seed content pin mismatch")
    return hardware(args)


def define(args):
    plan = preflight(args)
    VM_DIR.mkdir(mode=0o711)
    VM_DIR.chmod(0o711)
    receipt = VM_DIR / "intent.json"
    fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(
            {**plan, "seed_sha256": args.seed_sha256, "boot": str(args.boot)}, handle
        )
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(VM_DIR, os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    disk = VM_DIR / "system.qcow2"
    # The exclusive new directory contains only this task's state.
    run(
        "ionice",
        "-c",
        "3",
        "nice",
        "-n",
        "19",
        "cp",
        "--sparse=always",
        "--reflink=never",
        "--",
        str(args.seed),
        str(disk),
        timeout=240,
    )
    disk.chmod(0o600)
    check(digest(disk) == args.seed_sha256, "Copy differs from source seed")
    check(digest(args.seed) == args.seed_sha256, "Source changed during the copy")
    xml = VM_DIR / "domain.xml"
    with xml.open("x") as handle:
        handle.write(render_domain(args))
    xml.chmod(0o600)
    run(*VIRSH, "define", "--validate", str(xml))
    defined = ET.fromstring(run(*VIRSH, "dumpxml", NAME, "--inactive"))
    check(defined.findtext("uuid") == str(args.uuid), "Defined UUID mismatch")
    devices = defined.find("devices")
    check(devices is not None, "Missing defined devices")
    disks = devices.findall("disk")
    check(
        len(disks) == 1
        and disks[0].get("device") == "disk"
        and disks[0].get("type") == "file",
        "Unexpected defined disk set",
    )
    source = disks[0].find("source")
    driver = disks[0].find("driver")
    check(
        source is not None
        and source.get("file") == str(disk)
        and driver is not None
        and driver.get("type") == "qcow2",
        "Defined disk binding mismatch",
    )
    check(
        not any(devices.findall(tag) for tag in ("hostdev", "filesystem", "graphics")),
        "Unexpected external device",
    )
    chain = json.loads(
        run("qemu-img", "info", "--output=json", "--backing-chain", str(disk))
    )
    check(
        len(chain) == 1
        and chain[0]["format"] == "qcow2"
        and chain[0]["virtual-size"] == 64 * GIB,
        "Defined disk is not standalone",
    )
    check(
        not defined.findall("./devices/interface"), "New domain unexpectedly has a NIC"
    )
    check(
        run(*VIRSH, "domstate", NAME).strip() == "shut off",
        "New domain is not powered off",
    )
    return dict(plan, status="defined-not-started")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("preflight", "define"))
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--seed-sha256", required=True)
    parser.add_argument("--host-pin", required=True)
    parser.add_argument("--boot", type=uuid.UUID, required=True)
    parser.add_argument("--uuid", type=uuid.UUID, required=True)
    parser.add_argument("--mac", required=True)
    args = parser.parse_args()
    check(
        bool(re.fullmatch(r"52:54:00(?::[0-9a-f]{2}){3}", args.mac)),
        "Invalid local guest MAC",
    )
    result = preflight(args) if args.mode == "preflight" else define(args)
    print(json.dumps(result, indent=2))
