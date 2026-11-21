"""Guard exact owned relay ingress on the selected host and boot."""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path("/var/lib/libvirt/images/phoenix-mse-evidence-20261121/selected-live-relay")
TABLE = "phoenix_mse_selected_live_relay"
MARK = ROOT / "owner.json"
CONFIG = ROOT / "relay-config.json"
EXPECTED = ROOT / "guard.json"


def run(*args):
    return subprocess.check_output(args, text=True)


def records(table=TABLE):
    return json.loads(run("nft", "-j", "-s", "-a", "list", "table", "inet", table))[
        "nftables"
    ][1:]


def exists():
    all_tables = json.loads(run("nft", "-j", "list", "tables"))["nftables"]
    return any(item.get("table", {}).get("name") == TABLE for item in all_tables)


def canonical_rules(config, owner):
    host, phone = config["host"], config["phone"]
    lines = [
        f'create table inet {TABLE} {{ comment "{owner}"; }}',
        f"add chain inet {TABLE} input {{ type filter hook input priority -20; policy accept; }}",
    ]
    if config["phone_enabled"]:
        lines.append(
            f'add rule inet {TABLE} input iifname "tailscale0" ip saddr {phone} ip daddr {host} tcp dport 8446 counter accept'
        )
    lines.extend(
        (
            f'add rule inet {TABLE} input iifname "lo" ip saddr {host} ip daddr {host} tcp dport 8446 counter accept',
            f"add rule inet {TABLE} input ip daddr {host} tcp dport 8446 counter drop",
        )
    )
    return "\n".join(lines) + "\n"


def verify_kernel(state, config, owner):
    pairs = [("lo", config["host"], "accept"), (None, None, "drop")]
    if config["phone_enabled"]:
        pairs.insert(0, ("tailscale0", config["phone"], "accept"))
    assert [next(iter(x)) for x in state] == ["table", "chain"] + ["rule"] * len(pairs)
    table, chain, *rules = [next(iter(x.values())) for x in state]
    assert table["comment"] == owner and table["name"] == TABLE
    assert tuple(chain[x] for x in ("hook", "prio", "policy", "type")) == (
        "input",
        -20,
        "accept",
        "filter",
    )

    def match(left, right):
        return {"match": {"op": "==", "left": left, "right": right}}

    def payload(protocol, field):
        return {"payload": {"protocol": protocol, "field": field}}

    for rule, (interface, source, verdict) in zip(rules, pairs):
        terms = []
        if interface:
            terms += [
                match({"meta": {"key": "iifname"}}, interface),
                match(payload("ip", "saddr"), source),
            ]
        terms += [
            match(payload("ip", "daddr"), config["host"]),
            match(payload("tcp", "dport"), 8446),
            {"counter": None},
            {verdict: None},
        ]
        assert rule["table"] == TABLE and rule["chain"] == "input"
        actual = [
            {"counter": None} if list(x) == ["counter"] else x for x in rule["expr"]
        ]
        assert actual == terms


def main(mode):
    os.umask(0o077)
    expected = json.loads(EXPECTED.read_text())
    assert (
        hashlib.sha256(Path("/etc/machine-id").read_bytes()).hexdigest()
        == expected["host_pin"]
    )
    assert (
        Path("/proc/sys/kernel/random/boot_id").read_text().strip() == expected["boot"]
    )
    config = json.loads(CONFIG.read_text())
    for ip in (config["host"], config["phone"]):
        assert re.fullmatch(r"100(?:\.\d{1,3}){3}", ip)
    if mode == "check":
        rules = ROOT / "dry-run.nft"
        rules.write_text(canonical_rules(config, "preview-only"))
        output = run("nft", "--debug=netlink", "-c", "-f", str(rules))
        assert output.count("[ counter") == (3 if config["phone_enabled"] else 2)
    elif mode == "start":
        expiry = datetime.fromisoformat(config["expiry"].replace("Z", "+00:00"))
        assert datetime.now(timezone.utc) < expiry
        assert not exists() and not MARK.exists()
        assert not run("ss", "-Hltn", "sport = :8446").strip()
        address = json.loads(run("ip", "-j", "-4", "addr", "show", "dev", "tailscale0"))
        assert any(
            a.get("local") == config["host"] for r in address for a in r["addr_info"]
        )
        owner = "phoenix-mse-" + secrets.token_hex(12)
        rules = ROOT / "live.nft"
        rules.write_text(canonical_rules(config, owner))
        with MARK.open("x") as f:
            json.dump({"owner": owner}, f)
            f.flush()
            os.fsync(f.fileno())
        run("nft", "-c", "-f", str(rules))
        run("nft", "-f", str(rules))
        state = records()
        verify_kernel(state, config, owner)
        temporary = ROOT / "owner.new"
        temporary.write_text(json.dumps({"owner": owner, "state": state}))
        temporary.replace(MARK)
    elif mode == "stop":
        if exists():
            marker = json.loads(MARK.read_text())
            state = records()
            assert state[0]["table"]["comment"] == marker["owner"]
            if "state" in marker:
                assert state == marker["state"]
            run("nft", "delete", "table", "inet", TABLE)
        assert not exists()
        if MARK.exists():
            nonce = json.loads(MARK.read_text())["owner"]
            assert re.fullmatch(r"phoenix-mse-[a-f0-9]{24}", nonce)
            MARK.rename(ROOT / (nonce + ".closed.private.json"))
    else:
        raise ValueError("Invalid firewall operation")


if __name__ == "__main__":
    main(sys.argv[1])
