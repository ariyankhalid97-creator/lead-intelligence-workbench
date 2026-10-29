import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import connections
import public_sources


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.vault = {}
        self.patches = (
            patch.object(
                connections.keyring,
                "get_password",
                side_effect=lambda service, user: self.vault.get((service, user)),
            ),
            patch.object(
                connections.keyring,
                "set_password",
                side_effect=lambda service, user, value: self.vault.__setitem__(
                    (service, user), value
                ),
            ),
            patch.object(
                connections.keyring,
                "delete_password",
                side_effect=lambda service, user: self.vault.pop((service, user), None),
            ),
        )
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_provider_secret_is_masked_tested_and_disabled_by_default(self):
        saved = connections.save(
            "apollo", {"api_key": "apollo-secret-example", "enabled": True}
        )
        self.assertTrue(saved["configured"])
        self.assertFalse(saved["connected"])
        self.assertFalse(saved["enabled"])
        self.assertNotIn("apollo-secret-example", json.dumps(saved))
        with patch.object(
            connections, "_json_request", return_value={"status": "healthy"}
        ):
            tested = connections.test("apollo")
        self.assertTrue(tested["connected"])
        with self.assertRaises(ValueError):
            connections.set_enabled("apollo", True)
        self.assertEqual("", connections.secret("apollo"))

    def test_google_desktop_oauth_uses_loopback_pkce_and_same_exchange_uri(self):
        connections._write(
            "google_sheets",
            {
                "client_id": "123456789012345678901.apps.googleusercontent.com",
                "client_secret": "secret-value",
            },
        )
        callback = "http://127.0.0.1:8788"
        destination = connections.google_authorize_url(callback)
        query = parse_qs(urlparse(destination).query)
        self.assertEqual([callback], query["redirect_uri"])
        self.assertEqual(["S256"], query["code_challenge_method"])
        self.assertEqual(43, len(query["code_challenge"][0]))
        state = query["state"][0]
        self.assertEqual(callback, connections.OAUTH_STATES[state]["callback"])

        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(
            connections,
            "urlopen",
            side_effect=lambda request, timeout=0: (
                captured.update(body=request.data.decode("utf-8")) or Response()
            ),
        ), patch.object(
            connections.json,
            "load",
            return_value={"refresh_token": "refresh", "scope": connections.GOOGLE_SCOPE},
        ):
            connections.google_callback("code", state, callback)
        exchanged = parse_qs(captured["body"])
        self.assertEqual([callback], exchanged["redirect_uri"])
        self.assertTrue(exchanged["code_verifier"][0])

    def test_google_oauth_rejects_non_loopback_callback(self):
        connections._write(
            "google_sheets",
            {
                "client_id": "123456789012345678901.apps.googleusercontent.com",
                "client_secret": "secret-value",
            },
        )
        with self.assertRaises(ValueError):
            connections.google_authorize_url("https://example.test/callback")

    def test_source_catalog_is_seeded_without_enabling_paid_sources(self):
        conn = sqlite3.connect(":memory:")
        conn.executescript(Path("replica/schema.sql").read_text(encoding="utf-8"))
        connections.init_source_catalog(conn)
        rows = conn.execute(
            "SELECT country,status,enabled FROM source_catalog ORDER BY country"
        ).fetchall()
        self.assertEqual(4, len(rows))
        self.assertTrue(
            all(status == "planned" and enabled == 0 for _, status, enabled in rows)
        )

    def test_sheet_sync_creates_app_owned_sheet_and_writes_raw_values(self):
        connections._write(
            "google_sheets",
            {
                "client_id": "123456789012345678901.apps.googleusercontent.com",
                "client_secret": "secret-value",
                "refresh_token": "refresh-value",
            },
        )
        calls = []

        def request(url, **kwargs):
            calls.append((url, kwargs))
            if url == "https://sheets.googleapis.com/v4/spreadsheets":
                return {"spreadsheetId": "sheet-123"}
            return {"updatedCells": 19}

        snapshot = {
            "records": [],
            "collections": [
                {
                    "title": "Dentists · Dallas",
                    "niche": "Dentists",
                    "updated_at": "2026-10-27T00:00:00Z",
                    "rows": [
                        {
                            "name": "Acme Dental",
                            "city": "Dallas",
                            "email": "hello@example.test",
                        }
                    ],
                }
            ],
        }
        with (
            patch.object(connections, "_google_access_token", return_value="token"),
            patch.object(connections, "_json_request", side_effect=request),
        ):
            result = connections.sync_sheet(snapshot)
        self.assertEqual(1, result["rows"])
        self.assertEqual("sheet-123", result["spreadsheet_id"])
        self.assertEqual(["Dentists · Dallas"], result["worksheets"])
        self.assertEqual(
            "Dentists · Dallas",
            calls[0][1]["data"]["sheets"][0]["properties"]["title"],
        )
        self.assertEqual("RAW", calls[-1][0].split("valueInputOption=")[-1])
        self.assertEqual("Acme Dental", calls[-1][1]["data"]["values"][1][2])

    def test_sheet_sync_creates_separate_sanitized_worksheets(self):
        tabs = connections._sheet_tabs(
            {
                "collections": [
                    {"sheet_title": "E-sign Workflow - Real Estate", "rows": []},
                    {"sheet_title": "E-sign Workflow - Hiring", "rows": []},
                    {"sheet_title": "E-sign Workflow / Rentals", "rows": []},
                ]
            }
        )
        self.assertEqual(
            [
                "E-sign Workflow - Real Estate",
                "E-sign Workflow - Hiring",
                "E-sign Workflow - Rentals",
            ],
            [title for title, _ in tabs],
        )

    def test_running_offer_job_gets_its_own_titled_worksheet(self):
        snapshot = connections.job_sheet_snapshot(
            {
                "updated_at": "2026-10-28T00:00:00Z",
                "params": {
                    "offer_title": "E-sign Workflow",
                    "offer_segment_label": "Rental & leasing operators",
                    "niche": "rental companies",
                },
                "rows": [{"name": "Acme Rentals", "city": "Dallas"}],
            }
        )
        tab, values = connections._sheet_tabs(snapshot)[0]
        self.assertEqual("E-sign Workflow - Rental & leasing operators", tab)
        self.assertEqual("Acme Rentals", values[1][2])

    def test_employee_profiles_get_a_separate_deduplicated_worksheet(self):
        title, values = connections._employee_sheet_tab(
            {
                "params": {
                    "niche": "staffing agencies",
                    "location": "Singapore",
                },
                "employees": [
                    {
                        "company_name": "Acme Staffing",
                        "company_linkedin": "https://www.linkedin.com/company/acme/",
                        "employee_name": "Example Person",
                        "headline": "Operations Director",
                        "employee_linkedin": "https://www.linkedin.com/in/example-person/",
                        "evidence_url": "https://www.linkedin.com/company/acme/people/",
                        "basis": "visible_linkedin_company_people_page",
                        "observed_at": "2026-10-29T10:00:00+05:00",
                    },
                    {
                        "employee_name": "Duplicate",
                        "employee_linkedin": "https://www.linkedin.com/in/example-person/",
                    },
                ],
            }
        )
        self.assertEqual("staffing agencies · Singapore · Employees", title)
        self.assertEqual(list(connections.EMPLOYEE_SHEET_COLUMNS), values[0])
        self.assertEqual(2, len(values))
        self.assertEqual("Example Person", values[1][2])
        self.assertEqual(
            "https://www.linkedin.com/in/example-person/",
            values[1][connections.EMPLOYEE_SHEET_COLUMNS.index("employee_linkedin")],
        )

    def test_enabled_places_provider_maps_api_fields_to_lead(self):
        connections._write(
            "google_places",
            {
                "api_key": "places-secret-example",
                "verified_at": "2026-10-27T00:00:00Z",
                "enabled": True,
            },
        )
        place = {
            "id": "place-1",
            "displayName": {"text": "Acme Dental"},
            "formattedAddress": "1 Main St, Dallas, TX",
            "nationalPhoneNumber": "(214) 555-0100",
            "websiteUri": "https://acme.example",
            "primaryType": "dentist",
            "location": {"latitude": 32.7, "longitude": -96.8},
            "rating": 4.7,
            "userRatingCount": 12,
        }
        with patch.object(connections, "google_places_text", return_value=[place]):
            rows = public_sources.google_places_search(
                {"phrases": ["dentist"]}, "Dallas, Texas", 5
            )
        self.assertEqual(1, len(rows))
        self.assertEqual("google_places_api", rows[0].source)
        self.assertEqual("https://acme.example", rows[0].website)


if __name__ == "__main__":
    unittest.main()
