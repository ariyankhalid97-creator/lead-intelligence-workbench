import json
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import contacts
import discovery
import engine
import leadfinder as lf
import research


class ResearchWorkflowTests(unittest.TestCase):
    def params(self, **kwargs):
        return engine.validate(
            {
                "niche": "Hood Cleaning",
                "location": "Dallas, Texas",
                "source": "web",
                "limit": 20,
                **kwargs,
            }
        )

    def test_state_and_usa_sampling_are_explicit_and_bounded(self):
        plan = discovery.plan("hood cleaning")
        strategy = research.strategy(plan, self.params(coverage="usa", query_budget=12))
        self.assertEqual(50, len(strategy["locations"]))
        self.assertEqual(12, len(strategy["queries"]))
        self.assertGreater(len(strategy["unsearched_locations"]), 0)
        self.assertIn("individual", {q["intent"] for q in strategy["queries"]})
        self.assertIn("business", {q["intent"] for q in strategy["queries"]})
        texas = research.expand_locations(["TX"], "states")
        self.assertIn("Dallas, Texas, USA", texas)
        self.assertGreater(len(texas), 1)

    def test_individual_search_is_not_just_a_business_query(self):
        strategy = research.strategy(
            discovery.plan("web design"),
            self.params(niche="web design", target="individuals"),
        )
        queries = strategy["queries"]
        self.assertTrue(any("freelance" in q["query"] for q in queries))
        self.assertTrue(any("upwork.com" in q["query"] for q in queries))
        self.assertNotIn("business", {q["intent"] for q in queries})

    def test_tedt_profile_is_opt_in_and_within_query_budget(self):
        params = self.params(research_profile="hood_automation", query_budget=8)
        schedule = research.strategy(discovery.plan(params["niche"]), params)
        self.assertEqual(8, len(schedule["queries"]))
        self.assertEqual(
            {
                "business",
                "individual",
                "workflow_research",
                "profile",
                "platform_research",
            },
            {q["intent"] for q in schedule["queries"]},
        )
        self.assertEqual(100, sum(schedule["research_profile"]["weights"].values()))
        generic = research.strategy(
            discovery.plan("roofing"), self.params(niche="roofing")
        )
        self.assertFalse(
            any(q["intent"] == "workflow_research" for q in generic["queries"])
        )
        with self.assertRaises(ValueError):
            self.params(niche="web design", research_profile="hood_automation")

    def test_shared_contact_is_review_signal_not_automatic_exclusion(self):
        rows = [
            lf.Lead(name="One", website="https://one.test", email="office@shared.test"),
            lf.Lead(name="Two", website="https://two.test", email="office@shared.test"),
        ]
        for row in rows:
            research.analyze(row, discovery.plan("cleaning"))
        report = research.quality_review(rows)
        self.assertEqual(1, len(report["shared_operator_signals"]))
        self.assertEqual(
            2, report["missing_or_weak"]["possible_shared_operator_review"]
        )
        self.assertEqual(2, len(rows))

    def test_opportunity_order_retains_provider_and_city_diversity(self):
        rows = [
            lf.Lead(name="High", city="Dallas", opportunity_score=90),
            lf.Lead(name="Low", city="Dallas", opportunity_score=10),
            lf.Lead(
                name="Person",
                city="Dallas",
                discovery_intent="individual",
                opportunity_score=5,
            ),
            lf.Lead(name="Austin", city="Austin", opportunity_score=30),
        ]
        chosen = research.balanced_select(rows, 3, prefer_opportunity=True)
        self.assertEqual({"High", "Person", "Austin"}, {r.name for r in chosen})

    def test_owner_operated_is_not_proof_of_solo(self):
        lead = lf.Lead(name="Local Hood Company", city="Dallas")
        research.add_observation(
            lead,
            "page",
            "We are an owner-operated hood cleaning business.",
            "https://business.test/about",
            "page_text",
        )
        research.analyze(lead, discovery.plan("hood cleaning"))
        self.assertEqual("independent_business", lead.operator_type)
        self.assertEqual("self_reported", lead.operator_confidence)
        self.assertNotEqual("solo_provider", lead.operator_type)

    def test_query_or_personal_looking_name_never_confirms_independence(self):
        lead = lf.Lead(
            name="John Smith Hood Cleaning",
            discovery_query="owner operated hood cleaning Dallas",
        )
        research.analyze(lead, discovery.plan("hood cleaning"))
        self.assertEqual("unknown", lead.operator_type)
        self.assertIn("operator_unconfirmed", json.loads(lead.quality_flags))

    def test_solo_chain_agency_and_conflicts_have_evidence(self):
        for text, expected in [
            ("I work alone as a cleaner.", "solo_provider"),
            ("Explore our franchise opportunities.", "chain_or_franchise"),
            ("We are a digital agency.", "agency"),
            ("Not a franchise. Locally owned and operated.", "independent_business"),
            ("We are family-owned with locations nationwide.", "unknown"),
        ]:
            lead = lf.Lead(name="Company")
            research.add_observation(
                lead, "page", text, "https://business.test/about", "page_text"
            )
            research.analyze(lead, discovery.plan("cleaning"))
            self.assertEqual(expected, lead.operator_type, text)
            self.assertTrue(json.loads(lead.operator_evidence))

    def test_snippet_claim_is_distinct_from_observed_contact(self):
        lead = lf.Lead(
            name="Company",
            source="web",
            evidence=json.dumps(
                [
                    {
                        "field": "email",
                        "value": "info@business.test",
                        "url": "https://business.test/contact",
                        "method": "mailto link",
                    }
                ]
            ),
        )
        research.add_observation(
            lead,
            "search",
            "Owner-operated hood cleaning",
            "https://business.test",
            "search_snippet",
        )
        research.analyze(lead, discovery.plan("hood cleaning"))
        self.assertEqual("snippet_only", lead.operator_confidence)
        self.assertEqual(
            {"snippet_claim", "observed_published"},
            {f["status"] for f in json.loads(lead.facts)},
        )

    def test_public_seller_profiles_survive_directory_filter_without_cross_merging(
        self,
    ):
        data = [
            {
                "title": "Jane Hood Cleaning",
                "href": "https://www.thumbtack.com/tx/dallas/cleaning/jane/service/111",
                "body": "Hood cleaning services in Dallas",
            },
            {
                "title": "Alex Hood Cleaning",
                "href": "https://www.thumbtack.com/tx/dallas/cleaning/alex/service/222",
                "body": "Hood cleaning services in Dallas",
            },
            {
                "title": "Dallas providers",
                "href": "https://www.thumbtack.com/tx/dallas/cleaning",
                "body": "directory",
            },
        ]
        fake = SimpleNamespace(
            DDGS=lambda **kwargs: SimpleNamespace(text=lambda *args, **kwargs: data)
        )
        search = {
            **discovery.plan("hood cleaning"),
            "web_queries": [
                {
                    "query": "site:thumbtack.com hood cleaning Dallas",
                    "intent": "profile",
                }
            ],
        }
        with patch.dict(sys.modules, {"ddgs": fake}):
            rows = discovery.web_search(
                search, "Dallas", 10, threading.Event(), lambda *args, **kwargs: None
            )
        self.assertEqual(2, len(lf.deduplicate(rows)))
        self.assertTrue(all(r.profile_url and not r.website for r in rows))
        client = SimpleNamespace(
            get=lambda url: (_ for _ in ()).throw(
                AssertionError("Do not scrape platform corporate contacts")
            )
        )
        contacts.enrich(
            rows[0], client, threading.Event(), lambda *args, **kwargs: None
        )
        self.assertEqual("platform_profile_only", rows[0].contact_status)

    def test_quality_and_diversity_keep_missing_data_and_possible_duplicates_visible(
        self,
    ):
        a = lf.Lead(
            name="Acme LLC", city="Dallas", source="web", match_status="candidate"
        )
        b = lf.Lead(
            name="Acme", city="Dallas", source="web", source_url="https://other.test"
        )
        research.analyze(a, discovery.plan("hood cleaning"))
        research.analyze(b, discovery.plan("hood cleaning"))
        report = research.quality_review([a, b])
        self.assertEqual(1, len(report["possible_duplicates"]))
        self.assertEqual(2, report["missing_or_weak"]["missing_phone"])
        people = lf.Lead(
            name="Independent professional",
            city="Dallas",
            discovery_intent="individual",
        )
        more = lf.Lead(name="Another company", city="Dallas")
        selected = research.balanced_select([a, more, people], 2)
        self.assertIn(people, selected)


if __name__ == "__main__":
    unittest.main()
