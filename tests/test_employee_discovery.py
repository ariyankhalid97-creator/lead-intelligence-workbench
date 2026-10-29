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


if __name__ == "__main__":
    unittest.main()
