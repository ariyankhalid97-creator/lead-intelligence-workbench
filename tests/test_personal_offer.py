import unittest

import personal_offer


class PersonalOfferTests(unittest.TestCase):
    def test_esignature_workflow_has_three_researched_use_cases(self):
        plan = personal_offer.plan("electronic signature workflow", "MY")
        self.assertEqual(3, len(plan["segments"]))
        self.assertEqual("property management companies", plan["selected_segment"])
        self.assertIn("WhatsApp", plan["country_fit_note"])
        self.assertEqual(8, len(plan["search_approaches"]))

    def test_each_use_case_has_terms_roles_documents_and_boundary(self):
        for segment in personal_offer.ESIGNATURE_USE_CASES:
            with self.subTest(segment=segment["niche"]):
                plan = personal_offer.plan("electronic signature workflow", "SG", segment["niche"])
                self.assertGreaterEqual(len(plan["phrases"]), 8)
                self.assertGreaterEqual(len(plan["decision_roles"]), 6)
                self.assertGreaterEqual(len(plan["documents"]), 7)
                self.assertTrue(plan["legal_boundary"])

    def test_real_estate_plan_excludes_conveyancing_pitch(self):
        plan = personal_offer.plan("electronic signature workflow", "AU", "property management companies")
        self.assertIn("conveyancing", plan["legal_boundary"])
        self.assertIn("property management service agreements", plan["documents"])


if __name__ == "__main__":
    unittest.main()
