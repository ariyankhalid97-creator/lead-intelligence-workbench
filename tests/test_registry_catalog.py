import unittest

import registry_catalog


class RegistryCatalogTests(unittest.TestCase):
    def test_catalog_covers_all_supported_countries(self):
        metadata = registry_catalog.metadata()
        self.assertEqual(
            ["Australia", "Malaysia", "Singapore", "United States"],
            metadata["countries"],
        )
        self.assertGreaterEqual(len(metadata["directories"]), 10)

    def test_country_and_niche_filters_are_combined(self):
        rows = registry_catalog.list_directories("United States", "healthcare", "")
        self.assertEqual(["us-npi"], [row["id"] for row in rows])

    def test_restricted_directories_are_not_mislabeled_free(self):
        rows = registry_catalog.list_directories("Malaysia")
        self.assertTrue(rows)
        self.assertTrue(all("paid" in row["access"] for row in rows))


if __name__ == "__main__":
    unittest.main()
