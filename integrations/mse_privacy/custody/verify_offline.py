"""Run finite, dependency-free synthetic custody and authority qualification."""

from pathlib import Path
import subprocess
import sys

WORKER = """
import sys
import unittest

root = sys.argv[1]
sys.path.insert(0, root)
suite = unittest.defaultTestLoader.discover(root + "/tests/integration/mse_privacy/custody")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.testsRun or result.skipped or result.expectedFailures:
    print("Qualification requires a nonempty suite without skips or expected failures",
          file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(0 if result.wasSuccessful() else 1)
"""


def verify():
    root = Path(__file__).resolve().parents[3]
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", WORKER, str(root)],
            cwd=root,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        print("Offline custody verifier could not complete", file=sys.stderr)
        return 1
    return result.returncode if result.returncode >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(verify())
