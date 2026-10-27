import csv
import json
import sqlite3
import tempfile
import sys
from types import SimpleNamespace
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import contacts
import discovery
import engine
import leadfinder as lf
import dashboard
import niche_catalog
import public_sources
import prospecting


class QualityTests(unittest.TestCase):
    def test_curated_niche_memory_contains_200_editable_search_packs(self):
        self.assertEqual(200, len(niche_catalog.entries()))
        planned = discovery.plan("roof repair")
        self.assertIn("roofer", planned["phrases"])
        self.assertIn("roof replacement", planned["phrases"])

    def test_platform_planner_matches_b2b_and_startup_sources(self):
        params = engine.validate(
            {
                "niche": "software development agencies",
                "location": "Austin, Texas",
                "source": "hybrid",
            }
        )
        prepared = engine.strategy(discovery.plan(params["niche"]), params)
        domains = {item["domain"] for item in prepared["platforms"]}
        self.assertTrue(
            {
                "clutch.co",
                "goodfirms.co",
                "ycombinator.com",
                "producthunt.com",
                "betalist.com",
                "wellfound.com",
            }.issubset(domains)
        )

    def test_npi_provider_is_applicable_only_to_healthcare_terms(self):
        self.assertEqual("Dentist", public_sources.npi_taxonomy("pediatric dentists"))
        self.assertEqual("", public_sources.npi_taxonomy("roofing contractors"))

    def test_second_server_cannot_take_running_port(self):
        server = dashboard.LocalHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        try:
            with self.assertRaises(OSError):
                duplicate = dashboard.LocalHTTPServer(
                    server.server_address, dashboard.Handler
                )
                duplicate.server_close()
        finally:
            server.server_close()

    def test_hood_aliases_are_distinct_and_specific(self):
        plan = discovery.plan("Hood Cleaning")
        self.assertIn("kitchen exhaust cleaning", plan["phrases"])
        self.assertEqual(
            len(plan["phrases"]), len({p.casefold() for p in plan["phrases"]})
        )
        lead = lf.Lead(name="Dallas Maid Service", category="cleaning")
        discovery.relevance(lead, plan, "Dallas")
        self.assertEqual("candidate", lead.match_status)

    def test_specialized_word_matching_does_not_match_inside_neighborhood(self):
        lead = lf.Lead(
            name="Local dryer vent cleaners",
            category="Dryer vent cleaning service",
        )
        discovery.relevance(
            lead,
            discovery.plan("Hood Cleaning"),
            "Dallas",
            "Dryer vent cleaning throughout your neighborhood.",
        )
        self.assertEqual("candidate", lead.match_status)

    def test_animal_talent_requires_animal_and_talent_evidence(self):
        planned = discovery.plan("Animal Talent Agencies")
        generic = lf.Lead(name="Human Stars", category="Talent agency")
        discovery.relevance(
            generic, planned, "Dallas", "Actors and models for television"
        )
        self.assertEqual("candidate", generic.match_status)
        first_party = lf.Lead(name="Paws Casting", category="Talent agency")
        first_party.observations = json.dumps(
            [
                {
                    "basis": "page_text",
                    "text": "We provide trained animals and pet casting for film productions.",
                }
            ]
        )
        discovery.relevance(first_party, planned, "Dallas")
        self.assertEqual("service_match", first_party.match_status)
        listing = lf.Lead(name="Dognerd Animal Talent", category="Talent agency")
        discovery.relevance(listing, planned, "Dallas")
        self.assertEqual("category_match", listing.match_status)

    def test_generic_search_title_is_replaced_by_observed_page_brand(self):
        lead = lf.Lead(name="ABOUT")
        lead.observations = json.dumps(
            [
                {
                    "basis": "page_text",
                    "text": "ABOUT | HTM Animal Talent top of page CONTACT US",
                }
            ]
        )
        discovery.repair_generic_name(lead)
        self.assertEqual("HTM Animal Talent", lead.name)
        second = lf.Lead(name="FOR TALENT")
        second.observations = json.dumps(
            [
                {
                    "basis": "page_text",
                    "text": "FOR TALENT — THE DOG AGENCY ABOUT FOR BRANDS",
                }
            ]
        )
        discovery.repair_generic_name(second)
        self.assertEqual("THE DOG AGENCY", second.name)

    def test_balanced_maps_uses_aliases_and_applied_ai_tags(self):
        params = engine.validate(
            {
                "niche": "Hood Cleaning",
                "location": "Dallas, Texas",
                "source": "hybrid",
                "browser": True,
                "depth": "balanced",
                "phrases": "grease exhaust service",
                "query_budget": 24,
            }
        )
        search_plan = discovery.plan(params["niche"], params["phrases"])
        prepared = engine.strategy(search_plan, params)
        maps = [q for q in prepared["queries"] if q["channel"] == "browser"]
        self.assertIn(
            "grease exhaust service in Dallas, Texas",
            [q["query"] for q in maps],
        )
        self.assertGreater(len(maps), 1)

    def test_quick_maps_keeps_only_primary_phrase(self):
        params = engine.validate(
            {
                "niche": "Hood Cleaning",
                "location": "Dallas, Texas",
                "source": "hybrid",
                "browser": True,
                "depth": "quick",
                "phrases": "grease exhaust service",
            }
        )
        prepared = engine.strategy(
            discovery.plan(params["niche"], params["phrases"]), params
        )
        self.assertEqual(
            1, len([q for q in prepared["queries"] if q["channel"] == "browser"])
        )

    def test_food_export_rejects_generic_service_scaffolding(self):
        planned = discovery.plan(
            "Food Export",
            "Food Export contractor\nlocal Food Export\nindependent Food Export\nExport Certification",
        )
        self.assertEqual("food exporters", planned["phrases"][0])
        self.assertIn("food export companies", planned["phrases"])
        self.assertEqual(
            {
                "Food Export contractor",
                "local Food Export",
                "independent Food Export",
                "Export Certification",
            },
            {item["phrase"] for item in planned["rejected_phrases"]},
        )
        params = engine.validate(
            {
                "niche": "Food Export",
                "location": "Dallas, Texas",
                "source": "hybrid",
                "browser": True,
            }
        )
        prepared = engine.strategy(planned, params)
        self.assertEqual([], prepared["platforms"])
        self.assertIn(
            '"Food Export" trade association business directory',
            [item["query"] for item in prepared["queries"]],
        )
        self.assertNotIn(
            "contractor",
            " ".join(item["query"] for item in prepared["queries"]).casefold(),
        )

    def test_root_cause_report_preserves_exact_stop_and_merge_reasons(self):
        report = engine.root_cause_analysis(
            {"limit": 100},
            {
                "queries": [
                    {
                        "channel": "browser",
                        "query": "hood cleaning in Dallas",
                    }
                ]
            },
            {
                "browser": {"count": 32, "status": "complete", "successes": 1},
                "web": {
                    "count": 0,
                    "status": "failed",
                    "failures": 1,
                    "error": "No results found",
                },
            },
            [lf.Lead(name=f"Lead {i}") for i in range(30)],
            [
                {
                    "provider": "browser",
                    "message": "Opening Google Maps in dedicated Chrome",
                    "details": {"query": "hood cleaning in Dallas"},
                },
                {
                    "provider": "browser",
                    "message": "Maps scrolling stopped",
                    "details": {
                        "query": "hood cleaning in Dallas",
                        "reason": "no_new_links_after_three_scrolls",
                        "explanation": "Three checks added no links",
                        "links_collected": 32,
                    },
                },
            ],
            [
                {
                    "kept_name": "A",
                    "merged_name": "A LLC",
                    "reason": "same_normalized_phone",
                }
            ],
            4,
        )
        self.assertEqual(70, report["shortfall"])
        self.assertEqual("No results found", report["provider_failures"][0]["error"])
        self.assertEqual(
            "no_new_links_after_three_scrolls",
            report["maps"]["stop_events"][0]["reason"],
        )
        self.assertEqual(1, report["deduplication"]["merged_count"])

    def test_web_directory_is_not_returned_as_business(self):
        results = [
            {
                "title": "Hood Cleaning in Dallas",
                "href": "https://findhoodcleaner.com/states/texas/dallas-tx",
                "body": "directory",
            },
            {
                "title": "Acme Hood Cleaning",
                "href": "https://business.test",
                "body": "Hood cleaning in Dallas",
            },
        ]
        fake_ddgs = SimpleNamespace(
            DDGS=lambda **kwargs: SimpleNamespace(text=lambda *args, **kwargs: results)
        )
        with patch.dict(sys.modules, {"ddgs": fake_ddgs}):
            rows = discovery.web_search(
                discovery.plan("hood cleaning"),
                "Dallas, Texas",
                1,
                threading.Event(),
                lambda *args, **kwargs: None,
            )
        self.assertEqual(["Acme Hood Cleaning"], [row.name for row in rows])

    def test_web_media_domain_requires_business_schema(self):
        results = [
            {
                "title": "Acme profile in Dallas, TX | Dallas News",
                "href": "https://dallasnews.com/acme-profile",
                "body": "Hood cleaning in Dallas",
            }
        ]
        fake_ddgs = SimpleNamespace(
            DDGS=lambda **kwargs: SimpleNamespace(text=lambda *args, **kwargs: results)
        )
        with (
            patch.dict(sys.modules, {"ddgs": fake_ddgs}),
            patch(
                "discovery.fetch", return_value=b"<html><article>news</article></html>"
            ),
        ):
            rows = discovery.web_search(
                discovery.plan("hood cleaning"),
                "Dallas, Texas",
                5,
                threading.Event(),
                lambda *args, **kwargs: None,
            )
        self.assertEqual([], rows)

    def test_web_media_domain_allows_explicit_organization_schema(self):
        results = [
            {
                "title": "Acme Hood Cleaning in Dallas, TX | Dallas News",
                "href": "https://dallasnews.com/acme-profile",
                "body": "Hood cleaning in Dallas",
            }
        ]
        fake_ddgs = SimpleNamespace(
            DDGS=lambda **kwargs: SimpleNamespace(text=lambda *args, **kwargs: results)
        )
        document = b'<script type="application/ld+json">{"@type":"Organization","name":"Acme Hood Cleaning"}</script>'
        with (
            patch.dict(sys.modules, {"ddgs": fake_ddgs}),
            patch("discovery.fetch", return_value=document),
        ):
            rows = discovery.web_search(
                discovery.plan("hood cleaning"),
                "Dallas, Texas",
                5,
                threading.Event(),
                lambda *args, **kwargs: None,
            )
        self.assertEqual(["Acme Hood Cleaning"], [row.name for row in rows])

    def test_npi_secondary_waterfall_finds_practice_website(self):
        provider = lf.Lead(
            name="Jane Example",
            city="Dallas",
            source="npi_registry",
            source_id="1234567890",
        )
        fake_ddgs = SimpleNamespace(
            DDGS=lambda **kwargs: SimpleNamespace(
                text=lambda *args, **kwargs: [
                    {
                        "title": "Jane Example Family Dental",
                        "href": "https://janeexample.test",
                        "body": "Jane Example provides family dental care in Dallas.",
                    }
                ]
            )
        )
        with (
            patch.dict(sys.modules, {"ddgs": fake_ddgs}),
            patch("public_sources.time.sleep", return_value=None),
        ):
            rows = public_sources.npi_secondary_enrichment(
                [provider],
                "dentist",
                "Dallas, Texas",
                5,
                threading.Event(),
                lambda *args, **kwargs: None,
            )
        self.assertEqual("https://janeexample.test", rows[0].website)
        self.assertIn("secondary_web_discovery", rows[0].observations)

    def test_url_and_phone_merge_preserves_branches(self):
        merge_log = []
        rows = lf.deduplicate(
            [
                lf.Lead(
                    name="Same",
                    website="https://www.business.test/",
                    city="Dallas",
                    phone="+1 (214) 555-0100",
                ),
                lf.Lead(
                    name="Same LLC",
                    website="https://business.test/contact",
                    city="Dallas",
                    phone="2145550100",
                    email="contact@business.test",
                ),
                lf.Lead(
                    name="Same Austin",
                    website="https://business.test",
                    city="Austin",
                    address="3 Elm Street",
                ),
            ],
            merge_log=merge_log,
        )
        self.assertEqual(2, len(rows))
        self.assertEqual("contact@business.test", rows[0].email)
        self.assertEqual("same_normalized_phone", merge_log[0]["reason"])
        self.assertEqual("Same LLC", merge_log[0]["merged_name"])

    def test_contacts_have_evidence_and_ignore_script_noise(self):
        lead = lf.Lead(name="business.test", city="Dallas, Texas")
        document = """<script>let phone=1234567890; let x="fake@tracker.test";</script>
        <script type="application/ld+json">{"@graph":[{"@type":"LocalBusiness","name":"Kitchen Exhaust Co","telephone":"+1 214-555-0123","address":{"streetAddress":"10 Main","addressLocality":"Dallas"}}]}</script>
        <a href="mailto:info@business.test">Email</a><p>Call +1 214-555-0123</p>"""
        contacts.extract_document(document, "https://business.test/contact", lead)
        self.assertEqual("Kitchen Exhaust Co", lead.name)
        self.assertEqual("info@business.test", lead.email)
        self.assertNotIn("tracker", lead.emails)
        self.assertTrue(
            all(
                e["url"] == "https://business.test/contact"
                for e in json.loads(lead.evidence)
            )
        )
        self.assertTrue(lead.phone.startswith("+1"))

    def test_domain_keywords_alone_are_not_service_evidence(self):
        lead = lf.Lead(
            name="hoodcleaning.test",
            website="https://hoodcleaning.test",
            source="website_input",
        )
        discovery.relevance(lead, discovery.plan("hood cleaning"), "Dallas")
        self.assertEqual("candidate", lead.match_status)

    def test_us_state_locations_parse_domestic_phone_formats(self):
        for city in ("Phoenix, AZ", "Colorado Springs, Colorado", "Sacramento, CA"):
            lead = lf.Lead(
                name="Test business", city=city, website="https://business.test"
            )
            contacts.extract_document("<p>Call (480) 555-0123</p>", lead.website, lead)
            self.assertEqual("+14805550123", lead.phone, city)

    def test_empty_script_page_has_diagnostic_not_fake_first_party_evidence(self):
        lead = lf.Lead(
            name="business.test",
            website="https://business.test",
            source="website_input",
        )
        events = []
        client = SimpleNamespace(
            get=lambda url: (
                "<html><script>window.app = {};</script><body></body></html>",
                url,
            )
        )
        contacts.enrich(
            lead,
            client,
            threading.Event(),
            lambda *args, **kwargs: events.append((args, kwargs)),
        )
        engine.analyze(lead, discovery.plan("hood cleaning"))
        self.assertEqual("no_readable_content", lead.contact_status)
        self.assertEqual("unknown", lead.source_strength)
        self.assertEqual([], json.loads(lead.observations))
        self.assertTrue(any("no readable" in event[0][2] for event in events))

    def test_spreadsheet_formula_is_neutralized(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.csv"
            lf.export([lf.Lead(name='=HYPERLINK("bad")')], path, "csv")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                self.assertTrue(next(csv.DictReader(stream))["name"].startswith("'="))

    def test_legacy_database_migration_preserves_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "leads.db"
            conn = sqlite3.connect(path)
            conn.execute(
                "CREATE TABLE leads(identity TEXT PRIMARY KEY,name TEXT,updated_at TEXT)"
            )
            conn.execute("INSERT INTO leads VALUES('old','Original','yesterday')")
            conn.commit()
            conn.close()
            store = lf.Store(path)
            store.save([lf.Lead(name="New", city="Dallas")])
            self.assertEqual(
                2, store.db.execute("SELECT count(*) FROM leads").fetchone()[0]
            )
            store.close()

    def test_workflow_claims_survive_extraction_merge_and_reassessment(self):
        a = lf.Lead(name="Test company", website="https://business.test", city="Dallas")
        b = lf.Lead(name="Test company", website="https://business.test", city="Dallas")
        contacts.extract_document(
            "<p>Hood cleaning. We manually prepare reports. Jay Tully, Owner.</p>",
            a.website + "/about",
            a,
        )
        contacts.extract_document(
            '<script type="application/ld+json">{"@type":"LocalBusiness","founder":{"@type":"Person","name":"Jane Doe"}}</script><p>Hinge kits and maintenance plans.</p>',
            b.website + "/service",
            b,
        )
        row = lf.deduplicate([a, b])[0]
        prospecting.assess(row, "hood_automation")
        self.assertIn("repairs", {s["kind"] for s in json.loads(row.workflow_signals)})
        self.assertEqual(8, json.loads(row.opportunity)["dimensions"]["pain"]["value"])
        self.assertTrue(
            any(s["value"] == "Jane Doe" for s in json.loads(row.workflow_signals))
        )

    def test_input_validation_and_private_urls(self):
        for limit in (-1, 0, 501, True, "10"):
            with self.assertRaises(ValueError):
                engine.validate(
                    {"niche": "roofing", "location": "Dallas", "limit": limit}
                )
        with self.assertRaises(ValueError):
            contacts.public_url("http://127.0.0.1/admin")
        with self.assertRaises(ValueError):
            contacts.public_url("file:///etc/passwd")


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "replica").mkdir()
        (self.root / "replica" / "schema.sql").write_text(
            (engine.ROOT / "replica" / "schema.sql").read_text()
        )
        self.root_patch = patch.object(engine, "ROOT", self.root)
        self.db_patch = patch.object(engine, "DB", self.root / "data" / "jobs.db")
        self.root_patch.start()
        self.db_patch.start()
        engine.init()

    def tearDown(self):
        for handler in list(engine.LOG.handlers):
            handler.close()
            engine.LOG.removeHandler(handler)
        self.root_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def job(self, source="hybrid"):
        params = engine.validate(
            {
                "niche": "Hood Cleaning",
                "location": "Dallas, Texas",
                "source": source,
                "browser": False,
                "enrich": False,
                "limit": 10,
                "research_platforms": False,
            }
        )
        job = {
            "id": "test-job",
            "created_at": contacts.now(),
            "status": "queued",
            "params": params,
            "plan": discovery.plan(params["niche"]),
            "rows": [],
            "count": 0,
            "warnings": [],
            "providers": {},
            "stats": {},
        }
        engine.save(job)
        return job

    def test_failed_provider_keeps_successes_and_logs(self):
        job = self.job()
        job["params"]["niche"] = "Roofing"
        job["plan"] = discovery.plan("Roofing")
        engine.save(job)
        with (
            patch.object(lf, "osm_search", side_effect=RuntimeError("service timeout")),
            patch.object(
                engine,
                "web_search",
                return_value=[
                    lf.Lead(
                        name="Dallas Hood Cleaning",
                        website="https://business.test",
                        source="web",
                    )
                ],
            ),
        ):
            engine.run(job, threading.Event())
        result = engine.get_job(job["id"])
        self.assertEqual("partial", result["status"])
        self.assertEqual(1, result["count"])
        self.assertTrue(any(e["level"] == "error" for e in result["events"]))
        self.assertIsNotNone(engine.download(job["id"], "csv"))
        engine.init()
        self.assertEqual("partial", engine.get_job(job["id"])["status"])

    def test_zero_has_diagnosis(self):
        job = self.job("osm")
        with patch.object(lf, "osm_search", return_value=[]):
            engine.run(job, threading.Event())
        self.assertIn(
            "no dedicated OSM category", engine.get_job(job["id"])["diagnosis"]
        )

    def test_restart_marks_unfinished_job_interrupted(self):
        job = self.job()
        engine.init()
        self.assertEqual("interrupted", engine.get_job(job["id"])["status"])

    def test_cancel_retains_already_collected_website(self):
        job = self.job("osm")
        job["params"]["source"] = "websites"
        job["params"]["urls"] = "https://business.test"
        cancel = threading.Event()
        cancel.set()
        with patch.object(engine, "public_url", return_value="https://business.test"):
            engine.run(job, cancel)
        result = engine.get_job(job["id"])
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, result["count"])

    def test_multiple_locations_aggregate_provider_counts(self):
        job = self.job("osm")
        job["params"]["locations"] = ["Dallas, Texas", "Austin, Texas"]

        def search(niche, location, limit, emit):
            return [
                lf.Lead(
                    name="Hood cleaning " + location,
                    city=location,
                    source="openstreetmap",
                )
            ]

        with patch.object(lf, "osm_search", side_effect=search):
            engine.run(job, threading.Event())
        self.assertEqual(2, engine.get_job(job["id"])["providers"]["osm"]["count"])

    def test_library_recheck_keeps_geography_not_old_contacts_or_score(self):
        job = self.job("osm")
        job["params"].update(
            source="websites",
            urls="https://business.test",
            research_profile="hood_automation",
            reference_ids=["tedt-test"],
        )
        archived = {
            "id": "tedt-test",
            "website": "https://business.test",
            "city": "Fort Worth",
            "state": "TX",
            "email": "historical@business.test",
            "decision_maker": "Old Owner",
            "historical_score": 9.5,
            "as_of": "2026-08",
        }
        with (
            patch.object(
                engine.reference_library, "load", return_value={"records": [archived]}
            ),
            patch.object(engine, "public_url", return_value="https://business.test"),
        ):
            engine.run(job, threading.Event())
        row = engine.get_job(job["id"])["rows"][0]
        self.assertEqual("Fort Worth, TX", row["city"])
        self.assertEqual("tedt-test", row["reference_id"])
        self.assertEqual("", row["email"])
        self.assertEqual("", row["decision_maker"])
        self.assertEqual(0, row["opportunity_score"])
        self.assertIn(
            "opportunity", engine.download(job["id"], "csv")[0].decode("utf-8-sig")
        )

    def test_empty_website_response_marks_run_partial_with_diagnosis(self):
        job = self.job("osm")
        job["params"].update(
            source="websites", urls="https://hoodcleaning.test", enrich=True
        )
        client = SimpleNamespace(get=lambda url: ("<html><body></body></html>", url))
        with (
            patch.object(engine, "WebClient", return_value=client),
            patch.object(
                engine, "public_url", return_value="https://hoodcleaning.test"
            ),
        ):
            engine.run(job, threading.Event())
        result = engine.get_job(job["id"])
        self.assertEqual("partial", result["status"])
        self.assertIn("no usable page evidence", result["diagnosis"])
        self.assertEqual("candidate", result["rows"][0]["match_status"])


if __name__ == "__main__":
    unittest.main()
