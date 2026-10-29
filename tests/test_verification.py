import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import verification
import browser_session


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = engine.DB
        engine.DB = Path(self.temp.name) / "workbench.db"
        engine.init(recover=False)

    def tearDown(self):
        engine.DB = self.old_db
        verification.EVENTS.clear()
        self.temp.cleanup()

    def test_public_signals_are_labeled_without_claiming_active_ads(self):
        row = {
            "name": "Example Roofer",
            "website": "https://example.test",
            "facebook": "",
            "instagram": "",
            "linkedin": "",
            "rating": "4.8",
            "reviews": "42",
            "source_url": "https://maps.google.com/example",
            "search_location": "Dallas, Texas",
        }
        page = '<a href="https://facebook.com/example">Social</a><script>fbq("init")</script>'
        client = type("Client", (), {"get": lambda self, url: (page, url)})()
        with (
            patch.object(verification, "WebClient", return_value=client),
            patch.object(verification, "_review_sources", return_value=[]),
            patch.object(verification, "_market_signals", return_value={"status": "complete", "candidates": [], "direct_checks": {"meta_ad_library": "https://facebook.test/ads", "google_ads_transparency": "https://google.test/ads"}}),
            patch.object(browser_session, "enabled_services", return_value={"facebook": True, "linkedin": True}),
            patch.object(browser_session, "search_company_sources", return_value={"status": "complete", "query": "synthetic", "candidates": []}),
        ):
            _, report = verification._verify(0, row, threading.Event())
        self.assertEqual("reachable", report["website"]["status"])
        self.assertEqual("published_on_website", report["socials"]["facebook"]["status"])
        self.assertEqual("tracking_detected_not_campaign_verified", report["ads"]["status"])
        self.assertIn("does not prove an active campaign", report["ads"]["note"])
        self.assertEqual("https://facebook.test/ads", report["ads"]["meta_ad_library"])

    def test_default_scope_selects_only_service_or_category_matches(self):
        job = {
            "id": "a" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "rows": [
                {"name": "Match", "match_status": "service_match", "verification": "{}"},
                {"name": "Candidate", "match_status": "candidate", "verification": "{}"},
            ],
        }
        engine.save(job)
        reports = []

        def fake_verify(index, row, cancel):
            reports.append(row["name"])
            return index, {"status": "complete", "website": {}, "socials": {}, "ads": {}, "reviews": {}}

        task = {
            "id": "b" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "queued",
            "message": "",
            "progress": 0,
            "params": {"job_id": job["id"], "scope": "matches"},
            "checked": 0,
            "total": 0,
            "summary": {},
        }
        with patch.object(verification, "_verify", side_effect=fake_verify):
            verification._run(task, threading.Event())
        self.assertEqual(["Match"], reports)
        self.assertEqual("complete", task["status"])
        saved = engine.get_job(job["id"], events=False)
        self.assertEqual("complete", json.loads(saved["rows"][0]["verification"])["status"])
        self.assertEqual("{}", saved["rows"][1]["verification"])

    def test_unfinished_scope_skips_completed_browser_discovery(self):
        completed = {
            "status": "complete",
            "social_discovery": {"status": "complete_with_fallback", "candidates": []},
        }
        job = {
            "id": "c" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "rows": [
                {"name": "Done", "match_status": "service_match", "verification": json.dumps(completed)},
                {"name": "Missing", "match_status": "candidate", "verification": "{}"},
                {"name": "Failed", "match_status": "candidate", "verification": json.dumps({"status": "complete", "social_discovery": {"status": "failed"}})},
            ],
        }
        engine.save(job)
        checked = []

        def fake_verify(index, row, cancel):
            checked.append(row["name"])
            return index, {"status": "complete", "social_discovery": {"status": "manual_checkpoint_with_fallback", "candidates": []}, "website": {}, "socials": {}, "ads": {}, "reviews": {}}

        task = {
            "id": "d" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "queued",
            "message": "",
            "progress": 0,
            "params": {"job_id": job["id"], "scope": "unfinished"},
            "checked": 0,
            "total": 0,
            "summary": {},
        }
        with patch.object(verification, "_verify", side_effect=fake_verify):
            verification._run(task, threading.Event())
        self.assertCountEqual(["Missing", "Failed"], checked)
        self.assertEqual(2, task["scope_count"])

    def test_verified_company_linkedin_url_is_copied_to_saved_lead(self):
        job = {
            "id": "e" * 32,
            "created_at": "2026-10-28T00:00:00+05:00",
            "status": "complete",
            "rows": [
                {
                    "name": "Example Company",
                    "match_status": "service_match",
                    "linkedin": "",
                    "verification": "{}",
                }
            ],
        }
        engine.save(job)

        def fake_verify(index, row, cancel):
            return index, {
                "status": "complete",
                "social_discovery": {"status": "complete", "candidates": []},
                "socials": {},
                "website": {},
                "ads": {},
                "reviews": {},
                "resolved_fields": {
                    "linkedin": "https://www.linkedin.com/company/example-company/"
                },
            }

        task = {
            "id": "f" * 32,
            "created_at": "2026-10-28T00:00:00+05:00",
            "status": "queued",
            "message": "",
            "progress": 0,
            "params": {"job_id": job["id"], "scope": "matches"},
            "checked": 0,
            "total": 0,
            "summary": {},
        }
        with (
            patch.object(verification, "_verify", side_effect=fake_verify),
            patch.object(
                verification.connections,
                "statuses",
                return_value={
                    "providers": [{"id": "google_sheets", "connected": True}]
                },
            ),
            patch.object(
                verification.connections,
                "sync_job_sheet",
                return_value={
                    "url": "https://docs.google.com/spreadsheets/d/test/edit",
                    "worksheets": ["Example niche · Dallas"],
                    "rows": 1,
                },
            ) as sheet_sync,
        ):
            verification._run(task, threading.Event())
        saved = engine.get_job(job["id"], events=False)
        self.assertEqual(
            "https://www.linkedin.com/company/example-company/",
            saved["rows"][0]["linkedin"],
        )
        sheet_sync.assert_called_once()
        self.assertEqual("synced", task["summary"]["google_sheet_status"])


if __name__ == "__main__":
    unittest.main()
