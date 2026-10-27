import json
import unittest
from types import SimpleNamespace

import prospecting


class ProspectingTests(unittest.TestCase):
    def lead(self, **values):
        return SimpleNamespace(
            website="https://business.test",
            workflow_signals="[]",
            decision_maker="",
            decision_maker_role="",
            observations="[]",
            assumptions="[]",
            email="",
            phone="",
            **values,
        )

    def test_profile_metadata_is_explicit_and_not_mutable_shared_state(self):
        self.assertEqual(
            100,
            sum(prospecting.profile_metadata("hood_automation")["weights"].values()),
        )
        result = prospecting.profile_metadata("hood_automation")
        result["weights"]["pain"] = 0
        self.assertEqual(
            25, prospecting.profile_metadata("hood_automation")["weights"]["pain"]
        )
        with self.assertRaises(ValueError):
            prospecting.profile_metadata("invented")

    def test_general_collects_signals_without_scoring_offer(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "We provide hood cleaning and written reports with before and after photos. We use Jobber.",
            lead.website,
        )
        prospecting.assess(lead)
        self.assertEqual("not_requested", json.loads(lead.opportunity)["status"])
        self.assertEqual(0, lead.opportunity_score)
        self.assertIn(
            "software", {r["kind"] for r in json.loads(lead.workflow_signals)}
        )
        self.assertTrue(json.loads(lead.assumptions))

    def test_plain_reports_software_or_missing_tools_never_prove_manual_or_gap(self):
        for text in (
            "Written reports and photos are provided after every job.",
            "Our team uses Jobber.",
            "We offer hood cleaning.",
        ):
            lead = self.lead()
            prospecting.collect_signals(lead, text, lead.website)
            prospecting.assess(lead, "hood_automation")
            dimensions = json.loads(lead.opportunity)["dimensions"]
            self.assertIsNone(dimensions["pain"]["value"])
            self.assertIsNone(dimensions["underserved"]["value"])
            self.assertIsNone(dimensions["capacity"]["value"])

    def test_no_evidence_is_unknown_not_midpoint(self):
        lead = self.lead()
        prospecting.assess(lead, "hood_automation")
        opportunity = json.loads(lead.opportunity)
        self.assertEqual("not_enough_evidence", opportunity["status"])
        self.assertEqual(0, opportunity["supported_points"])
        self.assertEqual(0, opportunity["coverage"])
        self.assertTrue(
            all(d["value"] is None for d in opportunity["dimensions"].values())
        )

    def test_weighted_arithmetic_and_published_capacity_caveat(self):
        lead = self.lead()
        lead.email, lead.phone = "info@business.test", "+12145550123"
        text = "Hood cleaning since 1986. We manually prepare reports and quotes. Before and after photos. Hinge kits and maintenance plans. Jay Tully, Owner."
        prospecting.collect_signals(lead, text, lead.website)
        prospecting.assess(lead, "hood_automation")
        opportunity = json.loads(lead.opportunity)
        values = {k: d["value"] for k, d in opportunity["dimensions"].items()}
        self.assertEqual(
            {"pain": 8, "fit": 10, "access": 9, "capacity": 7, "underserved": 7}, values
        )
        self.assertEqual(82.5, opportunity["supported_points"])
        self.assertEqual(100, opportunity["coverage"])
        self.assertIn(
            "ability to pay are unknown",
            opportunity["dimensions"]["capacity"]["reason"],
        )

    def test_portal_or_automated_reporting_is_counter_signal_not_jobber_alone(self):
        for text, value in (
            ("We use Jobber.", None),
            ("Visit our customer portal.", 3),
            ("Automated reports are available.", 1),
        ):
            lead = self.lead()
            prospecting.collect_signals(lead, text, lead.website)
            prospecting.assess(lead, "hood_automation")
            self.assertEqual(
                value,
                json.loads(lead.opportunity)["dimensions"]["underserved"]["value"],
            )

    def test_explicit_manual_signal_persists_beyond_observation_cap(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "We manually assemble every report after cleaning.",
            lead.website + "/workflow",
        )
        original = json.loads(lead.workflow_signals)
        lead.observations = json.dumps([{"text": "unrelated"}] * 8)
        for _ in range(3):
            prospecting.assess(lead, "hood_automation")
            prospecting.collect_signals(
                lead, "Some other page.", lead.website + "/contact"
            )
        self.assertEqual(original, json.loads(lead.workflow_signals))
        self.assertEqual(8, json.loads(lead.opportunity)["dimensions"]["pain"]["value"])
        self.assertTrue(
            all(
                r["url"] and r["excerpt"] and r["basis"] == "published_page_claim"
                for r in original
            )
        )

    def test_negated_manual_workflow_is_not_collected(self):
        for text in (
            "No manual reports.",
            "Our software eliminates manual reports.",
            "Reports are generated without manual preparation.",
            "We do not manually prepare reports.",
        ):
            lead = self.lead()
            prospecting.collect_signals(lead, text, lead.website)
            self.assertNotIn(
                "manual_workflow",
                {r["kind"] for r in json.loads(lead.workflow_signals)},
                text,
            )

    def test_negated_portal_is_not_a_solved_workflow_claim(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead, "We do not have a customer portal or automated reports.", lead.website
        )
        prospecting.assess(lead, "hood_automation")
        self.assertIsNone(
            json.loads(lead.opportunity)["dimensions"]["underserved"]["value"]
        )

    def test_negated_hood_service_and_automated_reports_are_not_positive(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "We do not offer hood cleaning. We do not provide automated reports. No customer portal.",
            lead.website,
        )
        kinds = {r["kind"] for r in json.loads(lead.workflow_signals)}
        self.assertNotIn("hood_service", kinds)
        self.assertNotIn("automated_reporting", kinds)
        self.assertNotIn("customer_portal", kinds)

    def test_competitor_manual_paperwork_is_not_our_pain(self):
        for text in (
            "Our competitors manually prepare reports.",
            "Other companies manually assemble quotes.",
            "Our customers manually write reports.",
        ):
            lead = self.lead()
            prospecting.collect_signals(lead, text, lead.website)
            self.assertNotIn(
                "manual_workflow",
                {r["kind"] for r in json.loads(lead.workflow_signals)},
                text,
            )
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "Unlike competitors, we manually prepare reports for every client.",
            lead.website,
        )
        self.assertIn(
            "manual_workflow", {r["kind"] for r in json.loads(lead.workflow_signals)}
        )

    def test_manual_cleaning_and_reports_do_not_prove_manual_paperwork(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "We perform manual cleaning and provide service reports after each job.",
            lead.website,
        )
        self.assertNotIn(
            "manual_workflow", {r["kind"] for r in json.loads(lead.workflow_signals)}
        )

    def test_named_owner_requires_explicit_role_first_party_and_real_name(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "Contact Us. Owner Login. John Smith Hood Cleaning. johnsmith@business.test",
            lead.website,
        )
        self.assertEqual("", lead.decision_maker)
        prospecting.collect_signals(
            lead,
            "Jay Tully, Owner / Main Technician.",
            "https://directory.test/business",
        )
        self.assertEqual("", lead.decision_maker)
        prospecting.collect_signals(
            lead, "Jay Tully, Owner / Main Technician.", lead.website + "/about"
        )
        self.assertEqual("Jay Tully", lead.decision_maker)
        self.assertEqual("Owner", lead.decision_maker_role)

    def test_structured_person_requires_supported_role_and_name(self):
        lead = self.lead()
        prospecting.collect_signals(
            lead,
            "",
            lead.website,
            structured_people=[
                {"name": "Contact Us", "role": "Owner"},
                {"name": "Jane Doe", "role": "Technician"},
            ],
        )
        self.assertEqual("", lead.decision_maker)
        prospecting.collect_signals(
            lead,
            "",
            lead.website,
            structured_people=[{"name": "Jane Doe", "role": "Owner"}],
        )
        self.assertEqual("Jane Doe", lead.decision_maker)

    def test_signal_storage_is_bounded_and_idempotent(self):
        lead = self.lead()
        text = "Hood cleaning since 2000. Written reports. We manually prepare quotes. Jobber. Jay Tully, Owner."
        for i in range(20):
            prospecting.collect_signals(lead, text, lead.website + "/" + str(i))
        self.assertLessEqual(len(json.loads(lead.workflow_signals)), 24)
        before = lead.workflow_signals
        prospecting.collect_signals(lead, text, lead.website + "/0")
        self.assertEqual(before, lead.workflow_signals)


if __name__ == "__main__":
    unittest.main()
