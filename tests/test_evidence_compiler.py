import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import evidence_compiler
import intelligence
import organizer
import sequence_engine


class EvidenceCompilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(engine, "DB", Path(self.tmp.name) / "test.db")
        self.db_patch.start()
        engine.init(recover=False)

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def job(self):
        return {
            "id": "e" * 32,
            "params": {"niche": "Roofing"},
            "rows": [{
                "name": "Acme Roofing", "city": "Dallas", "address": "1 Main", "website": "https://acme.test",
                "email": "owner@acme.test", "decision_maker": "Jane Doe", "decision_maker_role": "Owner",
                "email_quality": json.dumps({"recommended": [{"email": "owner@acme.test", "recommended": True, "deliverability": "mail_domain_ready_mailbox_unverified"}]}),
                "verification": json.dumps({"status": "complete", "website": {"status": "reachable"}, "website_audit": {"status": "reachable", "url": "https://acme.test", "contact_form": False}}),
                "evidence": json.dumps([{"field": "email", "value": "owner@acme.test", "url": "https://acme.test/contact", "method": "mailto link", "observed_at": "2026-10-24T00:00:00+00:00"}]),
            }],
        }

    def test_compilation_creates_hierarchy_trust_ledger_and_valid_output(self):
        job = self.job()
        summary = intelligence.compile_job(job)
        row = job["rows"][0]
        self.assertEqual(3, summary["schema_version"])
        self.assertTrue(row["parent_brand_id"].startswith("brand-"))
        self.assertTrue(row["operating_entity_id"].startswith("operating-"))
        self.assertTrue(json.loads(row["evidence_ids"]))
        output = json.loads(row["compiler_output"])
        self.assertEqual("mx_only", output["contact_readiness"]["deliverability_state"])
        memory = intelligence.entity(row["entity_id"])
        self.assertEqual(1, len(memory["operating_entities"]))
        self.assertTrue(memory["evidence_claims"][0]["trust_score"] > 0)

    def test_invalid_ai_citation_is_rejected(self):
        ledger = [evidence_compiler.evidence_claim("c", "o", "j", {"field": "service", "value": "Roof repair", "url": "https://a.test", "basis": "page_text"}, "2026-10-24T00:00:00+00:00")]
        output = evidence_compiler.deterministic_output("c", "o", ledger, {}, "contact_discovery", "Missing contact", [], False)
        output["compiled_claims"] = [{"claim_type": "service_offering", "statement": "Invented", "verification_status": "verified_observation", "confidence_score": 1, "source_evidence_ids": ["missing"], "verbatim_excerpt": "Invented"}]
        with self.assertRaises(ValueError):
            evidence_compiler.validate_output(output, ledger)

    def test_email_citation_cannot_support_negative_leadership_claim(self):
        ledger = [evidence_compiler.evidence_claim("c", "o", "j", {"field": "email", "value": "info@acme.test", "url": "https://acme.test", "basis": "mailto link"}, "2026-10-24T00:00:00+00:00")]
        output = evidence_compiler.deterministic_output("c", "o", ledger, {}, "manual_browser_review", "Review", [], False)
        output["compiled_claims"] = [{"claim_type": "leadership_change", "statement": "No evidence of leadership change was observed.", "verification_status": "verified_observation", "confidence_score": 1, "source_evidence_ids": [ledger[0]["evidence_id"]], "verbatim_excerpt": "info@acme.test"}]
        with self.assertRaisesRegex(ValueError, "negative claim"):
            evidence_compiler.validate_output(output, ledger)

    def test_domain_dnc_and_catch_all_block_preflight(self):
        intelligence.add_dnc("domain", "blocked.test", "Requested no contact")
        self.assertFalse(intelligence.preflight({}, "person@blocked.test")["eligible"])
        intelligence.record_email_verification({"email": "owner@catch.test", "status": "catch_all", "provider": "official-provider"})
        self.assertFalse(intelligence.preflight({}, "owner@catch.test")["eligible"])

    def test_sequence_halts_on_reply(self):
        sequence_engine.create("roof-followup", [{"delay_days": 0, "subject": "Hello", "body": "Initial"}, {"delay_days": 3, "subject": "Following up", "body": "Follow-up"}])
        state_id = sequence_engine.enroll("roof-followup", "campaign", "company", "operating", "owner@acme.test")
        self.assertEqual(1, sequence_engine.apply_outcome("company", "owner@acme.test", "replied"))
        with engine.connection() as conn:
            state = conn.execute("SELECT state FROM outreach_sequence_states WHERE id=?", (state_id,)).fetchone()[0]
        self.assertEqual("halted", state)

    def test_referral_creates_unverified_contact_and_contact_discovery_task(self):
        with engine.connection() as conn:
            conn.execute(
                "INSERT INTO intelligence_companies(id,name,domain,phone,address,city,niche,payload,first_seen,last_seen) VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("company-referral", "Acme", "acme.test", "", "", "Dallas", "Roofing", "{}", "2026-10-24T00:00:00+00:00", "2026-10-24T00:00:00+00:00"),
            )
        intelligence.record_outcome({
            "company_id": "company-referral",
            "email": "old@acme.test",
            "outcome": "referral",
            "referred_name": "Alex Smith",
            "referred_email": "alex@acme.test",
        })
        with engine.connection() as conn:
            contact = conn.execute("SELECT status,confidence FROM intelligence_contacts WHERE company_id=? AND email=?", ("company-referral", "alex@acme.test")).fetchone()
            queue = conn.execute("SELECT action FROM intelligence_queue WHERE company_id=?", ("company-referral",)).fetchone()
        self.assertEqual(("referred_unverified", 20), contact)
        self.assertEqual("contact_discovery", queue[0])

    def test_inferred_permutation_is_never_recommended(self):
        row = {"decision_maker": "Jane Doe"}
        inferred = organizer.inferred_permutations(row, ["alex.smith@acme.test"])
        self.assertEqual("jane.doe@acme.test", inferred[0]["email"])
        self.assertFalse(inferred[0]["recommended"])


if __name__ == "__main__":
    unittest.main()
