import json
import unittest
from unittest.mock import patch

import local_ai
import organizer


class OrganizerTests(unittest.TestCase):
    def test_support_and_automated_are_excluded_but_general_is_recommended(self):
        with patch.object(local_ai, "status", return_value={"available": False}):
            rows, summary = organizer.organize_rows([
                {"name": "A", "email": "support@example.com", "emails": "support@example.com; info@example.com; noreply@example.com", "evidence": "[]"}
            ])
        quality = json.loads(rows[0]["email_quality"])
        self.assertEqual("info@example.com", rows[0]["email"])
        self.assertEqual(["general_business"], [item["type"] for item in quality["recommended"] if item["email"] == "info@example.com"])
        self.assertEqual({"support", "automated"}, {item["type"] for item in quality["excluded"]})
        self.assertEqual("not_tested", quality["recommended"][0]["deliverability"])
        self.assertEqual(1, summary["recommended_email_records"])

    def test_exact_duplicates_are_consolidated_with_source_ledger(self):
        rows = [
            {"name": "Acme Roof", "address": "1 Main St", "city": "Dallas", "email": "hello@acme.test", "source": "maps", "source_url": "https://maps.test/a", "evidence": "[]", "verification": "{}"},
            {"name": "Acme Roof", "address": "1 Main St", "city": "Dallas", "email": "hello@acme.test", "source": "web", "source_url": "https://acme.test", "evidence": "[]", "verification": "{}"},
        ]
        with patch.object(local_ai, "status", return_value={"available": False}):
            organized, summary = organizer.organize_rows(rows)
        self.assertEqual(1, len(organized))
        self.assertEqual(1, summary["duplicates_consolidated"])
        self.assertEqual("same_published_email_and_identity", json.loads(organized[0]["duplicate_summary"])[0]["reason"])

    def test_same_email_different_business_is_not_merged(self):
        rows = [
            {"name": "Branch One", "address": "1 Main", "email": "office@group.test", "evidence": "[]"},
            {"name": "Branch Two", "address": "2 Main", "email": "office@group.test", "evidence": "[]"},
        ]
        with patch.object(local_ai, "status", return_value={"available": False}):
            organized, summary = organizer.organize_rows(rows)
        self.assertEqual(2, len(organized))
        self.assertEqual(0, summary["duplicates_consolidated"])

    def test_domain_without_mail_route_and_automated_address_are_not_selected(self):
        verification = {"email_candidates": [
            {"email": "owner@dead.test", "status": "no_mail_route_observed"},
            {"email": "hello@live.test", "status": "mx_present"},
        ]}
        with patch.object(local_ai, "status", return_value={"available": False}):
            rows, _ = organizer.organize_rows([{
                "name": "A", "email": "owner@dead.test", "emails": "owner@dead.test; hello@live.test; noreply@live.test",
                "evidence": "[]", "verification": json.dumps(verification),
            }])
        quality = json.loads(rows[0]["email_quality"])
        self.assertEqual("hello@live.test", rows[0]["email"])
        self.assertEqual("domain_unsendable", next(item for item in quality["excluded"] if item["email"] == "owner@dead.test")["deliverability"])
        self.assertFalse(any(item["email"] == "noreply@live.test" for item in quality["recommended"]))


if __name__ == "__main__":
    unittest.main()
