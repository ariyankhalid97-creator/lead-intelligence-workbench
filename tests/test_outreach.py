import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import outreach


class OutreachTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = engine.DB
        engine.DB = Path(self.temp.name) / "workbench.db"
        engine.init(recover=False)

    def tearDown(self):
        engine.DB = self.old_db
        outreach.STOPS.clear()
        outreach.AI_JOBS.clear()
        self.temp.cleanup()

    def test_template_and_campaign_are_drafts_until_explicit_approval(self):
        template_id = outreach.save_template({
            "name": "Roofing intro",
            "niche": "Roofing",
            "subject": "Question for {{business_name}}",
            "body": "Hello {{business_name}},\nI noticed your work in {{city}}.\nReply unsubscribe if this is not relevant.",
        })
        job = {
            "id": "a" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Roofing"},
            "rows": [{"name": "Acme Roof", "email": "hello@example.com", "city": "Dallas", "match_status": "service_match"}],
        }
        engine.save(job)
        campaign_id = outreach.create_campaign({"job_id": job["id"], "template_id": template_id, "scope": "matches", "maximum": 10})
        campaign = outreach._campaign(campaign_id)
        self.assertEqual("draft", campaign["status"])
        self.assertEqual("draft", campaign["messages"][0]["status"])
        self.assertIn("Acme Roof", campaign["messages"][0]["subject"])
        with self.assertRaises(ValueError):
            outreach.start(campaign_id, confirmation=False)

    def test_suppression_and_campaign_cap(self):
        template_id = outreach.save_template({"name": "General", "niche": "Plumbing", "subject": "Hello {{business_name}}", "body": "Hello {{business_name}}, this is a relevant one-to-one note. Reply unsubscribe."})
        rows = [{"name": f"Lead {i}", "email": f"lead{i}@example.com", "match_status": "service_match"} for i in range(25)]
        job = {"id": "b" * 32, "created_at": "2026-10-22T00:00:00+05:00", "status": "complete", "params": {"niche": "Plumbing"}, "rows": rows}
        engine.save(job)
        outreach.suppress("lead0@example.com", "Opted out")
        campaign_id = outreach.create_campaign({"job_id": job["id"], "template_id": template_id, "scope": "matches", "maximum": 20})
        campaign = outreach._campaign(campaign_id)
        self.assertEqual(20, campaign["total"])
        self.assertNotIn("lead0@example.com", {m["recipient"] for m in campaign["messages"]})
        with self.assertRaises(ValueError):
            outreach.create_campaign({"job_id": job["id"], "template_id": template_id, "scope": "matches", "maximum": 21})

    def test_campaign_rotates_multiple_templates_across_recipients(self):
        first = outreach.save_template({
            "name": "Angle A",
            "niche": "Plumbing",
            "subject": "Angle A for {{business_name}}",
            "body": "Angle A body for {{business_name}}. Reply unsubscribe.",
        })
        second = outreach.save_template({
            "name": "Angle B",
            "niche": "Plumbing",
            "subject": "Angle B for {{business_name}}",
            "body": "Angle B body for {{business_name}}. Reply unsubscribe.",
        })
        job = {
            "id": "f" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Plumbing"},
            "rows": [
                {"name": f"Lead {i}", "email": f"lead{i}@example.com", "match_status": "service_match"}
                for i in range(4)
            ],
        }
        engine.save(job)
        campaign_id = outreach.create_campaign({
            "job_id": job["id"],
            "mode": "template",
            "template_ids": [first, second],
            "scope": "matches",
            "maximum": 4,
        })
        campaign = outreach._campaign(campaign_id)
        self.assertEqual([first, second], campaign["template_ids"])
        self.assertEqual("2 templates", campaign["template_name"])
        sources = [campaign["message_sources"][str(m["id"])] for m in campaign["messages"]]
        self.assertEqual(["Angle A", "Angle B", "Angle A", "Angle B"], sources)
        subjects = [m["subject"] for m in campaign["messages"]]
        self.assertTrue(subjects[0].startswith("Angle A"))
        self.assertTrue(subjects[1].startswith("Angle B"))

    def test_multiple_campaigns_can_send_at_the_same_time(self):
        template_id = outreach.save_template({
            "name": "Parallel",
            "niche": "Plumbing",
            "subject": "Hello {{business_name}}",
            "body": "Hello {{business_name}}, relevant note. Reply unsubscribe.",
        })
        job = {
            "id": "9" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Plumbing"},
            "rows": [
                {"name": "One", "email": "one@example.com", "match_status": "service_match"},
                {"name": "Two", "email": "two@example.com", "match_status": "service_match"},
            ],
        }
        engine.save(job)
        first = outreach.create_campaign({"job_id": job["id"], "template_id": template_id, "maximum": 1})
        second = outreach.create_campaign({"job_id": job["id"], "template_id": template_id, "maximum": 1})
        provider = {
            "connected": True,
            "from_address": "sender@example.com",
            "message": "connected",
            "missing": [],
        }
        with patch.object(outreach, "provider_status", return_value=provider), patch.object(
            outreach, "_zoho_send", return_value="provider-id"
        ), patch.object(outreach.random, "uniform", return_value=0):
            outreach.start(first, confirmation=True)
            outreach.start(second, confirmation=True)
            self.assertEqual(2, len(outreach.STOPS))
            deadline = time.time() + 5
            while time.time() < deadline:
                statuses = {
                    outreach._campaign(item)["status"] for item in (first, second)
                }
                if statuses == {"complete"}:
                    break
                time.sleep(0.02)
        self.assertEqual({"complete"}, statuses)
        self.assertEqual(0, len(outreach.STOPS))

    def _wait_for_drafting(self, campaign_id, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            campaign = outreach._campaign(campaign_id)
            if campaign["status"] != "drafting" and not campaign["drafting"]:
                return campaign
            time.sleep(0.05)
        raise AssertionError("AI drafting did not finish in time")

    def test_ai_campaign_assigns_local_model_and_drafts_each_message(self):
        job = {
            "id": "c" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Roofing"},
            "rows": [
                {"name": "Acme Roof", "email": "hello@example.com", "match_status": "service_match"},
                {"name": "Beta Roof", "email": "beta@example.com", "match_status": "service_match"},
            ],
        }
        engine.save(job)
        draft = {
            "status": "ready_for_review",
            "subject": "Quick question",
            "body": "Hello,\nWould a faster quote form help?",
            "model": "qwen3.5:4b",
        }
        with patch.object(outreach.local_ai, "review", return_value={"draft": draft, "analysis": {"status": "complete"}}) as review:
            campaign_id = outreach.create_campaign({
                "job_id": job["id"],
                "mode": "ai",
                "ai_model": "qwen3.5:4b",
                "offer": "I build fast quote forms",
                "scope": "matches",
                "maximum": 5,
            })
            campaign = self._wait_for_drafting(campaign_id)
        self.assertEqual("ai", campaign["mode"])
        self.assertEqual("qwen3.5:4b", campaign["ai_model"])
        self.assertEqual("draft", campaign["status"])
        self.assertEqual(2, review.call_count)
        self.assertEqual(2, campaign["ready"])
        self.assertEqual(0, campaign["draft_failed"])
        for message in campaign["messages"]:
            self.assertEqual("draft", message["status"])
            self.assertEqual("Quick question", message["subject"])
            self.assertIn("faster quote form", message["body"])

    def test_ai_campaign_marks_unusable_drafts_and_blocks_sending(self):
        job = {
            "id": "d" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Roofing"},
            "rows": [{"name": "Acme Roof", "email": "hello@example.com", "match_status": "service_match"}],
        }
        engine.save(job)
        empty = {"draft": {"status": "insufficient_evidence", "subject": "", "body": ""}, "analysis": {"status": "insufficient_evidence"}}
        with patch.object(outreach.local_ai, "review", return_value=empty):
            campaign_id = outreach.create_campaign({
                "job_id": job["id"],
                "mode": "ai",
                "ai_model": "qwen3.5:4b",
                "offer": "I build fast quote forms",
                "scope": "matches",
                "maximum": 3,
            })
            campaign = self._wait_for_drafting(campaign_id)
        self.assertEqual(1, campaign["draft_failed"])
        self.assertEqual("draft_failed", campaign["messages"][0]["status"])
        self.assertIn("evidence", campaign["messages"][0]["error"].lower())
        with self.assertRaises(ValueError):
            outreach.start(campaign_id, confirmation=True)

    def test_ai_campaign_requires_a_model_and_offer(self):
        job = {
            "id": "e" * 32,
            "created_at": "2026-10-22T00:00:00+05:00",
            "status": "complete",
            "params": {"niche": "Roofing"},
            "rows": [{"name": "Acme Roof", "email": "hello@example.com", "match_status": "service_match"}],
        }
        engine.save(job)
        with self.assertRaises(ValueError):
            outreach.create_campaign({"job_id": job["id"], "mode": "ai", "ai_model": "", "offer": "I build forms"})
        with self.assertRaises(ValueError):
            outreach.create_campaign({"job_id": job["id"], "mode": "ai", "ai_model": "qwen3.5:4b", "offer": ""})


if __name__ == "__main__":
    unittest.main()
