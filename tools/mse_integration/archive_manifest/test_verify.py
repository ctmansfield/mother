from io import BytesIO
import json
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from verify import VerificationError, verify_package

SOURCE = "research/mse/reference-v0.1.0/prototype/mse/__init__.py"
PIN = "b7aae4f2216d27f0544eab9fe9698286fe49d716"
MEMBER = "archive/reference.py"
ROOT = Path(__file__).resolve().parents[3]


class PackageVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.package = Path(temporary.name) / "synthetic-package"
        self.content = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{PIN}:{SOURCE}"])
        self.allowlist = json.dumps([{"commit": PIN, "member": MEMBER, "source": SOURCE}]).encode()

    def test_actual_git_blob_matches_both_archive_formats(self):
        with ZipFile(self.package, "w") as archive:
            archive.writestr(MEMBER, self.content)
        zipped = verify_package(ROOT, self.package, self.allowlist)
        with tarfile.open(self.package, "w") as archive:
            entry = tarfile.TarInfo(MEMBER)
            entry.size = len(self.content)
            archive.addfile(entry, BytesIO(self.content))
        tarred = verify_package(ROOT, self.package, self.allowlist)
        self.assertEqual(zipped["members"], tarred["members"])
        self.assertNotEqual(zipped["package_sha256"], tarred["package_sha256"])

    def test_modified_blob_and_unexpected_member_fail_closed(self):
        with ZipFile(self.package, "w") as archive:
            archive.writestr(MEMBER, b"x" + self.content[1:])
        with self.assertRaisesRegex(VerificationError, "bytes differ"):
            verify_package(ROOT, self.package, self.allowlist)
        with ZipFile(self.package, "w") as archive:
            archive.writestr(MEMBER, self.content)
            archive.writestr("config/.pgpass", b"synthetic excluded input")
        with self.assertRaisesRegex(VerificationError, "Disallowed"):
            verify_package(ROOT, self.package, self.allowlist)

    def test_archive_link_and_metadata_are_rejected(self):
        with tarfile.open(self.package, "w") as archive:
            link = tarfile.TarInfo(MEMBER)
            link.type = tarfile.SYMTYPE
            link.linkname = "unserved-target"
            archive.addfile(link)
        with self.assertRaisesRegex(VerificationError, "member type"):
            verify_package(ROOT, self.package, self.allowlist)
        with ZipFile(self.package, "w") as archive:
            archive.writestr(MEMBER, self.content)
            archive.comment = b"unexpected metadata"
        with self.assertRaisesRegex(VerificationError, "ZIP"):
            verify_package(ROOT, self.package, self.allowlist)
