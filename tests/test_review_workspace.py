import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import intelligence
import review_workspace


class ReviewWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch.object(engine, "DB", Path(self.tmp.name) / "test.db")
        self.patch.start()
        engine.init(recover=False)
        intelligence.init()
        review_workspace.init()
        self.job = {
            "id": "b" * 32,
            "params": {"niche": "Roofing", "location": "Dallas, Texas"},
            "rows": [{
                "name": "Branch Roof", "city": "Dallas", "address": "1 Main St",
                "website": "https://branch.example", "phone": "214-555-0100",
                "email": "owner@branch.example", "decision_maker": "Jamie Owner",
                "verification": json.dumps({"status": "complete", "website": {"status": "reachable"}}),
                "email_quality": json.dumps({"recommended": [{"email": "owner@branch.example", "recommended": True}]}),
                "evidence": json.dumps([{"field": "email", "value": "owner@branch.example", "url": "https://branch.example/contact", "basis": "page_text"}]),
            }],
        }
        intelligence.compile_job(self.job)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_contact_review_keeps_permission_separate(self):
        company_id = self.job["rows"][0]["entity_id"]
        before = review_workspace.contact_decisions(company_id)[0]
        self.assertTrue(before["address_verified"])
        self.assertFalse(before["send_eligible"])
        review_workspace.save_contact_review({
            "company_id": company_id, "email": "owner@branch.example",
            "decision": "confirmed", "permission_to_send": True,
        })
        after = review_workspace.contact_decisions(company_id)[0]
        self.assertTrue(after["contact_review"]["permission_to_send"])
        self.assertTrue(after["send_eligible"])

    def test_search_preset_round_trip(self):
        saved = review_workspace.save_preset({
            "name": "Dallas owners", "offer": "Document workflow",
            "target_role": "Owner", "geography": "Dallas, Texas",
            "exclusions": ["chains"], "sources": ["hybrid"],
        })
        self.assertEqual(saved["id"], review_workspace.presets()[0]["id"])


if __name__ == "__main__":
    unittest.main()
