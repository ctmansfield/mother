"""Refresh the pinned pilot guest UTC from the synchronized physical host."""

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("/run/phoenix-mse-pilot-clock")
VM = "phoenix-mse-evidence-20261121"
VIRSH = ("virsh", "--connect", "qemu:///system")
TIMER = "phoenix-mse-pilot-clock.timer"
MAX_BRACKET = 30_000_000
MAX_POST_LAG = 100_000_000
MIN_CLOCK_MARGIN = 20_000_000
MAX_GUEST_DISPATCH_NS = 250_000_000


def run(*argv):
    return subprocess.check_output(argv, timeout=8, text=True).strip()


def agent(execute, **arguments):
    return json.loads(run(*VIRSH, "qemu-agent-command", VM, "--timeout", "4",
                          json.dumps(dict(execute=execute, arguments=arguments))))["return"]


def bracket():
    t0 = time.time_ns()
    guest = agent("guest-get-time")
    t1 = time.time_ns()
    assert 0 <= t1 - t0 <= MAX_BRACKET, "guest time sample uncertainty out of bounds"
    return guest - t1, guest - t0, guest


def main():
    mode, plan_path, guest_source_path = sys.argv[1:]
    assert mode in ("check", "apply", "run")
    plan = json.loads(Path(plan_path).read_bytes())
    mode = "apply" if mode == "run" else mode
    assert hashlib.sha256(Path("/etc/machine-id").read_bytes()).hexdigest() == plan["host_pin"]
    assert Path("/proc/sys/kernel/random/boot_id").read_text().strip() == plan["host_boot"]
    assert run(*VIRSH, "domuuid", VM) == plan["guest_uuid"]
    start = datetime.fromisoformat(plan["window_start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(plan["window_end"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    assert start <= now
    if now >= end:
        if mode == "apply" and Path("/run/systemd/system", TIMER).is_symlink():
            run("systemctl", "stop", TIMER)
        print(json.dumps(dict(cutoff_reached=True, adjusted=False)))
        return
    if end-now <= timedelta(seconds=10):
        print(json.dumps(dict(cutoff_guard=True, adjusted=False)))
        return
    assert run("timedatectl", "show", "-p", "NTPSynchronized", "--value") == "yes"
    assert run("timedatectl", "show", "-p", "NTP", "--value") == "yes"
    assert run("systemctl", "is-active", "systemd-timesyncd.service") == "active"
    source = Path(guest_source_path).read_bytes()
    assert hashlib.sha256(source).hexdigest() == plan["guest_source_sha256"]
    lower, upper, _ = min((bracket() for _ in range(3)), key=lambda pair: pair[1]-pair[0])
    assert lower >= -2_000_000_000 and upper <= MAX_POST_LAG
    # Target the trusted host reading with a small conservative margin for
    # dispatch and sampling. The guest can only add a positive relative offset.
    dispatch_low, dispatch_high, guest_sample = bracket()
    assert dispatch_low >= -2_000_000_000 and dispatch_high <= MAX_POST_LAG
    if end-datetime.now(timezone.utc) <= timedelta(seconds=10):
        print(json.dumps(dict(cutoff_guard=True, adjusted=False)))
        return
    target = str(time.time_ns() - MIN_CLOCK_MARGIN)
    cutoff_ns = str(int(end.timestamp()) * 1_000_000_000 + end.microsecond * 1000)
    pid = agent("guest-exec", path="/usr/bin/python3",
        arg=["-I", "-B", "-c", source.decode(), mode, plan["guest_machine"], plan["guest_boot"], target, cutoff_ns, str(guest_sample+MAX_GUEST_DISPATCH_NS)],
        **{"capture-output": True})["pid"]
    for _ in range(30):
        result = agent("guest-exec-status", pid=pid)
        if result["exited"]:
            assert result["exitcode"] == 0, "pinned guest clock check or adjustment refused"
            detail = json.loads(base64.b64decode(result["out-data"]))
            break
        time.sleep(.05)
    else:
        raise RuntimeError("Pinned guest clock command did not finish")
    low,high,_=min((bracket() for _ in range(3)),key=lambda pair: pair[1]-pair[0])
    if mode == "apply":
        assert low >= -MAX_POST_LAG and high <= MAX_POST_LAG, "post-check UTC alignment refused"
    print(json.dumps(dict(before_guest_minus_host_ns=[lower,upper],after_guest_minus_host_ns=[low,high],
                          **detail)))


if __name__ == "__main__":
    main()
