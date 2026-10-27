import tempfile
import unittest
from pathlib import Path

import leadfinder


class LeadFinderTests(unittest.TestCase):
    def test_deduplicate_merges_fields(self):
        one = leadfinder.Lead(
            name="Acme", phone="+1 555 0100", website="https://acme.test"
        )
        two = leadfinder.Lead(
            name="Acme LLC", email="info@acme.test", website="https://acme.test"
        )
        rows = leadfinder.deduplicate([one, two])
        self.assertEqual(1, len(rows))
        self.assertEqual("info@acme.test", rows[0].email)

    def test_score_rewards_contacts(self):
        full = leadfinder.Lead(
            name="A", phone="1", email="a@example.com", website="https://example.com"
        )
        empty = leadfinder.Lead(name="B")
        self.assertGreater(leadfinder.score(full), leadfinder.score(empty))

    def test_directory_title_is_cleaned_before_deduplication(self):
        lead = leadfinder.Lead(
            name="Acme Dental in Dallas, TX | Chamber of Commerce",
            city="Dallas, TX",
        )
        self.assertEqual("Acme Dental", lead.name)

    def test_multi_listing_phone_container_is_discarded(self):
        container = leadfinder.Lead(
            name="Acme 214-555-0100 Beta 214-555-0101",
            website="https://directory.test/list",
        )
        self.assertEqual([], leadfinder.deduplicate([container]))
        self.assertIn("multi_listing_phone_container", container.quality_flags)

    def test_unbounded_entity_title_is_discarded(self):
        container = leadfinder.Lead(name="A" * 81)
        self.assertEqual([], leadfinder.deduplicate([container]))

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.csv"
            leadfinder.export([leadfinder.Lead(name="A")], target, "csv")
            self.assertIn("name", target.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
