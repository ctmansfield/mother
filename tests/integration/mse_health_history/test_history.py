"""Fabricated archive, paired BP, source custody, and consumer projection tests."""

from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import struct
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZipInfo

from integrations.mse_health_history.catalog import SyntheticHistoryCatalog
from integrations.mse_health_history.files import InvalidHistory
from integrations.mse_health_history.inventory import BP_TYPE, BP_TYPES, Limits
from integrations.mse_health_history.projection import (
    consumer_snapshot,
    synthetic_nightscout_entries,
    write_snapshot,
)
from integrations.mse_health_history.vault import CiphertextVault, Enrollment, utc

OBSERVED = "2026-11-21 10:00:00 +1000"
UTC = "2026-11-21T00:00:00.000000Z"
THROUGH = "2026-11-23T00:00:00.000000Z"
UUIDS = [f"00000000-0000-4000-8000-{n:012d}" for n in range(1, 6)]
SYSTOLIC, DIASTOLIC = BP_TYPES


def record(typ, value, uid=None):
    native = f' uuid="{uid}"' if uid else ""
    return (
        f'<Record type="{typ}" value="{value}" unit="mmHg" '
        f'sourceName="fabricated-source" startDate="{OBSERVED}" endDate="{OBSERVED}"{native}/>'
    )


def correlation(records, uid=None):
    native = f' uuid="{uid}"' if uid else ""
    return (
        f'<Correlation type="{BP_TYPE}" sourceName="fabricated-source" '
        f'startDate="{OBSERVED}" endDate="{OBSERVED}"{native}>{records}</Correlation>'
    )


def xml(body):
    return (
        '<?xml version="1.0" standalone="yes"?>\n'
        "<!DOCTYPE HealthData [<!ELEMENT HealthData (Correlation|Record|Me)*>"
        "<!ELEMENT Record EMPTY>]><HealthData>" + body + "</HealthData>"
    ).encode()


