import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_brain
import ai_teaching
import engine


class AIBrainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(engine, "DB", Path(self.tmp.name) / "test.db")
        self.env_patch = patch.dict(os.environ, {"LEAD_EXTRACTOR_HOME": self.tmp.name})
        self.db_patch.start()
        self.env_patch.start()
        engine.init(recover=False)

    def tearDown(self):
        self.env_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def _job(self):
        return {
            "id": "brain-job",
            "status": "complete",
            "params": {"niche": "Roofing"},
            "count": 12,
            "rows": [{"name": "Private Company", "email": "secret@example.test"}],
            "stats": {"emails": 4, "phones": 10, "websites": 11, "matches": 9},
            "providers": {
                "browser": {"successes": 2, "failures": 0, "count": 12},
                "osm": {"successes": 0, "failures": 2, "count": 0},
            },
        }

    def test_snapshot_is_aggregate_and_excludes_lead_identity(self):
        job = self._job()
        with engine.connection() as conn:
            conn.execute(
                "INSERT INTO jobs(id,created_at,updated_at,status,payload) VALUES(?,?,?,?,?)",
                (job["id"], "2026-01-01", "2026-01-01", "complete", json.dumps(job)),
            )
        result = ai_brain.refresh("Roofing")
        encoded = json.dumps(result)
        self.assertEqual(1, result["source_runs"])
        self.assertEqual(12, result["results_observed"])
        self.assertEqual("browser", result["historical_provider_performance"][0]["provider"])
        self.assertNotIn("Private Company", encoded)
        self.assertNotIn("secret@example.test", encoded)

    def test_reviewed_feedback_shapes_prompt_memory(self):
        ai_teaching.record_feedback("Roofing", ["roof leak repair"], True)
        ai_teaching.record_feedback("Roofing", ["roofing solutions"], False)
        context = ai_brain.prompt_context("Roofing")
        self.assertIn("roof leak repair", context["approved_phrases"])
        self.assertIn("roofing solutions", context["avoid_phrases"])
        self.assertIn("Evidence saved in the current run remains the only authority for lead claims.", context["consistency_rules"])

    def test_prompt_context_initializes_a_completely_fresh_database(self):
        fresh_db = Path(self.tmp.name) / "fresh" / "workbench.db"
        with patch.object(engine, "DB", fresh_db):
            context = ai_brain.prompt_context("Roofing")
            with engine.connection() as conn:
                table = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_memory_snapshots'"
                ).fetchone()
        self.assertEqual(("ai_memory_snapshots",), table)
        self.assertEqual("new", context["confidence"])


if __name__ == "__main__":
    unittest.main()
