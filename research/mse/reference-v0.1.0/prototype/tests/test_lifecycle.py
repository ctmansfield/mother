from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.lifecycle import install, retire


class LifecycleTests(unittest.TestCase):
    def test_install_and_retire_preserve_all_payload_bytes(self):
        with tempfile.TemporaryDirectory(prefix="mse-install-test-") as directory:
            target = Path(directory) / "new-install"
            with redirect_stdout(io.StringIO()):
                install(target)
            before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
            output = io.StringIO()
            with redirect_stdout(output):
                retire(target)
            retired = Path(json.loads(output.getvalue())["retained_directory"])
            after = {str(p.relative_to(retired)): p.read_bytes() for p in retired.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertFalse(target.exists())
            self.assertTrue(retired.exists())

    def test_install_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory(prefix="mse-install-test-") as directory:
            target = Path(directory)
            marker = target / "unrelated"
            marker.write_text("preserve")
            with self.assertRaises(ValueError):
                install(target)
            self.assertEqual(marker.read_text(), "preserve")

    def test_retire_refuses_modified_code(self):
        with tempfile.TemporaryDirectory(prefix="mse-install-test-") as directory:
            target = Path(directory) / "new-install"
            with redirect_stdout(io.StringIO()):
                install(target)
            changed = target / "mse" / "model.py"
            changed.write_text(changed.read_text() + "\n# user edit\n")
            with self.assertRaises(ValueError):
                retire(target)
            self.assertTrue(target.exists())

    def test_retire_refuses_untracked_data(self):
        with tempfile.TemporaryDirectory(prefix="mse-install-test-") as directory:
            target = Path(directory) / "new-install"
            with redirect_stdout(io.StringIO()):
                install(target)
            (target / "user-data.json").write_text("{}")
            with self.assertRaises(ValueError):
                retire(target)
            self.assertTrue((target / "user-data.json").exists())


if __name__ == "__main__":
    unittest.main()
