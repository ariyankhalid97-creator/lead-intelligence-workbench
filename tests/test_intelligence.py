import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import intelligence
from leadfinder import Lead


class IntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.db_patch = patch.object(engine, "DB", self.db)
        self.db_patch.start()
        engine.init(recover=False)
        intelligence.init()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def job(self, email="owner@acme.test", phone="214-555-0100"):
        return {
            "id": "a" * 32,
            "params": {"niche": "Roofing", "location": "Dallas, Texas"},
            "rows": [
                {
                    "name": "Acme Roof",
                    "city": "Dallas",
                    "address": "1 Main St",
                    "website": "https://acme.test",
                    "phone": phone,
                    "email": email,
                    "decision_maker": "Jamie Owner",
                    "email_quality": json.dumps({"recommended": [{"email": email, "recommended": True}]}),
                    "verification": json.dumps({"status": "complete", "website": {"status": "reachable", "final_url": "https://acme.test"}, "website_audit": {"status": "reachable", "url": "https://acme.test", "contact_form": False, "booking_path": False}}),
                    "evidence": json.dumps([{"field": "email", "value": email, "url": "https://acme.test/contact", "basis": "page_text"}]),
                }
            ],
        }

    def test_compile_builds_identity_memory_queue_and_change_detection(self):
        first = self.job()
        summary = intelligence.compile_job(first)
        row = first["rows"][0]
        self.assertEqual(1, summary["compiled_entities"])
        self.assertTrue(row["entity_id"].startswith("company-"))
        self.assertEqual("ready_for_outreach", row["next_best_action"])
        self.assertGreaterEqual(row["contact_confidence"], 80)
        self.assertEqual(1, intelligence.overview()["companies"])
        self.assertEqual(1, intelligence.overview()["watcher"]["scheduled"])
        self.assertEqual(row["entity_id"], intelligence.queue()[0]["company_id"])
        memory = intelligence.entity(row["entity_id"])
        self.assertEqual(1, len(memory["locations"]))
        self.assertEqual(1, len(memory["contacts"]))
        self.assertEqual("email", memory["evidence"][0]["field"])

        changed = self.job(phone="214-555-0199")
        intelligence.compile_job(changed)
        self.assertEqual(row["entity_id"], changed["rows"][0]["entity_id"])
        self.assertTrue(json.loads(changed["rows"][0]["intelligence"])["change_detected"])

    def test_outcome_updates_queue_and_suppression_gate(self):
        job = self.job()
        intelligence.compile_job(job)
        row = job["rows"][0]
        intelligence.record_outcome({"company_id": row["entity_id"], "email": row["email"], "outcome": "bounced"})
        self.assertFalse(intelligence.preflight(row, row["email"])["eligible"])
        self.assertEqual("suppress", intelligence.queue()[0]["action"])
        with engine.connection() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM outreach_suppressions WHERE email=?", (row["email"],)).fetchone())

    def test_niche_pack_is_editable_and_bounded(self):
        slug = intelligence.save_niche_pack({"name": "Pool Cleaning", "synonyms": ["pool cleaner", "pool maintenance"], "decision_maker_roles": ["owner"]})
        self.assertEqual("pool-cleaning", slug)
        pack = next(item for item in intelligence.niche_packs() if item["name"] == "Pool Cleaning")
        self.assertEqual(["pool cleaner", "pool maintenance"], pack["synonyms"])
        self.assertEqual("user_approved", pack["generated_by"])

    def test_niche_pack_exclusion_only_uses_strong_business_fields(self):
        pack = {"exclusions": ["jobs", "training"]}
        ordinary = Lead(name="Acme Roofing", category="Roofing contractor")
        intelligence.apply_niche_pack(ordinary, pack)
        self.assertNotIn("niche_exclusion", ordinary.quality_flags)

        excluded = Lead(name="Roofing Jobs and Training", category="Training center", match_status="service_match")
        intelligence.apply_niche_pack(excluded, pack)
        self.assertEqual("candidate", excluded.match_status)
        self.assertIn("niche_exclusion:jobs", json.loads(excluded.quality_flags))

    def test_browser_checkpoint_and_experiment_results_remain_connected(self):
        job = self.job()
        intelligence.compile_job(job)
        row = job["rows"][0]
        intelligence.browser_checkpoint({"company_id": row["entity_id"], "service": "linkedin", "status": "security_check", "url": "https://www.linkedin.com/company/acme"})
        self.assertEqual("manual_browser_review", intelligence.queue()[0]["action"])
        intelligence.browser_checkpoint({"company_id": row["entity_id"], "service": "linkedin", "status": "complete", "url": "https://www.linkedin.com/company/acme"})
        self.assertEqual("ready_for_outreach", intelligence.queue()[0]["action"])

        variant = intelligence.variant_index(row, "campaign-1", 2)
        intelligence.record_outcome({"company_id": row["entity_id"], "email": row["email"], "campaign_id": "campaign-1", "outcome": "replied"})
        results = intelligence.experiment_results("campaign-1")["variants"]
        variant_name = chr(65 + variant)
        self.assertEqual(1, results[variant_name]["assigned"])
        self.assertEqual(1, results[variant_name]["outcomes"]["replied"])

    def test_rerun_restores_supported_contacts_and_ai_terms_persist(self):
        job = self.job()
        intelligence.compile_job(job)
        sparse = [{"name": "Acme Roof", "city": "Dallas", "website": "https://acme.test", "evidence": "[]"}]
        self.assertEqual(1, intelligence.restore_remembered_contacts(sparse))
        self.assertEqual("owner@acme.test", sparse[0]["email"])
        self.assertEqual("2145550100", sparse[0]["phone"])
        self.assertEqual("restored_from_prior_compiled_evidence", json.loads(sparse[0]["contact_memory"])["status"])

        intelligence.record_ai_search_terms("Roofing", ["roof restoration contractor"], "local-model")
        pack = next(item for item in intelligence.niche_packs() if item["name"] == "Roofing")
        self.assertIn("roof restoration contractor", pack["synonyms"])
        self.assertEqual(["roof restoration contractor"], pack["ai_terms"])


if __name__ == "__main__":
    unittest.main()
