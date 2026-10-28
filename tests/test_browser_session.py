import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import browser_session


class BrowserCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "browser-session.json"
        self.state_patch = patch.object(browser_session, "STATE", self.state)
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop()
        self.temp.cleanup()

    def test_opening_profile_does_not_erase_search_pause(self):
        browser_session._pause_public_search("CAPTCHA detected", seconds=900)
        browser_session._remember("linkedin")
        checkpoint = browser_session.search_checkpoint_status()
        self.assertTrue(checkpoint["paused"])
        self.assertEqual("CAPTCHA detected", checkpoint["reason"])

    def test_paused_search_uses_fallback_without_opening_chrome(self):
        browser_session._pause_public_search("Google 403", seconds=900)
        candidate = {"kind": "linkedin_company", "url": "https://linkedin.com/company/example"}
        with (
            patch.object(browser_session, "_fallback_candidates", return_value=([candidate], "")) as fallback,
            patch.object(browser_session, "running") as running,
        ):
            result = browser_session.search_company_sources("Example", "Dallas, Texas")
        self.assertEqual("manual_checkpoint_with_fallback", result["status"])
        self.assertEqual([candidate], result["candidates"])
        fallback.assert_called_once()
        running.assert_not_called()

    def test_clear_checkpoint_allows_manual_resume(self):
        browser_session._pause_public_search("Google 429", seconds=900)
        browser_session.clear_search_checkpoint()
        self.assertFalse(browser_session.search_checkpoint_status()["paused"])
        saved = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertNotIn("search_pause_until", saved)

    def test_normal_verification_types_exact_linkedin_lookup_then_uses_fallback(self):
        candidate = {"kind": "linkedin_company", "url": "https://linkedin.com/company/example"}
        exact = {
            "status": "complete",
            "query": '"Example" LinkedIn',
            "candidates": [candidate],
        }
        with (
            patch.object(browser_session, "_google_linkedin_company", return_value=exact) as google,
            patch.object(browser_session, "_fallback_candidates", return_value=([], "")),
        ):
            result = browser_session.search_company_sources("Example", "Dallas, Texas")
        self.assertTrue(result["browser_automation_disabled"])
        self.assertEqual(
            ["google_typed_company_lookup", "public_search_adapter"],
            result["search_engines"],
        )
        self.assertEqual([candidate], result["candidates"])
        google.assert_called_once()

    def test_only_company_pages_are_accepted_as_linkedin_company_urls(self):
        self.assertEqual(
            "https://www.linkedin.com/company/example-co/",
            browser_session._canonical_linkedin_company_url(
                "https://www.linkedin.com/company/example-co/?trk=public"
            ),
        )
        self.assertEqual(
            "",
            browser_session._canonical_linkedin_company_url(
                "https://www.linkedin.com/in/private-person/"
            ),
        )


if __name__ == "__main__":
    unittest.main()
