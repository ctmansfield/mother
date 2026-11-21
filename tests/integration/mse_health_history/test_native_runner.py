"""Fabricated native ZIP import and bounded streaming qualification."""

from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from hashlib import sha256
import errno
import hmac
from io import BytesIO, StringIO
import json
import os
import plistlib
from pathlib import Path
import sqlite3
from struct import pack_into, unpack_from
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

from test_native_universal import verify_universal_transfer
from test_typed_vm_support import (
    verify_admitted_guest,
    verify_projection_window,
    verify_shared_vector,
)

from mother.physiology.contracts import canonical_json

from integrations.mse_health_history import native_custodian, native_status
from integrations.mse_health_history.blood_pressure import protected_ref
from integrations.mse_health_history.catalog import (
    SyntheticHistoryCatalog,
    _HistoryCatalog,
)
from integrations.mse_health_history.files import (
    InvalidHistory,
    LimitKind,
    NamedHistoryLimit,
)
from integrations.mse_health_history.inventory import (
    BP_TYPE,
    DEFAULT_ZIP_MEMBERS,
    MAX_ZIP_MEMBERS,
    Limits,
    scan,
)
from integrations.mse_health_history.native_zip_metadata import zip_metadata
from integrations.mse_health_history.vault import CiphertextVault, Enrollment, utc


class NativeRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

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

    def test_named_archive_and_xml_limits_remain_distinct(self):
        plain = (
            b'<HealthData><Record marker="'
            + b"x" * 200
            + b'"><Child/></Record><Record/></HealthData>'
        )
        zipper = BytesIO()
        with ZipFile(zipper, "w", ZIP_DEFLATED) as archive:
            archive.writestr("export.xml", plain)
            archive.writestr("synthetic.txt", b"z" * 2048)
        packed = zipper.getvalue()
        cases = (
            (plain, Limits(archive_bytes=16), "ARCHIVE_BYTES_LIMIT"),
            (plain, Limits(xml_depth=2), "XML_DEPTH_LIMIT"),
            (plain, Limits(xml_token_bytes=64), "XML_TOKEN_LIMIT"),
            (plain, Limits(top_level_rows=1), "XML_ROW_LIMIT"),
            (packed, Limits(members=1), "ZIP_MEMBER_COUNT_LIMIT"),
            (packed, Limits(member_bytes=1000), "ZIP_MEMBER_BYTES_LIMIT"),
            (packed, Limits(ratio=8), "ZIP_RATIO_LIMIT"),
            (packed, Limits(expanded_bytes=1024), "ZIP_EXPANDED_BYTES_LIMIT"),
        )
        for raw, limits, expected in cases:
            with (
                self.subTest(expected=expected),
                self.assertRaises(NamedHistoryLimit) as refused,
            ):
                scan(BytesIO(raw), limits, lambda *_: None, lambda *_: None)
            self.assertEqual(
                native_custodian.diagnostic_category(
                    refused.exception, "ARCHIVE_OR_XML"
                ),
                expected,
            )

    def test_large_native_layout_keeps_directory_and_attachment_accounting(self):
        source = self.root / "fabricated-large.zip"
        route_count = DEFAULT_ZIP_MEMBERS - 2
        with ZipFile(source, "w", ZIP_DEFLATED) as archive:
            archive.writestr("apple_health_export/", "")
            archive.writestr("apple_health_export/workout-routes/", "")
            archive.writestr("apple_health_export/electrocardiograms/", "")
            archive.writestr(
                "apple_health_export/export.xml",
                xml(correlation(record(SYSTOLIC, "124") + record(DIASTOLIC, "81"))),
            )
            for number in range(route_count):
                archive.writestr(
                    f"apple_health_export/workout-routes/route-{number:05d}.gpx",
                    f"<gpx>{number}</gpx>",
                )
            archive.writestr(
                "apple_health_export/electrocardiograms/sample.csv", "synthetic"
            )
        source.chmod(0o600)
        count, directory_bytes = zip_metadata(source)
        self.assertEqual(count, route_count + 5)
        self.assertGreater(count, DEFAULT_ZIP_MEMBERS)
        self.assertLess(directory_bytes, Limits().directory_bytes)

        with (
            source.open("rb") as stream,
            self.assertRaises(NamedHistoryLimit) as refused,
        ):
            scan(stream, Limits(), lambda *_: None, lambda *_: None)
        self.assertIs(refused.exception.kind, LimitKind.ZIP_MEMBERS)
        with (
            source.open("rb") as stream,
            self.assertRaises(NamedHistoryLimit) as refused,
        ):
            scan(
                stream,
                Limits(members=count, expanded_bytes=1024),
                lambda *_: None,
                lambda *_: None,
            )
        self.assertIs(refused.exception.kind, LimitKind.ZIP_EXPANDED)

        dest = self.root / "large-catalog"
        dest.mkdir(mode=0o700)
        catalog = SyntheticHistoryCatalog(
            dest,
            enrollment="synthetic-large-directory",
            key=b"f" * 32,
            limits=Limits(members=count),
        )
        catalog.initialize()
        receipt = catalog.ingest(source)
        members = catalog.members(receipt["sha256"])
        self.assertEqual(len(members), count)
        self.assertEqual(
            receipt["attachment_members_retained_unnormalized"], route_count + 1
        )
        self.assertEqual(receipt["healthdata_xml_members"], 1)
        self.assertEqual(receipt["bp_pairing_counts"]["paired"], 1)
        selected = next(
            row for row in members if row["path"].endswith("route-00000.gpx")
        )
        self.assertEqual(selected["sha256"], sha256(b"<gpx>0</gpx>").hexdigest())

        with ZipFile(source, "a", ZIP_DEFLATED) as archive:
            archive.writestr("../fabricated-escape.gpx", "reject")
        with (
            source.open("rb") as stream,
            self.assertRaisesRegex(InvalidHistory, "unsafe ZIP"),
        ):
            scan(stream, Limits(members=count + 1), lambda *_: None, lambda *_: None)
        with self.assertRaises(ValueError):
            Limits(members=MAX_ZIP_MEMBERS + 1)

    def test_central_directory_is_counted_before_zipfile_materialization(self):
        source = BytesIO()
        with ZipFile(source, "w") as archive:
            archive.writestr("export.xml", xml("<Record/>"))
            archive.writestr("attachment.csv", "synthetic")
        raw = bytearray(source.getvalue())
        offset = raw.rindex(b"PK\x05\x06")
        pack_into("<HH", raw, offset + 8, 1, 1)
        with (
            patch(
                "integrations.mse_health_history.inventory.ZipFile",
                side_effect=AssertionError("materialized"),
            ),
            self.assertRaises(NamedHistoryLimit) as refused,
        ):
            scan(BytesIO(raw), Limits(members=1), lambda *_: None, lambda *_: None)
        self.assertIs(refused.exception.kind, LimitKind.ZIP_MEMBERS)
        with self.assertRaisesRegex(InvalidHistory, "count mismatch"):
            scan(BytesIO(raw), Limits(members=2), lambda *_: None, lambda *_: None)

    def test_zip64_metadata_is_supported_without_opening_members(self):
        source = self.root / "synthetic-zip64.zip"
        with patch("zipfile.ZIP_FILECOUNT_LIMIT", 1), ZipFile(source, "w") as archive:
            archive.writestr("export.xml", xml("<Record/>"))
            archive.writestr("attachment.csv", "synthetic")
        source.chmod(0o600)
        with patch(
            "integrations.mse_health_history.inventory.ZipFile",
            side_effect=AssertionError("opened members"),
        ):
            self.assertEqual(zip_metadata(source)[0], 2)
        ready = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "integrations.mse_health_history.native_zip_metadata",
                str(source),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            set(json.loads(ready.stdout)), {"member_count", "central_directory_bytes"}
        )
        self.assertEqual(ready.stderr, "")
        with source.open("rb") as stream:
            self.assertEqual(
                scan(stream, Limits(), lambda *_: None, lambda *_: None)[1],
                source.stat().st_size,
            )

    def test_actual_sqlite_full_and_file_errors_keep_safe_categories(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE sample (body BLOB)")
            db.execute("PRAGMA max_page_count=2")
            with self.assertRaises(sqlite3.Error) as refused:
                db.execute("INSERT INTO sample VALUES (zeroblob(100000))")
            self.assertEqual(
                native_custodian.diagnostic_category(
                    refused.exception, "ARCHIVE_OR_XML"
                ),
                (
                    "SQLITE_FULL"
                    if hasattr(refused.exception, "sqlite_errorcode")
                    else "CATALOG"
                ),
            )
        for number, expected in (
            (errno.ENOSPC, "FILESYSTEM_FULL"),
            (errno.EDQUOT, "FILESYSTEM_QUOTA"),
            (errno.EFBIG, "FILE_SIZE_LIMIT"),
        ):
            self.assertEqual(
                native_custodian.diagnostic_category(
                    OSError(number, "fabricated private marker"), "CATALOG"
                ),
                expected,
            )
        with self.assertRaises(NamedHistoryLimit) as refused:
            native_custodian.file_limit(None, None)
        self.assertEqual(
            native_custodian.diagnostic_category(refused.exception, "CATALOG"),
            "FILE_SIZE_LIMIT",
        )

    def test_wrapper_sanitizer_only_accepts_exact_complete_output(self):
        expected = b"Protected native import category ARCHIVE_OR_XML\n"
        self.assertEqual(
            native_status.capture_status(1, b"", expected),
            ("REFUSED", "ARCHIVE_OR_XML"),
        )
        self.assertEqual(
            native_status.capture_status(0, native_status.SUCCESS, b""),
            ("RUNNER_REPORTED_SUCCESS", None),
        )
        for stderr in (
            expected + b"Traceback: fabricated-private-member/export.xml\n",
            b"Traceback: fabricated-private-member/export.xml\n" + expected,
            expected + expected,
            b"Protected native import category NOT_ALLOWLISTED\n",
            b"Protected native import category XML_ROW_LIMIT fabricated marker\n",
        ):
            self.assertEqual(
                native_status.capture_status(1, b"", stderr), ("UNCLASSIFIED", None)
            )
        self.assertEqual(
            native_status.capture_status(2, b"", expected), ("UNCLASSIFIED", None)
        )
        self.assertEqual(
            native_status.capture_status(1, b"unexpected stdout", expected),
            ("UNCLASSIFIED", None),
        )
        for kind in LimitKind:
            stderr = (
                native_status.DIAGNOSTIC_PREFIX + kind.value.encode("ascii") + b"\n"
            )
            self.assertEqual(
                native_status.capture_status(1, b"", stderr), ("REFUSED", kind.value)
            )

    def test_reviewed_projection_boundary_and_terminal_vectors(self):
        verify_projection_window(self, self.root)
        verify_shared_vector(self, self.root)

    def test_parent_only_catalog_refuses_fresh_import_before_authentication(self):
        dest = self.root / "legacy-shaped-catalog"
        dest.mkdir(mode=0o700)
        catalog = SyntheticHistoryCatalog(
            dest, enrollment="synthetic-legacy-shape", key=b"q" * 32
        )
        catalog.initialize()
        original = self.root / "legacy-source.xml"
        original.write_bytes(
            xml(correlation(record(SYSTOLIC, "124") + record(DIASTOLIC, "81")))
        )
        receipt = catalog.ingest(original)
        with catalog._connection(write=True) as db:
            db.execute("DROP TABLE native_bp_children")
        with (
            patch(
                "integrations.mse_health_history.catalog.authenticate_export",
                side_effect=AssertionError("authenticated"),
            ),
            self.assertRaisesRegex(InvalidHistory, "requires a fresh catalog"),
        ):
            catalog.ingest_sealed_export(
                plaintext_sha256=receipt["sha256"],
                plaintext_length=receipt["byte_length"],
                receipt={},
            )
        self.assertEqual(catalog.receipt(receipt["sha256"]), receipt)
        self.assertEqual(
            len(list(catalog.blood_pressure_lineage(receipt["sha256"]))), 1
        )

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
                    correlation(
                        record(DIASTOLIC, "81")
                        + '<MetadataEntry key="test" value="intervening"/>'
                        + record(SYSTOLIC, "124.50")
                    )
                    + record(SYSTOLIC, "120")
                    + '<Workout><WorkoutRoute><FileReference path="../opaque.gpx"/></WorkoutRoute></Workout>'
                    + '<Record type="HKClinicalTypeIdentifierLabResultRecord"/>'
                    + "<MedicationRecord/>"
                    + '<Record type="HKQuantityTypeIdentifierStepCount" value="9" unit="count" '
                    'startDate="2026-11-21 10:00:00 +1000" endDate="2026-11-21 10:00:00 +1000"/>'
                    + '<Record type="HKQuantityTypeIdentifierStepCount" value="10" unit="count" '
                    'startDate="2026-11-21 10:00:00 +1000" endDate="2026-11-21 10:00:00 +1000"/>'
                    + '<Record type="HKCategoryTypeIdentifierSleepAnalysis" value="FabricatedState"/>'
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
        self.assertEqual(first["unnormalized_top_level_rows"], 6)
        self.assertFalse(list((typed / "originals").iterdir()))
        self.assertFalse(list(scratch.iterdir()))
        typed_catalog = SyntheticHistoryCatalog(
            typed, enrollment="synthetic-history-test", key=b"k" * 32
        )
        bound = typed_catalog.receipt(value["plaintext_sha256"])
        self.assertEqual(bound["ciphertext_receipt"], receipt)
        self.assertEqual(
            dict(
                typed_catalog.blood_pressure_component_lineage(
                    value["plaintext_sha256"], 1, 1
                )
            ),
            {1: "diastolic", 3: "systolic"},
        )
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

        verify_universal_transfer(
            self,
            self.root / "source-transfer",
            typed_catalog,
            value["plaintext_sha256"],
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

        def run(
            signature, *, selected=policy, diagnostic=False, **filesystem_overrides
        ):
            admission.write_text(
                json.dumps(dict(policy=selected, hmac_sha256=signature))
            )
            stderr, stdout = StringIO(), StringIO()
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
                        *(["--diagnostic-category"] if diagnostic else []),
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
                redirect_stderr(stderr),
                redirect_stdout(stdout),
            )
            with ExitStack() as stack:
                for context in contexts:
                    stack.enter_context(context)
                status = native_custodian.main()
            return status, stderr.getvalue()

        self.assertEqual(
            run("0" * 64),
            (
                1,
                "Protected native import refused or requires receipt reconciliation\n",
            ),
        )
        self.assertEqual(run(sign(policy), EncryptionThisVolumeProper=False)[0], 1)
        self.assertFalse(list(catalog.iterdir()))

        for member_cap in (MAX_ZIP_MEMBERS + 1, False):
            selected = dict(policy, max_zip_members=member_cap)
            self.assertEqual(
                run(sign(selected), selected=selected, diagnostic=True),
                (1, "Protected native import category ADMISSION\n"),
            )
        unsigned_change = dict(policy, max_zip_members=MAX_ZIP_MEMBERS)
        self.assertEqual(
            run(sign(policy), selected=unsigned_change, diagnostic=True),
            (1, "Protected native import category ADMISSION\n"),
        )
        self.assertFalse(list(catalog.iterdir()))

        recipient = subprocess.check_output(
            [age.with_name("age-keygen"), "-y", identity]
        ).strip()

        def bind_fixture(raw, name):
            encrypted = subprocess.check_output([age, "-e", "-r", recipient], input=raw)
            fixture = self.root / name
            fixture.touch(mode=0o600)
            fixture.write_bytes(encrypted)
            exact_receipt = dict(
                binding["receipt"],
                ciphertext_sha256=sha256(encrypted).hexdigest(),
                byte_length=len(encrypted),
            )
            exact_receipt.pop("receipt_id")
            exact_receipt["receipt_id"] = sha256(
                canonical_json(exact_receipt).encode()
            ).hexdigest()
            return dict(
                policy,
                ciphertext=str(fixture),
                binding=dict(
                    binding,
                    receipt=exact_receipt,
                    plaintext_sha256=sha256(raw).hexdigest(),
                    plaintext_length=len(raw),
                ),
            )

        parser_case = bind_fixture(
            b"<HealthData><fabricated-private-marker></HealthData>",
            "synthetic-parser-refusal.age",
        )
        packed = BytesIO()
        with ZipFile(packed, "w", ZIP_DEFLATED) as archive:
            archive.writestr("fabricated-private-member/export.xml", xml("<Record/>"))
        damaged = bytearray(packed.getvalue())
        name_size, extra_size = unpack_from("<HH", damaged, 26)
        first_compressed_byte = 30 + name_size + extra_size
        # Reserved DEFLATE block type. The ZIP directory and admitted ciphertext
        # stay well formed so refusal happens inside the decompressor.
        damaged[first_compressed_byte] = 0b111
        damaged_case = bind_fixture(bytes(damaged), "synthetic-damaged-stream.age")
        wrong_key = self.root / "synthetic-wrong-identity"
        subprocess.run(
            [age.with_name("age-keygen"), "-pq", "-o", wrong_key],
            check=True,
            capture_output=True,
        )
        cases = (
            (
                "BINDING",
                dict(policy, binding=dict(binding, plaintext_sha256="0" * 64)),
                nullcontext(),
            ),
            (
                "AUTHENTICATION",
                dict(policy, identity_file=str(wrong_key)),
                nullcontext(),
            ),
            ("ARCHIVE_OR_XML", parser_case, nullcontext()),
            ("ARCHIVE_OR_XML", damaged_case, nullcontext()),
            ("XML_ROW_LIMIT", dict(policy, max_top_level_rows=1), nullcontext()),
            ("ZIP_MEMBER_COUNT_LIMIT", dict(policy, max_zip_members=1), nullcontext()),
            (
                "PRECOMMIT_WINDOW",
                policy,
                patch.object(
                    native_custodian,
                    "lease",
                    side_effect=[None, ValueError("fabricated private marker")],
                ),
            ),
            (
                "FILESYSTEM_RESERVE_LIMIT",
                policy,
                patch.object(
                    native_custodian,
                    "ensure_space",
                    side_effect=[
                        None,
                        NamedHistoryLimit(
                            LimitKind.FILESYSTEM_RESERVE,
                            "fabricated private resource marker",
                        ),
                    ],
                ),
            ),
        )
        for category, selected, injected in cases:
            with self.subTest(category=category), injected:
                self.assertEqual(
                    run(sign(selected), selected=selected, diagnostic=True),
                    (1, f"Protected native import category {category}\n"),
                )
                with sqlite3.connect(
                    (catalog / "history.sqlite3").as_uri() + "?mode=ro", uri=True
                ) as db:
                    for table in ("artifacts", "members", "sightings", "bp_revisions"):
                        self.assertEqual(
                            db.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,)
                        )
                self.assertFalse((catalog / "history.sqlite3-journal").exists())
                self.assertFalse(list(scratch.iterdir()))

        large_fixture = BytesIO()
        attachment_count = 24_675 - 3
        with ZipFile(large_fixture, "w", ZIP_DEFLATED) as archive:
            archive.writestr("apple_health_export/", "")
            archive.writestr("apple_health_export/workout-routes/", "")
            archive.writestr("apple_health_export/export.xml", xml("<Record/>"))
            for number in range(attachment_count):
                archive.writestr(
                    f"apple_health_export/workout-routes/{number:05d}.gpx", "synthetic"
                )
        large_policy = bind_fixture(
            large_fixture.getvalue(), "synthetic-large-directory.age"
        )
        self.assertEqual(
            run(sign(large_policy), selected=large_policy, diagnostic=True),
            (1, "Protected native import category ZIP_MEMBER_COUNT_LIMIT\n"),
        )
        with sqlite3.connect(
            (catalog / "history.sqlite3").as_uri() + "?mode=ro", uri=True
        ) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM artifacts").fetchone(), (0,)
            )
        universal_output = self.root / "synthetic-universal-ready"
        larger_admission = dict(
            large_policy,
            max_zip_members=attachment_count + 3,
            universal_transfer=dict(
                output=str(universal_output),
                import_ref="synthetic-universal-large",
                max_bytes=32 * 1024**2,
            ),
        )
        self.assertEqual(
            run(sign(larger_admission), selected=larger_admission), (0, "")
        )

        child_key = self.root / "fabricated-mapping-key"
        child_key.touch(mode=0o600)
        child_key.write_bytes(b"m" * 32)
        projected = self.root / "protected-projection"
        projection = {
            "scope": {
                "store_id": "fabricated-admitted-guest",
                "enrollment_id": policy["enrollment"],
                "source_namespace_ref": protected_ref(
                    b"m" * 32,
                    "native-namespace",
                    policy["enrollment"],
                    policy["source_instance"],
                ),
                "import_ref": "fabricated-exact-import",
                "normalization_version": "native-bp-0_1",
            },
            "bounds": [UTC, THROUGH],
            "mapping_key_file": str(child_key),
            "output": str(projected),
            "max_batches": 4,
            "max_bytes": 1024**2,
        }
        selected = dict(policy, max_zip_members=2, projection=projection)
        self.assertEqual(run(sign(selected), selected=selected), (0, ""))
        ledger = json.loads((projected / "private-accounting.json").read_bytes())
        self.assertEqual(ledger["accounting"]["emitted_upsert_count"], 2)
        self.assertEqual(len(ledger["batches"]), 2)
        for batch in ledger["batches"]:
            path = projected / "batches" / batch["file"]
            self.assertEqual(sha256(path.read_bytes()).hexdigest(), batch["sha256"])
        self.assertTrue(
            json.loads((projected / "batches" / "0002.json").read_bytes())["final"]
        )
        self.assertEqual(run(sign(policy)), (0, ""))
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
        wire_manifest = json.loads(
            (universal_output / "private-manifest.json").read_bytes()
        )
        wire = (universal_output / "exact-source.frames").read_bytes()
        self.assertEqual(wire_manifest["wire_sha256"], sha256(wire).hexdigest())
        self.assertEqual(wire_manifest["wire_bytes"], len(wire))
        self.assertEqual(wire_manifest["inventory"]["source_occurrences"], 1)
        larger_receipt = reopened.receipt(large_policy["binding"]["plaintext_sha256"])
        self.assertEqual(larger_receipt["members"], attachment_count + 3)
        self.assertEqual(
            larger_receipt["attachment_members_retained_unnormalized"], attachment_count
        )
        self.assertFalse(list(scratch.iterdir()))
        self.assertFalse(list(reopened.objects.iterdir()))
        verify_admitted_guest(
            self,
            self.root / "admitted-loopback",
            reopened,
            binding["plaintext_sha256"],
            UTC,
            THROUGH,
            tuple(
                (projected / "batches" / name).read_bytes()
                for name in ("0001.json", "0002.json")
            ),
        )
