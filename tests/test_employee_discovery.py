import unittest
from unittest.mock import patch

import employee_discovery


class EmployeeDiscoveryTests(unittest.TestCase):
    def test_visible_headline_gets_title_role_seniority_and_tags(self):
        profile = employee_discovery._classify_profile(
            {
                "employee_name": "Example Person",
                "headline": "Head of Talent Acquisition | Technology Hiring | Singapore",
            }
        )
        self.assertEqual("Head of Talent Acquisition", profile["title"])
        self.assertEqual("recruitment_talent", profile["role_group"])
        self.assertEqual("director_head", profile["seniority"])
        self.assertEqual("high", profile["outreach_priority"])
        self.assertIn("decision_maker", profile["role_tags"])

    def test_school_headline_is_not_invented_as_a_job_title(self):
        profile = employee_discovery._classify_profile(
            {"headline": "Tunku Abdul Rahman University Management and Technology"}
        )
        self.assertEqual("", profile["title"])
        self.assertEqual("education_student", profile["role_group"])
        self.assertEqual("headline_only", profile["title_status"])

    def test_settings_keep_only_verified_unique_company_pages(self):
        job = {
            "status": "complete",
            "rows": [
                {
                    "name": "Acme",
                    "linkedin": "https://www.linkedin.com/company/acme/",
                },
                {
                    "name": "Acme duplicate",
                    "linkedin": "https://www.linkedin.com/company/acme/?trk=dup",
                },
                {
                    "name": "Person page is not a company",
                    "linkedin": "https://www.linkedin.com/in/person/",
                },
            ],
        }
        companies, per_company = employee_discovery._settings(
            job, {"company_limit": 1000, "per_company": 1000}
        )
        self.assertEqual(1, len(companies))
        self.assertEqual("https://www.linkedin.com/company/acme/", companies[0]["linkedin"])
        self.assertEqual(100, per_company)

    def test_employee_sheet_sync_retains_error_without_losing_profiles(self):
        job = {"employees": [{"employee_linkedin": "https://www.linkedin.com/in/a/"}]}
        task = {}
        with (
            patch.object(
                employee_discovery.connections,
                "statuses",
                return_value={"providers": [{"id": "google_sheets", "connected": True}]},
            ),
            patch.object(
                employee_discovery.connections,
                "sync_employee_sheet",
                side_effect=ValueError("temporary Sheets error"),
            ),
        ):
            employee_discovery._sync(job, task)
        self.assertEqual("error", task["sheet_status"])
        self.assertIn("temporary Sheets error", task["sheet_error"])
        self.assertEqual(1, len(job["employees"]))

    def test_company_website_bio_becomes_manual_linkedin_review(self):
        import json

        row = {
            "decision_maker": "Jane Doe",
            "decision_maker_role": "Head of Talent Acquisition",
            "checked_at": "2026-11-10T00:00:00Z",
            "evidence": json.dumps([{
                "field": "email", "value": "jane@example.com", "url": "https://example.com/team",
                "contact_name": "Jane Doe", "contact_role": "Head of Talent Acquisition",
                "excerpt": "Jane Doe — Head of Talent Acquisition", "observed_at": "2026-11-10T00:00:00Z",
            }]),
        }
        profiles = employee_discovery._website_people(row, {"name": "Example Co", "city": "Dallas", "website": "https://example.com", "linkedin": "https://www.linkedin.com/company/example/"})
        self.assertEqual(1, len(profiles))
        self.assertTrue(profiles[0]["manual_review_required"])
        self.assertIn("linkedin.com/search/results/people", profiles[0]["manual_search_url"])
        self.assertFalse(profiles[0].get("employee_linkedin"))

    def test_company_bio_must_match_configured_niche_role(self):
        import json

        row = {
            "evidence": json.dumps([{
                "contact_name": "Jane Doe",
                "contact_role": "Senior Operations Manager",
                "url": "https://example.com/team",
            }]),
        }
        profiles = employee_discovery._website_people(
            row,
            {"name": "Example Co", "city": "Dallas", "website": "https://example.com"},
            ["owner", "operations manager"],
        )
        self.assertEqual(1, len(profiles))
        self.assertEqual("Jane Doe", profiles[0]["employee_name"])
        self.assertEqual("operations manager", profiles[0]["configured_role"])
        self.assertTrue(profiles[0]["niche_role_match"])

    def test_unconfigured_published_role_becomes_generic_manual_review(self):
        import json

        row = {
            "decision_maker": "Alex Smith",
            "decision_maker_role": "Marketing Coordinator",
            "evidence": json.dumps([{
                "contact_name": "Alex Smith",
                "contact_role": "Marketing Coordinator",
                "url": "https://example.com/team",
            }]),
        }
        profiles = employee_discovery._website_people(
            row,
            {"name": "Example Co", "city": "Dallas", "website": "https://example.com"},
            ["owner", "operations manager"],
        )
        self.assertEqual(1, len(profiles))
        self.assertEqual("Decision maker review", profiles[0]["employee_name"])
        self.assertEqual("manual_linkedin_review_no_published_company_bio", profiles[0]["basis"])


if __name__ == "__main__":
    unittest.main()
