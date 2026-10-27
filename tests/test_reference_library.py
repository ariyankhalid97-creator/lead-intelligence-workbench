import csv
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import reference_library as library


class ReferenceLibraryTests(unittest.TestCase):
    def source(self, directory):
        source = Path(directory)
        (source / "research").mkdir()
        (source / "outreach").mkdir()
        primary = [
            {
                "Company": "Example Hoods",
                "City": "Dallas",
                "State": "TX",
                "Website": "https://www.example.com/about",
                "Phone": "(214) 555-0100",
                "Email": "Unknown (obfuscated)",
                "DecisionMaker": "Unknown",
                "Role": "Unknown",
                "Score": "7.4",
                "ReportsPhotoWorkflow": "Photo report promised",
                "ExistingSoftware": "None visible",
                "EvidenceOfManualWorkflow": "Likely: not confirmed",
                "SourceURL": "https://example.com/services",
            },
            {
                "Company": "CIMA Hood Cleaning",
                "City": "Tampa",
                "State": "FL",
                "Website": "https://cima.example.com",
                "Phone": "VERIFY (site lists 645-224-2817 — invalid area code)",
                "Email": "info@cima.example.com",
                "DecisionMaker": "Unknown",
                "Score": "7.4",
            },
            {
                "Company": "Georgia Vent Works",
                "Website": "https://georgia.example.com",
                "Phone": "770-474-5510",
            },
            {
                "Company": "Mr. Hood Clean",
                "Website": "https://mrhood.example.com",
                "Email": "pat@mrhood.example.com",
            },
        ]
        additions = [
            {
                "Business": "Example Hoods",
                "City": "Dallas",
                "State": "TX",
                "Website": "example.com",
                "Number": "214-555-0100",
                "Email": "owner@example.com",
                "Name": "Jamie",
                "Outreach Status": "Queued - send 8/22",
            },
            {
                "Business": "Example Hoods Second Claim",
                "City": "Dallas",
                "State": "TX",
                "Website": "http://EXAMPLE.COM/",
                "Number": "214-555-0199",
                "Email": "other@example.com",
                "Name": "Other Name",
                "Outreach Status": "Emailed 8/21",
            },
        ]
        for relative, rows in zip(library.CSV_FILES, (primary, additions)):
            headers = list(dict.fromkeys(key for row in rows for key in row))
            with (source / relative).open(
                "w", encoding="utf-8-sig", newline=""
            ) as stream:
                writer = csv.DictWriter(stream, headers)
                writer.writeheader()
                writer.writerows(rows)
        (source / library.NOTE_FILES[0]).write_text(
            "CIMA source phone 645-224-2817 invalid. Georgia phone came from a search-result summary.",
            encoding="utf-8",
        )
        (source / library.NOTE_FILES[1]).write_text(
            "CIMA SKIPPED: delivery delayed since August 20.", encoding="utf-8"
        )
        (source / library.NOTE_FILES[2]).write_text(
            "Mr. Hood Clean: Address not found bounce.", encoding="utf-8"
        )
        return source

    def test_source_is_unchanged_and_all_rows_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source(directory)
            before = {
                p.relative_to(source).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in source.rglob("*")
                if p.is_file()
            }
            snapshot = library.build(source)
            after = {
                p.relative_to(source).as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in source.rglob("*")
                if p.is_file()
            }
            self.assertEqual(before, after)
            self.assertEqual(6, snapshot["source_row_count"])
            self.assertEqual(4, snapshot["record_count"])
            self.assertEqual(
                6, sum(len(record["provenance"]) for record in snapshot["records"])
            )
            self.assertEqual(64, len(snapshot["snapshot_hash"]))
            self.assertEqual(
                snapshot["snapshot_hash"], library.build(source)["snapshot_hash"]
            )

    def test_host_dedup_first_nonempty_values_and_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = library.build(self.source(directory))
            record = snapshot["records"][0]
            self.assertEqual("Example Hoods", record["name"])
            self.assertEqual("owner@example.com", record["email"])
            self.assertEqual("Jamie", record["decision_maker"])
            self.assertEqual("(214) 555-0100", record["phone"])
            self.assertEqual(7.4, record["historical_score"])
            self.assertEqual(3, len(record["provenance"]))
            self.assertEqual(
                "Unknown (obfuscated)", record["provenance"][0]["raw_row"]["Email"]
            )
            self.assertTrue(
                any(
                    "Conflicting historical phone" in warning
                    for warning in record["warnings"]
                )
            )
            self.assertEqual("historical_unverified", record["contact_status"])
            self.assertEqual("unknown", record["email_deliverability"])
            self.assertFalse(record["verified"])

    def test_unknowns_and_later_historical_incidents_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = library.build(self.source(directory))
            first, cima, georgia, bounced = snapshot["records"]
            self.assertEqual("", first["role"])
            self.assertEqual("", cima["phone"])
            self.assertEqual("", cima["decision_maker"])
            self.assertTrue(
                any("delivery delays" in warning for warning in cima["warnings"])
            )
            self.assertTrue(
                any(
                    "search-result summary" in warning
                    for warning in georgia["warnings"]
                )
            )
            self.assertTrue(
                any(
                    "address-not-found bounce" in warning
                    for warning in bounced["warnings"]
                )
            )
            self.assertEqual("unknown", bounced["email_deliverability"])

    def test_load_missing_and_malformed_snapshot_are_nonfatal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with patch.object(library, "SNAPSHOT_PATH", path):
                self.assertEqual([], library.load()["records"])
                self.assertFalse(library.load()["available"])
                path.write_text("{broken", encoding="utf-8")
                self.assertEqual(0, library.load()["record_count"])
                path.write_text(
                    json.dumps({"schema_version": 1, "records": "wrong"}),
                    encoding="utf-8",
                )
                self.assertFalse(library.load()["available"])

    def test_organized_runs_become_full_compiled_collections(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "library.db"
            snapshot_path = Path(directory) / "missing-snapshot.json"
            conn = sqlite3.connect(database)
            conn.execute(
                "CREATE TABLE jobs (id TEXT, payload TEXT, updated_at TEXT)"
            )
            organized = {
                "id": "organized-run",
                "created_at": "2026-10-23T10:00:00+05:00",
                "status": "complete",
                "params": {"niche": "Roofing", "location": "Dallas, Texas"},
                "rows": [{"name": "Acme Roof", "email": "owner@acme.test", "verification": "{}"}],
                "organization": {
                    "organized_records": 1,
                    "duplicates_consolidated": 2,
                    "recommended_email_records": 1,
                    "ai_status": "complete",
                },
                "diagnosis": {"summary": "complete"},
            }
            unfinished = {
                "id": "discovery-only",
                "created_at": "2026-10-23T09:00:00+05:00",
                "status": "complete",
                "params": {"niche": "Roofing", "location": "Austin, Texas"},
                "rows": [{"name": "Not verified"}],
            }
            conn.executemany(
                "INSERT INTO jobs VALUES (?,?,?)",
                [
                    (organized["id"], json.dumps(organized), "2026-10-23T10:10:00+05:00"),
                    (unfinished["id"], json.dumps(unfinished), "2026-10-23T09:10:00+05:00"),
                ],
            )
            conn.commit()
            conn.close()

            @contextmanager
            def connection():
                current = sqlite3.connect(database)
                try:
                    yield current
                finally:
                    current.close()

            fake_engine = SimpleNamespace(connection=connection)
            with (
                patch.dict(sys.modules, {"engine": fake_engine}),
                patch.object(library, "SNAPSHOT_PATH", snapshot_path),
            ):
                loaded = library.load()
            self.assertEqual(1, loaded["compiled_record_count"])
            self.assertEqual(1, len(loaded["collections"]))
            collection = loaded["collections"][0]
            self.assertEqual("organized-run", collection["job_id"])
            self.assertEqual("Acme Roof", collection["rows"][0]["name"])
            self.assertEqual(2, collection["organization"]["duplicates_consolidated"])
            self.assertEqual({"summary": "complete"}, collection["diagnosis"])

    def test_fictional_demo_data_is_not_imported(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source(directory)
            (source / "demo").mkdir()
            (source / "demo" / "index.html").write_text(
                "fictional company: Demo Job", encoding="utf-8"
            )
            snapshot = library.build(source)
            self.assertEqual(4, snapshot["record_count"])
            self.assertNotIn("Demo Job", json.dumps(snapshot))

    def test_known_source_csv_unquoted_commas_are_recovered_with_raw_cells(self):
        headers = "Rank,Company,City,State,Website,Phone,Email,DecisionMaker,Role,YearsInBusiness,Services,RecurringService,ReportsPhotoWorkflow,ExistingSoftware,EvidenceOfManualWorkflow,CompanySizeSignal,Score,PainReason,PersonalizationHook,SourceURL".split(
            ","
        )
        cases = [
            (
                "Clean Hoods Express",
                "EvidenceOfManualWorkflow",
                "Likely: recurring accounts",
                " no report tool shown",
            ),
            (
                "WhaleyCo Kitchen & Cleaning Services",
                "EvidenceOfManualWorkflow",
                "Likely: diversified small shop",
                " no reporting tool",
            ),
            (
                "DDAN Hood Services",
                "CompanySizeSignal",
                "Established (3",
                "000+ kitchens)",
            ),
        ]
        for company, field, left, right in cases:
            with self.subTest(company=company):
                values = dict.fromkeys(headers, "")
                values.update(
                    Company=company, Score="7.35", SourceURL="https://example.com"
                )
                values[field] = left + "," + right
                cells = [values[key] for key in headers]
                index = headers.index(field)
                cells[index : index + 1] = [left, right]
                parsed, raw_row, raw_cells, repair = library._parse_row(
                    headers, cells, library.CSV_FILES[0], 11
                )
                self.assertEqual("7.35", parsed["Score"])
                self.assertEqual("https://example.com", parsed["SourceURL"])
                self.assertEqual(left + "," + right, parsed[field])
                self.assertEqual(cells, raw_cells)
                self.assertTrue(raw_row["__extra_columns"])
                self.assertIn("known unquoted comma", repair)
        with self.assertRaisesRegex(ValueError, "requires review"):
            library._parse_row(
                ["Company", "Website"],
                ["Other", "https://example.com", "extra"],
                library.CSV_FILES[0],
                2,
            )

    def test_load_roundtrip_retains_snapshot_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.source(directory)
            snapshot = library.build(source)
            path = source / "snapshot.json"
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            with patch.object(library, "SNAPSHOT_PATH", path):
                loaded = library.load()
            self.assertTrue(loaded["available"])
            self.assertEqual(snapshot["snapshot_hash"], loaded["snapshot_hash"])
            self.assertEqual(4, loaded["record_count"])


if __name__ == "__main__":
    unittest.main()
