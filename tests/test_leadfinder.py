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

    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "out.csv"
            leadfinder.export([leadfinder.Lead(name="A")], target, "csv")
            self.assertIn("name", target.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
