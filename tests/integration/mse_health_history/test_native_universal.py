"""Exact source retrieval with mixed fabricated XML and opaque attachments."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from integrations.mse_health_history.blood_pressure import source_time
from integrations.mse_health_history.catalog import SyntheticHistoryCatalog
from integrations.mse_health_history.files import CHUNK, InvalidHistory


class NativeUniversalTests(unittest.TestCase):
    def test_native_clock_conversion_accepts_basic_offsets_and_variable_fraction(self):
        self.assertEqual(
            source_time("2026-01-01 08:00:00 +1000"),
            "2025-12-31T22:00:00.000000Z",
        )
        self.assertEqual(
            source_time("2026-01-01T08:00:00.1Z"),
            "2026-01-01T08:00:00.100000Z",
        )
        with self.assertRaises(ValueError):
            source_time("2026-01-01T08:00:00+0060")

    def test_exact_members_ordered_fallback_typed_quarantine_and_reopen(self):
        with TemporaryDirectory() as private:
            root = Path(private).resolve()
            state = root / "catalog"
            state.mkdir(mode=0o700)
            original = root / "synthetic.zip"
            xml = b"""<HealthData xmlns:z="urn:synthetic"><!--document comment-->
<Record type="HKQuantityTypeIdentifierStepCount" value="3.00" unit="count" startDate="2026-01-01 00:00:00 +0000"/>
<Record type="HKCategoryTypeIdentifierSleepAnalysis" value="FabricatedState"/>
<Workout workoutActivityType="fabricated" duration="3" durationUnit="min"/>
<ActivitySummary dateComponents="2026-01-01"/>
<Record type="HKQuantityTypeIdentifierUnsupported" value="bad"/>
<z:Future z:key="v">before<z:Child/>between<z:Child><![CDATA[after]]></z:Child></z:Future>
<WorkoutRoute><FileReference path="resources/route.gpx"/></WorkoutRoute>
<ClinicalRecord type="fabricated"><FileReference path="https://example.invalid/blocked"/></ClinicalRecord>
</HealthData>"""
            large = b"synthetic" * (CHUNK // 9 + 7)
            entries = [
                ("export.xml", xml),
                ("resources/", b""),
                (
                    "resources/route.gpx",
                    b"\xfe\xff"
                    + '<gpx xmlns="urn:gpx"><trk><name>synthetic</name></trk></gpx>'.encode(
                        "utf-16-be"
                    ),
                ),
                (
                    "resources/cda.xml",
                    b'<ClinicalDocument xmlns="urn:cda"><component/></ClinicalDocument>',
                ),
                ("resources/one.dat", large),
                ("resources/two.dat", large),
                ("resources/empty.dat", b""),
            ]
            with ZipFile(original, "w") as archive:
                for path, raw in entries:
                    archive.writestr(path, raw)

            def open_catalog():
                return SyntheticHistoryCatalog(
                    state, enrollment="synthetic-all-source", key=b"k" * 32
                )

            catalog = open_catalog()
            catalog.initialize()
            receipt = catalog.ingest(original)
            archive = receipt["sha256"]
            readback = open_catalog()
            self.assertEqual(readback.ingest(original), receipt)
            self.assertEqual(readback.receipt(archive), receipt)
            report = receipt["source_inventory"]
            self.assertEqual(
                report["member_payload_bytes"], sum(len(raw) for _, raw in entries)
            )
            self.assertEqual(report["source_occurrences"], 10)
            self.assertEqual(
                report["typed_occurrences"]
                + report["descriptor_occurrences"]
                + report["fallback_occurrences"]
                + report["quarantined_occurrences"],
                10,
            )
            self.assertEqual(report["quarantined_occurrences"], 1)
            rows = readback.source_occurrences(archive, limit=3)
            self.assertEqual(
                [r["adapter"] for r in rows], ["quantity", "sleep_state", "workout"]
            )
            self.assertEqual(json.loads(rows[0]["typed_json"])["source_value"], "3.00")
            self.assertEqual(json.loads(rows[0]["typed_json"])["value"], "3")
            self.assertEqual(len(readback.source_occurrences(archive, after=(1, 3))), 7)
            self.assertEqual(
                readback.source_occurrences(archive, family="auxiliary_xml")[0][
                    "adapter"
                ],
                "fallback",
            )
            events = readback.source_events(archive, 1, 6)
            self.assertEqual(
                [json.loads(e["data_json"]) for e in events if e["kind"] == "text"],
                ["before", "between", "after"],
            )
            found = [
                r
                for r in readback.source_elements(archive, 1)
                if r["qualified_name"].startswith("z:")
            ]
            self.assertEqual([r["namespace"] for r in found], ["urn:synthetic"] * 3)
            self.assertEqual([r["child_position"] for r in found[1:]], [1, 2])
            self.assertEqual(
                [r["parent"] for r in found[1:]], [found[0]["element"]] * 2
            )
            self.assertEqual(json.loads(found[0]["attributes_json"]), [["z:key", "v"]])

            route = readback.source_elements(archive, 3)
            self.assertEqual(
                [item["qualified_name"] for item in route], ["gpx", "trk", "name"]
            )
            members = readback.members(archive)
            self.assertEqual(members[2]["kind"], "source_xml")
            for row, (path, raw) in zip(members, entries):
                self.assertEqual(row["path"], path)
                self.assertEqual(row["sha256"], sha256(raw).hexdigest())
                if row["kind"] == "directory":
                    with self.assertRaises(KeyError):
                        readback.source_member_range(
                            archive, row["ordinal"], row["sha256"], 0, 0
                        )
                else:
                    self.assertEqual(
                        readback.source_member_range(
                            archive, row["ordinal"], row["sha256"], 0, len(raw)
                        ),
                        raw,
                    )
            self.assertEqual(
                readback.source_member_range(
                    archive, 5, sha256(large).hexdigest(), CHUNK - 3, 12
                ),
                large[CHUNK - 3 : CHUNK + 9],
            )
            with self.assertRaises(KeyError):
                readback.source_member_range(
                    archive, 5, sha256(b"wrong").hexdigest(), 0, 1
                )
            with readback._connection() as db:
                self.assertEqual(
                    db.execute(
                        "SELECT status,target_member FROM native_source_refs ORDER BY status"
                    ).fetchall(),
                    [("blocked", None), ("resolved", 3)],
                )
                self.assertEqual(
                    db.execute(
                        "SELECT count(*) FROM native_source_chunks WHERE sha256=?",
                        (sha256(large[:CHUNK]).hexdigest(),),
                    ).fetchone(),
                    (1,),
                )

    def test_invalid_temporal_dispositions_preserve_exact_source(self):
        from test_history import DIASTOLIC, OBSERVED, SYSTOLIC, correlation, record, xml

        earlier = "2026-11-21 09:59:00 +1000"
        end = f'endDate="{OBSERVED}"'
        reversed_end = f'endDate="{earlier}"'
        pair = record(SYSTOLIC, "125") + record(DIASTOLIC, "81")
        original_xml = xml(
            '<ActivitySummary dateComponents="2026-02-30"/>'
            '<Record type="HKQuantityTypeIdentifierStepCount" value="2" unit="count" '
            'startDate="2026-02-30T10:00:00Z"/>'
            '<Record type="HKQuantityTypeIdentifierStepCount" value="3" unit="count" '
            f'startDate="{OBSERVED}" {reversed_end}/>'
            + correlation(pair).replace(end, reversed_end, 1)
            + correlation(pair.replace(end, reversed_end, 1))
            + correlation(pair)
        )
        with TemporaryDirectory() as private:
            root = Path(private).resolve()
            state = root / "catalog"
            state.mkdir(mode=0o700)
            archive_path = root / "synthetic.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("export.xml", original_xml)
            catalog = SyntheticHistoryCatalog(
                state, enrollment="synthetic-clock-dispositions", key=b"k" * 32
            )
            catalog.initialize()
            artifact = catalog.ingest(archive_path)["sha256"]
            rows = catalog.source_occurrences(artifact)
            self.assertEqual(
                [row["level"] for row in rows], ["quarantine"] * 5 + ["typed"]
            )
            self.assertEqual(
                [json.loads(row["typed_json"])["reason"] for row in rows[:5]],
                [
                    "invalid_activity_date",
                    "invalid_source_clock",
                    "reversed_source_interval",
                    "reversed_source_interval",
                    "reversed_source_interval",
                ],
            )
            self.assertEqual(
                catalog.source_member_range(
                    artifact, 1, sha256(original_xml).hexdigest(), 0, len(original_xml)
                ),
                original_xml,
            )
            self.assertTrue(catalog.source_events(artifact, 1, 5))

    def test_purpose_excludes_legacy_reversed_root_and_component_intervals(self):
        import sqlite3
        from types import SimpleNamespace

        from integrations.mse_health_history.inventory import BP_TYPE
        from integrations.mse_health_history.native_universal_https import (
            UniversalServer,
        )

        begin = "2026-11-21T00:00:00.000000Z"
        instant = "2026-11-21T00:01:00.000000Z"
        end = "2026-11-22T00:00:00.000000Z"
        quantity = "HKQuantityTypeIdentifierStepCount"

        def pressure(start, finish, component_end):
            return dict(
                pairing="paired",
                clocks=dict(event_start=start, event_end=finish),
                components=[
                    dict(
                        role="systolic",
                        value="120",
                        clocks=dict(event_start=instant, event_end=component_end),
                    ),
                    dict(
                        role="diastolic",
                        value="80",
                        clocks=dict(event_start=instant, event_end=instant),
                    ),
                ],
            )

        db = sqlite3.connect(":memory:")
        db.execute(
            "CREATE TABLE native_source_occurrences (artifact,member,ordinal,source_type,adapter,typed)"
        )
        rows = [
            (
                quantity,
                "quantity",
                dict(
                    value="8",
                    source_unit="count",
                    clocks=dict(startDate=dict(utc=instant), endDate=dict(utc=begin)),
                ),
            ),
            (BP_TYPE, "blood_pressure", pressure(instant, begin, instant)),
            (BP_TYPE, "blood_pressure", pressure(instant, instant, begin)),
            (BP_TYPE, "blood_pressure", pressure(instant, instant, instant)),
        ]
        db.executemany(
            "INSERT INTO native_source_occurrences VALUES ('synthetic',1,?,?,?,?)",
            [
                (ordinal, source_type, adapter, json.dumps(body))
                for ordinal, (source_type, adapter, body) in enumerate(rows, 1)
            ],
        )
        server = SimpleNamespace(
            policies={
                "mother": {
                    "subject": "fabricated",
                    "adapters": ["quantity", "blood_pressure"],
                    "types": [quantity, BP_TYPE],
                    "units": ["count"],
                    "states": [],
                    "activities": [],
                    "from": begin,
                    "before": end,
                    "timeless": True,
                    "limit": 1,
                }
            },
            cursor_key=b"k" * 32,
            store=SimpleNamespace(
                connect=lambda: db,
                receipt=lambda: None,
                pin="synthetic",
                manifest={"artifact": "synthetic"},
            ),
        )
        result = json.loads(UniversalServer.features(server, "mother", None))
        self.assertEqual(
            [row["fields"] for row in result["rows"]],
            [
                {"systolic": "120", "diastolic": "80", "unit": "mmHg"},
            ],
        )
        self.assertIsNone(result["next"])

    def test_security_refusal_keeps_no_universal_rows(self):
        with TemporaryDirectory() as private:
            root = Path(private).resolve()
            state = root / "catalog"
            state.mkdir(mode=0o700)
            source = root / "synthetic.zip"
            with ZipFile(source, "w") as archive:
                archive.writestr("first.bin", b"payload")
                archive.writestr(
                    "export.xml",
                    '<!DOCTYPE HealthData [<!ENTITY prohibited "source">]><HealthData/>',
                )
            catalog = SyntheticHistoryCatalog(
                state, enrollment="synthetic-unsafe-source", key=b"k" * 32
            )
            catalog.initialize()
            with self.assertRaises(InvalidHistory):
                catalog.ingest(source)
            with catalog._connection() as db:
                for table in (
                    "artifacts",
                    "native_source_events",
                    "native_source_chunks",
                    "native_source_member_chunks",
                ):
                    self.assertEqual(
                        db.execute(f"SELECT count(*) FROM {table}").fetchone(), (0,)
                    )


def verify_universal_transfer(test, root, catalog, artifact, start, end):
    from hashlib import sha256
    from io import BytesIO

    from integrations.mse_health_history.blood_pressure import source_time
    from integrations.mse_health_history.native_universal_transfer import (
        PART_BYTES,
        UniversalStore,
        export_catalog,
    )
    from integrations.mse_health_history.typed_vm import (
        Conflict,
        Indeterminate,
        encoded,
    )

    root.mkdir(mode=0o700)
    spool = BytesIO()
    manifest = export_catalog(
        catalog, artifact, spool, import_ref="synthetic-universal"
    )
    repeat = BytesIO()
    test.assertEqual(
        export_catalog(catalog, artifact, repeat, import_ref="synthetic-universal"),
        manifest,
    )
    test.assertEqual(spool.getvalue(), repeat.getvalue())
    pin = sha256(encoded(manifest)).hexdigest()
    start, end = source_time(start), source_time(end)
    now = start
    checks = 0
    trip_at = None

    def clock():
        nonlocal checks
        checks += 1
        return end if checks == trip_at else now

    def open_store(name):
        return UniversalStore(
            root / name,
            manifest,
            trusted_manifest_sha256=pin,
            starts=start,
            ends=end,
            clock=clock,
            database_bytes=64 * 1024**2,
        )

    def stage(store, raw=None):
        prior = None
        raw = spool.getvalue() if raw is None else raw
        for i in range(store.manifest["parts"]):
            part = raw[i * PART_BYTES : (i + 1) * PART_BYTES]
            digest = sha256(part).hexdigest()
            test.assertEqual(
                store.put(i + 1, part, predecessor=prior, digest=digest), 201
            )
            test.assertEqual(
                store.put(i + 1, part, predecessor=prior, digest=digest), 200
            )
            prior = digest

    store = open_store("normal.sqlite3")
    store.initialize()
    with test.assertRaises(Conflict):
        store.finish()
    stage(store)
    with test.assertRaises(KeyError):
        store.restricted_occurrences()
    status, acceptance = store.finish()
    test.assertEqual(status, 201)
    test.assertEqual(store.finish(), (200, acceptance))
    reopened = open_store("normal.sqlite3")
    test.assertEqual(reopened.receipt(), acceptance)
    test.assertEqual(
        reopened.restricted_occurrences(), catalog.source_occurrences(artifact)
    )
    attachment = next(
        row for row in reopened.restricted_members() if row["kind"] == "attachment"
    )
    test.assertEqual(attachment["disposition"], "byte_only")
    test.assertEqual(attachment["reason"], "gpx_not_recognized_as_supported_xml")
    for row in catalog.members(artifact):
        if row["kind"] == "directory":
            continue
        length = min(row["byte_length"], 1024**2)
        test.assertEqual(
            reopened.restricted_member_range(row["ordinal"], row["sha256"], 0, length),
            catalog.source_member_range(
                artifact, row["ordinal"], row["sha256"], 0, length
            ),
        )

    late = open_store("late.sqlite3")
    late.initialize()
    stage(late)
    # The fourth check is the first trusted clock reading after staging commits.
    trip_at = checks + 4
    with test.assertRaises(Indeterminate):
        late.finish()
    trip_at = None
    with test.assertRaises(Indeterminate):
        open_store("late.sqlite3").restricted_occurrences()
    with test.assertRaises(Indeterminate):
        open_store("late.sqlite3").finish()

    def invalid_structure(kind):
        frames = [json.loads(line) for line in spool.getvalue().splitlines()]
        if kind == "nested":
            index = next(
                i
                for i, (table, row) in enumerate(frames)
                if table == "native_source_elements" and row[6] == "MetadataEntry"
            )
            frames[index][1][6] = "rebinding"
        elif kind == "top":
            index = next(
                i
                for i, (table, row) in enumerate(frames)
                if table == "native_source_occurrences"
            )
            frames[index][1][3] = "wrong-family"
        else:
            index = next(
                i
                for i, (table, _) in enumerate(frames)
                if table == "native_source_refs"
            )
            del frames[index]
        raw = b"".join(encoded(frame) + b"\n" for frame in frames)
        altered = dict(
            manifest,
            wire_bytes=len(raw),
            wire_sha256=sha256(raw).hexdigest(),
            parts=(len(raw) + PART_BYTES - 1) // PART_BYTES,
        )
        store = UniversalStore(
            root / (kind + ".sqlite3"),
            altered,
            trusted_manifest_sha256=sha256(encoded(altered)).hexdigest(),
            starts=start,
            ends=end,
            clock=clock,
            database_bytes=64 * 1024**2,
        )
        store.initialize()
        stage(store, raw)
        with test.assertRaises(InvalidHistory):
            store.finish()
        with test.assertRaises(KeyError):
            store.receipt()

    for kind in ("nested", "top", "reference"):
        invalid_structure(kind)

    network = open_store("network.sqlite3")
    network.initialize()
    member = next(
        row for row in catalog.members(artifact) if row["kind"] == "attachment"
    )
    fallback = next(
        row
        for row in catalog.source_occurrences(artifact)
        if row["source_type"] == "HKClinicalTypeIdentifierLabResultRecord"
    )
    element = next(
        item
        for item in catalog.source_elements(artifact, fallback["member"])
        if item["occurrence"] == fallback["ordinal"]
    )
    verify_universal_https(
        test,
        root / "tls",
        network,
        spool.getvalue(),
        start,
        end,
        member,
        fallback,
        element,
    )


def verify_universal_https(
    test, root, store, spool, start, end, member, fallback, element
):
    """Use actual hostname-verified mTLS over loopback with fabricated records."""
    from hashlib import sha256
    from http.client import HTTPSConnection
    from ipaddress import IPv4Network
    import ssl
    import subprocess
    from threading import Thread
    from unittest.mock import patch

    from integrations.mse_health_history.blood_pressure import source_time
    from integrations.mse_health_history.native_universal_https import UniversalServer

    root.mkdir(mode=0o700)
    roles = (
        "writer",
        "receipt",
        "source",
        "mother",
        "coach",
        "fallback-grant",
        "attachment-grant",
    )

    def issue(role, extra):
        cert, key = root / (role + ".pem"), root / (role + ".key")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                f"/CN=Fabricated universal {role}",
                "-keyout",
                key,
                "-out",
                cert,
                "-addext",
                extra,
            ],
            check=True,
            capture_output=True,
        )
        key.chmod(0o600)
        return cert, key

    certs = {role: issue(role, "basicConstraints=critical,CA:TRUE") for role in roles}
    server_cert, server_key = issue("server", "subjectAltName=IP:127.0.0.1")
    ca = root / "client-ca.pem"
    ca.write_bytes(b"".join(cert.read_bytes() for cert, _ in certs.values()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(server_cert, server_key)
    context.load_verify_locations(cafile=ca)
    context.verify_mode = ssl.CERT_REQUIRED
    grants = {
        role: (
            sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest(),
            end if role == "writer" else source_time("2030-01-01T00:00:00Z"),
        )
        for role, (cert, _) in certs.items()
    }
    common = {
        "from": start,
        "before": end,
        "activities": [],
        "units": ["count"],
        "states": ["FabricatedState"],
        "timeless": True,
        "limit": 1,
    }
    policies = {
        "mother": dict(
            common,
            subject="fabricated-mother",
            adapters=["quantity"],
            types=["HKQuantityTypeIdentifierStepCount"],
        ),
        "coach": dict(
            common,
            subject="fabricated-coach",
            adapters=["sleep_state"],
            types=["HKCategoryTypeIdentifierSleepAnalysis"],
        ),
    }
    reviewed = {
        "fallback-grant": {
            "purpose": "mother",
            "audience": "fabricated-audience",
            "attachment": None,
            "fallback": {
                "member": fallback["member"],
                "ordinal": fallback["ordinal"],
                "element": element["element"],
                "fields": ["type"],
            },
        },
        "attachment-grant": {
            "purpose": "coach",
            "audience": "fabricated-audience",
            "fallback": None,
            "attachment": {
                "member": member["ordinal"],
                "sha256": member["sha256"],
                "start": 1,
                "before": 5,
                "budget": 4,
            },
        },
    }
    with patch(
        "integrations.mse_health_history.native_universal_https.PRIVATE",
        (IPv4Network("127.0.0.1/32"),),
    ):
        server = UniversalServer(
            ("127.0.0.1", 0),
            store,
            context,
            grants,
            policies,
            check_storage=lambda: None,
            cursor_key=b"c" * 32,
            reviewed=reviewed,
        )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    test.addCleanup(server.server_close)
    test.addCleanup(thread.join, 5)
    test.addCleanup(server.shutdown)

    def request(role, method, path, body=None, **headers):
        ctx = ssl.create_default_context(cafile=server_cert)
        ctx.load_cert_chain(*certs[role])
        client = HTTPSConnection(
            "127.0.0.1", server.server_port, context=ctx, timeout=8
        )
        try:
            client.request(method, server.route + path, body=body, headers=headers)
            response = client.getresponse()
            return response.status, response.read()
        finally:
            client.close()

    test.assertEqual(request("mother", "GET", "/purposes/mother")[0], 404)
    test.assertEqual(request("source", "GET", "/source?member=0&ordinal=0")[0], 404)
    from integrations.mse_health_history.native_universal_client import ManualTransfer
    from integrations.mse_health_history.typed_vm import encoded

    spool_path, manifest_path = (
        root / "synthetic.frames",
        root / "synthetic-manifest.json",
    )
    spool_path.write_bytes(spool)
    manifest_path.write_bytes(encoded(store.manifest))
    spool_path.chmod(0o600)
    manifest_path.chmod(0o600)
    sender = ManualTransfer(
        {
            "host": "127.0.0.1",
            "port": server.server_port,
            "spool": str(spool_path),
            "manifest": str(manifest_path),
            "manifest_sha256": store.pin,
            "guest_ca": str(server_cert),
            "writer": [str(path) for path in certs["writer"]],
            "receipt": [str(path) for path in certs["receipt"]],
        }
    )
    test.assertEqual(request("receipt", "GET", "/receipt")[0], 404)
    test.assertEqual(sender.transfer(), sender.verify_receipt())
    with store.connect() as db:
        member_id, ordinal, nested = db.execute(
            """SELECT member,occurrence,element FROM native_source_elements
               WHERE qualified_name='MetadataEntry'"""
        ).fetchone()
    test.assertEqual(
        json.loads(store.approved_fallback(member_id, ordinal, nested, ["key"])),
        {"fields": {"key": "test"}},
    )
    test.assertEqual(request("receipt", "GET", "/manifest")[0], 200)
    test.assertEqual(request("mother", "GET", "/source/coverage")[0], 403)
    coverage_code, coverage_body = request("source", "GET", "/source/coverage")
    test.assertEqual(coverage_code, 200)
    test.assertIn("descriptor_occurrences", json.loads(coverage_body))
    discovery_code, discovery_body = request(
        "mother", "GET", "/purposes/mother/discovery"
    )
    test.assertEqual(discovery_code, 200)
    test.assertIs(json.loads(discovery_body)["timeless"], True)
    test.assertEqual(
        json.loads(discovery_body)["fields"], {"quantity": ["value", "source_unit"]}
    )
    test.assertEqual(request("coach", "GET", "/purposes/mother/discovery")[0], 403)

    test.assertEqual(request("coach", "GET", "/purposes/mother")[0], 403)
    test.assertEqual(request("mother", "GET", "/source?member=0&ordinal=0")[0], 403)
    test.assertEqual(request("mother", "GET", "/receipt")[0], 403)
    from base64 import urlsafe_b64decode

    status, raw = request("mother", "GET", "/purposes/mother")
    test.assertEqual(status, 200)
    first = json.loads(raw)
    cursor = first["next"]
    test.assertIsInstance(cursor, str)
    decoded = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    test.assertEqual(
        json.loads(decoded[:-32])[1:],
        [first["rows"][0]["event_utc"], first["rows"][0]["ref"]],
    )
    test.assertTrue(all(isinstance(item, str) for item in json.loads(decoded[:-32])))
    status, raw = request("mother", "GET", "/purposes/mother?after=" + cursor)
    test.assertEqual(status, 200)
    second = json.loads(raw)
    test.assertEqual(len(second["rows"]), 1)
    test.assertIsNone(second["next"])
    test.assertEqual(
        {first["rows"][0]["fields"]["value"], second["rows"][0]["fields"]["value"]},
        {"9", "10"},
    )
    test.assertEqual(request("coach", "GET", "/purposes/coach?after=" + cursor)[0], 400)
    changed = ("B" if cursor[0] == "A" else "A") + cursor[1:]
    test.assertEqual(
        request("mother", "GET", "/purposes/mother?after=" + changed)[0], 400
    )
    status, raw = request("coach", "GET", "/purposes/coach")
    test.assertEqual(status, 200)
    test.assertEqual(
        [item["fields"] for item in json.loads(raw)["rows"]],
        [{"source_state": "FabricatedState"}],
    )
    fallback_path = (
        f"/reviewed/fallback-grant/fabricated-audience/fallback/"
        f"{fallback['member']}/{fallback['ordinal']}/{element['element']}"
    )
    test.assertEqual(request("mother", "GET", fallback_path)[0], 403)
    fallback_status, fallback_raw = request("fallback-grant", "GET", fallback_path)
    test.assertEqual(fallback_status, 200)
    test.assertEqual(
        json.loads(fallback_raw), {"fields": {"type": fallback["source_type"]}}
    )
    test.assertEqual(
        request(
            "fallback-grant",
            "GET",
            fallback_path.replace("fabricated-audience", "other-audience"),
        )[0],
        403,
    )
    approved_payload = f"/reviewed/attachment-grant/fabricated-audience/payload/{member['ordinal']}?sha256={member['sha256']}"
    test.assertEqual(
        request("coach", "GET", approved_payload + "&offset=1&length=4")[0], 403
    )
    test.assertEqual(
        request("attachment-grant", "GET", approved_payload + "&offset=0&length=4")[0],
        403,
    )
    granted, chunk = request(
        "attachment-grant", "GET", approved_payload + "&offset=1&length=4"
    )
    test.assertEqual((granted, len(chunk)), (200, 4))
    test.assertEqual(
        request("attachment-grant", "GET", approved_payload + "&offset=1&length=1")[0],
        413,
    )
    suffix = f"/source/{member['ordinal']}/payload?sha256={member['sha256']}&offset=0&length={member['byte_length']}"
    test.assertEqual(request("mother", "GET", suffix)[0], 403)
    status, payload = request("source", "GET", suffix)
    test.assertEqual(status, 200)
    test.assertEqual(sha256(payload).hexdigest(), member["sha256"])
