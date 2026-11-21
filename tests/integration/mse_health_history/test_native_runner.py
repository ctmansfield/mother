"""Fabricated native ZIP import and bounded streaming qualification."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from hashlib import sha256
import hmac
from io import BytesIO, StringIO
import json
import os
import plistlib
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import tracemalloc
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from test_history import (
    DIASTOLIC,
    SYSTOLIC,
    THROUGH,
    UTC,
    UUIDS,
    api_page,
    correlation,
    record,
    xml,
)

from test_typed_vm_support import verify_guest, verify_shared_vector

from mother.physiology.contracts import canonical_json

from integrations.mse_health_history import native_custodian
from integrations.mse_health_history.catalog import (
    SyntheticHistoryCatalog,
    _HistoryCatalog,
)
from integrations.mse_health_history.files import InvalidHistory
from integrations.mse_health_history.inventory import BP_TYPE, Limits, scan
from integrations.mse_health_history.vault import CiphertextVault, Enrollment, utc


class NativeRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_shared_three_operation_terminal_vector(self):
        verify_shared_vector(self, self.root)

    def test_inline_dtd_cannot_supply_native_row_types(self):
        def document(declarations):
            return BytesIO(
                f"<!DOCTYPE HealthData [{declarations}]>"
                "<HealthData><Correlation/></HealthData>".encode()
            )

        def collect(declarations, limits=Limits()):
            rows = []
            scan(
                document(declarations),
                limits,
                lambda *row: rows.append(row),
                lambda *_: None,
            )
            return rows

        grammar = (
            "<!ELEMENT HealthData (Correlation*)><!ELEMENT Correlation EMPTY>"
            "<!ATTLIST Correlation type CDATA #IMPLIED>"
        )
        self.assertEqual(collect(grammar)[0][3], "")
        refusals = (
            (f'<!ATTLIST Correlation type CDATA "{BP_TYPE}">', Limits()),
            (f'<!ATTLIST Correlation type CDATA #FIXED "{BP_TYPE}">', Limits()),
            ('<!ENTITY injected "source">', Limits()),
            ('<!ENTITY % injected "source">', Limits()),
            ("<!--" + "x" * (192 * 1024) + "-->", Limits()),
        )
        for declaration, limits in refusals:
            with (
                self.subTest(declaration=declaration[:40]),
                self.assertRaises(InvalidHistory),
            ):
                collect(declaration, limits)

    def test_large_stream_inventory_does_not_retain_xml_or_nested_elements(self):
        count = 80_000
        path = self.root / "large.zip"
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            with archive.open("export.xml", "w") as source:
                source.write(b"<HealthData>")
                for n in range(count):
                    marker = sha256(str(n).encode()).hexdigest()
                    source.write(
                        (
                            f'<Workout uuid="{marker}"><WorkoutStatistics type="synthetic"/>'
                            f'<WorkoutRoute><FileReference path="never-open-{n}.gpx"/></WorkoutRoute>'
                            "</Workout>"
                        ).encode()
                    )
                source.write(b"</HealthData>")
        totals = {"rows": 0, "nested": 0, "attachments": 0}

        def row(*_):
            totals["rows"] += 1

        def member(*_):
            totals["attachments"] += 1

        def nested(*_):
            totals["nested"] += 1

        tracemalloc.start()
        try:
            with path.open("rb") as source:
                result = scan(source, Limits(), row, member, nested)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result[1], path.stat().st_size)
        self.assertEqual(totals, {"rows": count, "nested": count * 3, "attachments": 1})
        self.assertLess(peak, 8 * 1024**2)

    def test_pinned_api_deletion_reconciles_explicit_native_component_only(self):
        dest = self.root / "typed"
        dest.mkdir(mode=0o700)
        catalog = SyntheticHistoryCatalog(
            dest, enrollment="synthetic-history-test", key=b"a" * 32, bp_cutoff=THROUGH
        )
        catalog.initialize()
        original = self.root / "export.xml"
        original.write_bytes(
            xml(
                correlation(
                    record(SYSTOLIC, "124", UUIDS[1])
                    + record(DIASTOLIC, "81", UUIDS[2]),
                    UUIDS[0],
                )
                + correlation(record(SYSTOLIC, "124") + record(DIASTOLIC, "81"))
            )
        )
        receipt = catalog.ingest(original)
        self.assertEqual(
            [r["ordinal"] for r in catalog.blood_pressure_lineage(receipt["sha256"])],
            [1, 2],
        )
        self.assertEqual(len(list(catalog.blood_pressure(current=True))), 2)
        tombstone = self.root / "native-page.json"
        tombstone.write_text(json.dumps(api_page("systolic", deleted=[UUIDS[1]])))
        catalog.ingest_bp_page(tombstone)
        self.assertEqual(len(list(catalog.blood_pressure())), 2)
        current = list(catalog.blood_pressure(current=True))
        self.assertEqual(len(current), 1)
        self.assertIsNone(current[0]["native_ref"])

    @unittest.skipUnless(
        os.environ.get("MSE_HISTORY_AGE_BIN"), "requires pinned synthetic age tool"
    )
    def test_authenticated_zip_runner_reopens_typed_db_and_consumer_snapshot(self):
        age = Path(os.environ["MSE_HISTORY_AGE_BIN"]).resolve()
        identity = self.root / "detached"
        subprocess.run(
            [age.with_name("age-keygen"), "-pq", "-o", identity],
            check=True,
            capture_output=True,
        )
        recipient = subprocess.check_output(
            [age.with_name("age-keygen"), "-y", identity]
        ).strip()
        pin = sha256(recipient).hexdigest()
        original = self.root / "export.zip"
        with ZipFile(original, "w") as archive:
            archive.writestr(
                "apple_health_export/export.xml",
                xml(
                    correlation(record(SYSTOLIC, "124.50") + record(DIASTOLIC, "81"))
                    + record(SYSTOLIC, "120")
                    + '<Workout><WorkoutRoute><FileReference path="../opaque.gpx"/></WorkoutRoute></Workout>'
                    + '<Record type="HKClinicalTypeIdentifierLabResultRecord"/>'
                    + "<MedicationRecord/>"
                ),
            )
            archive.writestr("opaque.gpx", b"fabricated route attachment")
        raw = original.read_bytes()
        cipher = self.root / "cipher.age"
        cipher.touch(mode=0o600)
        with cipher.open("wb") as stream:
            subprocess.run(
                [age, "-e", "-r", recipient],
                input=raw,
                stdout=stream,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        encrypted = cipher.read_bytes()
        vault_root = self.root / "vault"
        vault_root.mkdir(mode=0o700)
        enrollment = Enrollment(
            "synthetic-vault",
            "synthetic-import",
            pin,
            sha256(encrypted).hexdigest(),
            len(encrypted),
            THROUGH,
            12 * 1024**3,
            16 * 1024**3,
            True,
        )
        vault = CiphertextVault(vault_root, enrollment, clock=lambda: utc(UTC))
        vault.initialize()
        receipt = vault.put(0, len(encrypted), encrypted, enrollment.expected_sha256)
        typed, scratch = self.root / "typed", self.root / "scratch"
        typed.mkdir(mode=0o700)
        scratch.mkdir(mode=0o700)
        pkey, ckey = self.root / "provenance", self.root / "consumer"
        for file in (pkey, ckey):
            file.touch(mode=0o600)
            file.write_bytes(b"k" * 32)
        binding = self.root / "binding.json"
        binding.touch(mode=0o600)
        value = dict(
            receipt=receipt,
            recipient_fingerprint=pin,
            plaintext_sha256=sha256(raw).hexdigest(),
            plaintext_length=len(raw),
            age_sha256=sha256(age.read_bytes()).hexdigest(),
        )
        base = [
            sys.executable,
            "-B",
            "-m",
            "integrations.mse_health_history.native_runner",
        ]
        common = [
            "--root",
            str(typed),
            "--enrollment",
            "synthetic-history-test",
            "--provenance-key-file",
            str(pkey),
        ]

        def run(mode, *args, check=True):
            return subprocess.run(
                [*base, mode, *common, *args],
                check=check,
                capture_output=True,
                text=True,
            )

        run("init")
        import_args = [
            "--custodian-binding",
            str(binding),
            "--ciphertext",
            str(cipher),
            "--age-executable",
            str(age),
            "--identity-file",
            str(identity),
            "--scratch-root",
            str(scratch),
        ]
        binding.write_text(json.dumps(dict(value, plaintext_sha256="0" * 64)))
        self.assertEqual(run("import", *import_args, check=False).returncode, 1)
        binding.write_text(json.dumps(value))
        first = json.loads(run("import", *import_args).stdout)
        self.assertEqual(first, json.loads(run("import", *import_args).stdout))
        self.assertEqual(first["normalized_bp_rows"], 2)
        self.assertEqual(first["unnormalized_top_level_rows"], 3)
        self.assertFalse(list((typed / "originals").iterdir()))
        self.assertFalse(list(scratch.iterdir()))
        typed_catalog = SyntheticHistoryCatalog(
            typed, enrollment="synthetic-history-test", key=b"k" * 32
        )
        bound = typed_catalog.receipt(value["plaintext_sha256"])
        self.assertEqual(bound["ciphertext_receipt"], receipt)
        self.assertTrue(
            any(
                row["family"] == "attachment_reference"
                for row in bound["nested_occurrences"]
            )
        )
        output = self.root / "projection.db"
        run(
            "snapshot",
            "--purpose",
            "mother-bp-cgm-review",
            "--consumer-key-file",
            str(ckey),
            "--start",
            UTC,
            "--end",
            THROUGH,
            "--output",
            str(output),
        )
        with sqlite3.connect(output.as_uri() + "?mode=ro", uri=True) as conn:
            body = json.loads(conn.execute("SELECT body FROM facts").fetchone()[0])
            self.assertEqual(body["systolic"], "124.5")
            self.assertNotIn("source_ref", body)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM facts")

        verify_guest(
            self,
            self.root,
            typed_catalog,
            value["plaintext_sha256"],
            bound["receipt_id"],
            UTC,
            THROUGH,
        )
        self.verify_protected_admission(value, cipher, identity, age, pkey, scratch)

    def verify_protected_admission(self, binding, cipher, identity, age, pkey, scratch):
        catalog = self.root / "protected-typed"
        catalog.mkdir(mode=0o700)
        approval = self.root / "authority-key"
        approval.touch(mode=0o600)
        approval.write_bytes(b"a" * 32)
        admission = self.root / "admission"
        admission.touch(mode=0o600)
        policy = dict(
            mode="protected-native-import",
            archive_id="admitted-archive",
            enrollment="admitted-enrollment",
            source_instance="admitted-source",
            allowed_at="2020-01-01T00:00:00.000000Z",
            expires_at="2040-01-01T00:00:00.000000Z",
            volume_uuid="fabricated-volume",
            mount=str(self.root),
            catalog=str(catalog),
            scratch=str(scratch),
            ciphertext=str(cipher),
            identity_file=str(identity),
            provenance_key_file=str(pkey),
            age_executable=str(age),
            binding=binding,
            catalog_bytes=64 * 1024**2,
            reserve_bytes=256 * 1024**2,
            runtime_seconds=60,
            max_expanded_bytes=1024**2,
            max_top_level_rows=100,
        )
        filesystem = dict(
            MountPoint=str(self.root),
            FilesystemType="apfs",
            EncryptionThisVolumeProper=True,
            VolumeUUID="fabricated-volume",
        )

        def sign(value):
            return hmac.new(
                b"a" * 32,
                native_custodian.DOMAIN + canonical_json(value).encode(),
                sha256,
            ).hexdigest()

        def run(signature, **filesystem_overrides):
            admission.write_text(json.dumps(dict(policy=policy, hmac_sha256=signature)))
            contexts = (
                patch.object(
                    sys,
                    "argv",
                    [
                        "runner",
                        "--admission",
                        str(admission),
                        "--approval-key",
                        str(approval),
                    ],
                ),
                patch.object(sys, "platform", "darwin"),
                patch.dict(os.environ),
                patch.object(native_custodian.resource, "setrlimit"),
                patch.object(native_custodian.signal, "signal"),
                patch.object(native_custodian.signal, "alarm"),
                patch.object(
                    native_custodian.subprocess,
                    "check_output",
                    return_value=plistlib.dumps(
                        dict(filesystem, **filesystem_overrides)
                    ),
                ),
                redirect_stderr(StringIO()),
                redirect_stdout(StringIO()),
            )
            with ExitStack() as stack:
                for context in contexts:
                    stack.enter_context(context)
                return native_custodian.main()

        self.assertEqual(run("0" * 64), 1)
        self.assertEqual(run(sign(policy), EncryptionThisVolumeProper=False), 1)
        self.assertFalse(list(catalog.iterdir()))
        self.assertEqual(run(sign(policy)), 0)
        self.assertEqual(run(sign(policy)), 0)
        reopened = _HistoryCatalog(
            catalog,
            key=b"k" * 32,
            archive_id=policy["archive_id"],
            enrollment=policy["enrollment"],
            source_instance=policy["source_instance"],
        )
        self.assertEqual(
            reopened.receipt(binding["plaintext_sha256"])["ciphertext_receipt"],
            binding["receipt"],
        )
        self.assertFalse(list(reopened.objects.iterdir()))
