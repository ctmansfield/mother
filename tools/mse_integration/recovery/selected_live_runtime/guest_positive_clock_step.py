"""Guest-side x86_64 Linux positive relative clock adjustment."""

import ctypes as c
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

NANOSECOND = 1_000_000_000
MIN_STEP_NS = 50_000_000
MAX_STEP_NS = 2 * NANOSECOND
CUTOFF_RESERVE_NS = 5 * NANOSECOND


class Timeval(c.Structure):
    _fields_ = [("seconds", c.c_long), ("fraction", c.c_long)]


class Timex(c.Structure):
    _fields_ = [
        ("modes", c.c_uint), ("offset", c.c_long), ("freq", c.c_long),
        ("maxerror", c.c_long), ("esterror", c.c_long), ("status", c.c_int),
        ("constant", c.c_long), ("precision", c.c_long), ("tolerance", c.c_long),
        ("time", Timeval), ("tick", c.c_long), ("ppsfreq", c.c_long),
        ("jitter", c.c_long), ("shift", c.c_int), ("stabil", c.c_long),
        ("jitcnt", c.c_long), ("calcnt", c.c_long), ("errcnt", c.c_long),
        ("stbcnt", c.c_long), ("tai", c.c_int), ("padding", c.c_int * 11),
    ]


def clock_function():
    assert platform.machine() == "x86_64" and c.sizeof(c.c_long) == 8
    assert c.sizeof(Timex) == 208 and Timex.time.offset == 72
    header = Path("/usr/include/linux/timex.h").read_text()
    assert "#define ADJ_SETOFFSET" in header and "#define ADJ_NANO" in header
    libc = c.CDLL(None, use_errno=True)
    step = libc.clock_adjtime
    step.argtypes = [c.c_int, c.POINTER(Timex)]
    step.restype = c.c_int
    return step


def adjust(offset, cutoff_ns, execution_deadline_ns):
    assert MIN_STEP_NS <= offset <= MAX_STEP_NS
    step = clock_function()
    value = Timex()
    value.modes = 0x0100 | 0x2000  # ADJ_SETOFFSET | ADJ_NANO
    value.time.seconds, value.time.fraction = divmod(offset, NANOSECOND)
    # This check is in the guest process that is about to call the kernel.
    # Reserve the entire bounded correction plus five seconds of UTC margin.
    now = time.time_ns()
    if now >= execution_deadline_ns:
        raise RuntimeError("guest correction command expired before adjustment")
    if now + offset + CUTOFF_RESERVE_NS >= cutoff_ns:
        raise RuntimeError("guest correction refused at the conservative cutoff guard")
    if step(0, c.byref(value)) < 0:  # CLOCK_REALTIME
        error = c.get_errno()
        raise OSError(error, "positive relative guest clock adjustment failed")


def main():
    mode, machine_hash, boot, target_text, cutoff_text, deadline_text = sys.argv[1:]
    assert mode in ("check", "apply")
    assert hashlib.sha256(Path("/etc/machine-id").read_bytes()).hexdigest() == machine_hash
    assert Path("/proc/sys/kernel/random/boot_id").read_text().strip() == boot
    assert clock_function()(0, c.byref(Timex())) >= 0  # modes=0 is a kernel clock read
    target = int(target_text)
    before = time.time_ns()
    delta = target - before
    assert -100_000_000 <= delta <= MAX_STEP_NS, "guest clock offset out of bounds"
    applied = mode == "apply" and delta >= MIN_STEP_NS
    assert before < int(deadline_text), "guest correction command expired on arrival"
    if applied:
        adjust(delta, int(cutoff_text), int(deadline_text))
    after = time.time_ns()
    if applied:
        assert after >= before + delta
    print(json.dumps(dict(mode=mode, candidate_offset_ns=delta, applied=applied)))


if __name__ == "__main__":
    main()