def api_page(
    feed="correlation", prior=None, next_value="a", *, deleted=(), value="124"
):
    def lineage(native):
        return {
            "uuid": native,
            "start": UTC,
            "end": UTC,
            "source_bundle": "example.synthetic.bp",
            "source_version": None,
            "sync_id": None,
            "sync_version": None,
        }

    pair = {
        "lineage": lineage(UUIDS[0]),
        "unexpected_component_ids": [],
        "components": [
            {"lineage": lineage(UUIDS[1]), "feed": "systolic", "mmhg": value},
            {"lineage": lineage(UUIDS[2]), "feed": "diastolic", "mmhg": "81"},
        ],
    }
    return {
        "schema_version": "mse.historical-bp-page/0.1",
        "enrollment": "synthetic-history-test",
        "through": THROUGH,
        "feed": feed,
        "prior_cursor_sha256": prior,
        "next_cursor_sha256": next_value * 64,
        "upserts": [pair] if feed == "correlation" and not deleted else [],
        "deleted_ids": list(deleted),
        "exhausted": feed != "correlation" and not deleted,
    }


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.state = self.root / "catalog"
        self.state.mkdir(mode=0o700)
        self.catalog = self.open_catalog()
        self.catalog.initialize()

    def open_catalog(self, limits=Limits()):
        return SyntheticHistoryCatalog(
            self.state,
            enrollment="synthetic-history-test",
            key=b"p" * 32,
            limits=limits,
            bp_cutoff=THROUGH,
        )

    def file(self, content, name="source"):
        path = self.root / name
        path.write_bytes(content)
        return path

    def test_streamed_zip_preserves_unmapped_attachments_and_unpaired_records(self):
        pair = record(SYSTOLIC, "124.00") + record(DIASTOLIC, "81")
        body = (
            correlation(pair)
            + correlation(record(SYSTOLIC, "124"))
            + record(DIASTOLIC, "81")
            + record(DIASTOLIC, "81")
            + '<Workout workoutActivityType="synthetic"/>'
            + '<Record type="HKQuantityTypeIdentifierUnsupported" value="9"/>'
        )
        path = self.root / "export.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("apple_health_export/export.xml", xml(body))
            archive.writestr(
                "apple_health_export/workout-routes/a.gpx", b"fabricated attachment"
            )
        original = path.read_bytes()
        receipt = self.catalog.ingest(path)
        reopened = self.open_catalog()
        self.assertEqual(reopened.ingest(path), receipt)
        self.assertEqual(reopened.receipt(receipt["sha256"]), receipt)
        self.assertEqual(receipt["observed_top_level_rows"], 6)
        self.assertEqual(receipt["normalized_bp_top_level_rows"], 4)
        self.assertEqual(receipt["unnormalized_top_level_rows"], 2)
        self.assertEqual(receipt["attachment_members_retained_unnormalized"], 1)
        self.assertEqual(
            receipt["bp_pairing_counts"],
            {
                "paired": 1,
                "incomplete": 1,
                "unpaired": 2,
                "ambiguous": 0,
            },
        )
        self.assertEqual(
            (self.catalog.objects / receipt["sha256"]).read_bytes(), original
        )
        members = reopened.members(receipt["sha256"])
        self.assertEqual(
            members[1]["sha256"], sha256(b"fabricated attachment").hexdigest()
        )
        coverage = reopened.coverage(receipt["sha256"])
        self.assertEqual(sum(row["observed"] for row in coverage), 6)
        facts = list(reopened.blood_pressure())
        unpaired = [fact["identity"] for fact in facts if fact["pairing"] == "unpaired"]
        self.assertEqual(len(set(unpaired)), 2)
        original_pair = next(fact for fact in facts if fact["pairing"] == "paired")
        upper = next(
            item for item in original_pair["components"] if item["role"] == "systolic"
        )
        self.assertEqual((upper["original_decimal"], upper["value"]), ("124.00", "124"))
        self.assertEqual(upper["clocks"]["source_start"], OBSERVED)

    def test_path_escape_confusable_names_symlink_and_entities_are_refused(self):
        for name, reason in (
            ("../escape", "unsafe ZIP"),
            ("/absolute", "unsafe ZIP"),
            ("root/a", "duplicate"),
            ("root/link", "encoding"),
        ):
            with self.subTest(name=name):
                path = self.root / "unsafe.zip"
                with ZipFile(path, "w") as archive:
                    info = ZipInfo(name)
                    if name == "root/link":
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, b"x")
                    if name == "root/a":
                        archive.writestr("ROOT/A", b"duplicate")
                with self.assertRaisesRegex(InvalidHistory, reason):
                    self.catalog.ingest(path)
        for doctype in (
            '<!DOCTYPE HealthData SYSTEM "file:///private/example">',
            '<!DOCTYPE HealthData [<!ENTITY x SYSTEM "file:///private/example">]>',
        ):
            with self.assertRaisesRegex(InvalidHistory, "XML declaration"):
                self.catalog.ingest(self.file((doctype + "<HealthData/>").encode()))
        self.assertEqual(list(self.catalog.objects.iterdir()), [])

    def test_zip_central_entry_cannot_point_outside_local_header(self):
        path = self.root / "pointer.zip"
        with ZipFile(path, "w") as archive:
            archive.writestr("export.xml", xml(""))
        raw = bytearray(path.read_bytes())
        offset = raw.index(b"PK\x01\x02")
        struct.pack_into("<I", raw, offset + 42, 0x7FFFFFF0)
        path.write_bytes(raw)
        with self.assertRaisesRegex(InvalidHistory, "ZIP structure"):
            self.catalog.ingest(path)
        self.assertFalse(list(self.catalog.objects.iterdir()))

    def test_scan_limits_reject_before_publishing(self):
        cases = (
            (replace(Limits(), xml_depth=2), "depth"),
            (replace(Limits(), top_level_rows=1), "row limit"),
        )
        pair = record(SYSTOLIC, "124") + record(DIASTOLIC, "81")
        for limits, reason in cases:
            with self.assertRaisesRegex(InvalidHistory, reason):
                self.open_catalog(limits).ingest(
                    self.file(xml(correlation(pair) + record(SYSTOLIC, "120")))
                )
        self.assertEqual(list(self.catalog.objects.iterdir()), [])

    def test_native_revision_conflicts_are_retained_without_current_override(self):
        self.catalog.ingest(
            self.file(
                xml(
                    correlation(
                        record(SYSTOLIC, "124") + record(DIASTOLIC, "81"), UUIDS[0]
                    )
                )
            )
        )
        self.catalog.ingest(
            self.file(
                xml(
                    correlation(
                        record(SYSTOLIC, "125") + record(DIASTOLIC, "81"), UUIDS[0]
                    )
                )
            )
        )
        self.assertEqual(len(list(self.catalog.blood_pressure())), 2)
        self.assertEqual(list(self.catalog.blood_pressure(current=True)), [])

    def test_api_cursor_retry_rollback_and_component_tombstone(self):
        def add(page):
            return self.open_catalog().ingest_bp_page(
                self.file(json.dumps(page).encode())
            )

        first = add(api_page())
        self.assertEqual(add(api_page()), first)
        self.assertEqual(first["typed_upserts"], 1)
        self.assertEqual(len(list(self.catalog.blood_pressure(current=True))), 1)
        with self.assertRaisesRegex(InvalidHistory, "cursor"):
            add(api_page(next_value="b"))
        broken = api_page(prior="a" * 64, next_value="b", value="not-decimal")
        with self.assertRaisesRegex(ValueError, "decimal"):
            add(broken)
        self.assertEqual(len(list(self.catalog.blood_pressure(current=True))), 1)
        deletion = add(api_page("systolic", next_value="c", deleted=[UUIDS[1]]))
        self.assertEqual(deletion["typed_tombstones"], 1)
        self.assertEqual(len(list(self.catalog.blood_pressure())), 1)
        self.assertFalse(list(self.catalog.blood_pressure(current=True)))
        terminal = api_page(prior="a" * 64, next_value="a")
        terminal.update(upserts=[], exhausted=True)
        end = add(terminal)
        self.assertEqual(add(terminal), end)
        self.assertEqual(end["status"], "typed_and_cursor_durable")
        self.assertTrue(end["exhausted"])
        with self.assertRaisesRegex(InvalidHistory, "feed already completed"):
            add(api_page(prior="a" * 64, next_value="d"))

    def test_projection_has_purpose_specific_ids_and_no_raw_lineage(self):
        self.catalog.ingest_bp_page(self.file(json.dumps(api_page()).encode()))
        cgms = self.file(
            json.dumps(
                [
                    {
                        "_id": "fabricated-direct-id",
                        "type": "sgv",
                        "dateString": UTC,
                        "sgv": 103,
                        "units": "mg/dL",
                    },
                    {"_id": "bad", "dateString": UTC, "sgv": 104},
                ]
            ).encode(),
            "nightscout.json",
        )
        glucose = synthetic_nightscout_entries(cgms)
        self.assertEqual(glucose["unnormalized"], 1)
        settings = dict(
            consumer_key=b"c" * 32, start=UTC, end=THROUGH, synthetic_glucose=glucose
        )
        mother = consumer_snapshot(
            self.catalog, purpose="mother-bp-cgm-review", **settings
        )
        coach = consumer_snapshot(
            self.catalog, purpose="coach-bp-cgm-review", **settings
        )
        self.assertNotEqual(mother["subject"], coach["subject"])
        self.assertEqual(mother["rows"], coach["rows"])
        self.assertEqual(len(mother["rows"]), 2)
        self.assertEqual(len({row["bucket"] for row in mother["rows"]}), 1)
        for private in (
            "source_ref",
            "native_ref",
            "fabricated-direct-id",
            "source_bundle",
        ):
            self.assertNotIn(private, json.dumps(mother))
        file = self.root / "consumer.sqlite3"
        write_snapshot(mother, file)
        with sqlite3.connect(file.as_uri() + "?mode=ro", uri=True) as read_only:
            self.assertEqual(
                read_only.execute("SELECT COUNT(*) FROM facts").fetchone(), (2,)
            )
            with self.assertRaises(sqlite3.OperationalError):
                read_only.execute("DELETE FROM facts")

    @unittest.skipUnless(
        os.environ.get("MSE_HISTORY_AGE_BIN"), "requires pinned synthetic age tool"
    )
    def test_authenticated_sealed_bp_page_keeps_plaintext_off_disk(self):
        age = Path(os.environ["MSE_HISTORY_AGE_BIN"]).resolve()
        keygen = age.with_name("age-keygen")
        identity = self.root / "key"
        subprocess.run([keygen, "-pq", "-o", identity], check=True, capture_output=True)
        recipient = subprocess.check_output([keygen, "-y", identity]).strip()
        pin = sha256(recipient).hexdigest()
        page = json.dumps(api_page()).encode()
        cipher = self.root / "cipher.age"
        cipher.touch(mode=0o600)
        with cipher.open("wb") as stream:
            subprocess.run(
                [age, "-e", "-r", recipient],
                input=page,
                stdout=stream,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        cipher_bytes = cipher.read_bytes()
        vault_root = self.root / "vault"
        vault_root.mkdir(mode=0o700)
        enrollment = Enrollment(
            "synthetic-vault",
            "synthetic-import",
            pin,
            sha256(cipher_bytes).hexdigest(),
            len(cipher_bytes),
            THROUGH,
            12 * 1024**3,
            16 * 1024**3,
            True,
        )
        vault = CiphertextVault(vault_root, enrollment, clock=lambda: utc(UTC))
        vault.initialize()
        raw_receipt = vault.put(
            0, len(cipher_bytes), cipher_bytes, enrollment.expected_sha256
        )
        inputs = dict(
            ciphertext=cipher,
            vault_receipt=raw_receipt,
            recipient_fingerprint=pin,
            plaintext_sha256=sha256(page).hexdigest(),
            plaintext_length=len(page),
            age_executable=age,
            age_sha256=sha256(age.read_bytes()).hexdigest(),
            identity_file=identity,
        )
        with self.assertRaisesRegex(ValueError, "plaintext pin"):
            self.catalog.ingest_sealed_bp_page(
                **(inputs | {"plaintext_sha256": "0" * 64})
            )
        wrong = self.root / "wrong"
        subprocess.run([keygen, "-pq", "-o", wrong], check=True, capture_output=True)
        with self.assertRaisesRegex(ValueError, "authentication"):
            self.catalog.ingest_sealed_bp_page(**(inputs | {"identity_file": wrong}))
        receipt = self.catalog.ingest_sealed_bp_page(**inputs)
        self.assertEqual(receipt["ciphertext_receipt"], raw_receipt)
        self.assertEqual(receipt["typed_upserts"], 1)
        self.assertEqual(self.open_catalog().ingest_sealed_bp_page(**inputs), receipt)
        self.assertEqual(self.open_catalog().receipt(receipt["sha256"]), receipt)
        self.assertFalse(list(self.catalog.objects.iterdir()))
