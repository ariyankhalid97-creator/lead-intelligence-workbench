import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_tasks
import engine
import leadfinder as lf
from contacts import now


class LocalAITaskTests(unittest.TestCase):
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
        self.job_id = "a" * 32
        self.original = {
            "name": "Synthetic Test Business",
            "city": "Dallas",
            "email": "published@business.test",
            "phone": "+12145550123",
            "website": "https://business.test",
            "score": 72,
            "operator_type": "unknown",
            "facts": "[]",
            "ai_analysis": '{"old":true}',
            "ai_draft": "{}",
        }
        engine.save(
            {
                "id": self.job_id,
                "created_at": now(),
                "status": "complete",
                "params": {"niche": "Test service"},
                "rows": [dict(self.original)],
                "count": 1,
            }
        )

    def tearDown(self):
        ai_tasks.EVENTS.clear()
        for handler in list(engine.LOG.handlers):
            handler.close()
            engine.LOG.removeHandler(handler)
        self.root_patch.stop()
        self.db_patch.stop()
        self.tmp.cleanup()

    def settings(self, **changes):
        return {
            "task": "review",
            "model": "qwen3.5:4b",
            "job_id": self.job_id,
            "row_index": 0,
            "offer": "My stated test offer",
            **changes,
        }

    def task(self, **changes):
        return {
            "id": "b" * 32,
            "created_at": now(),
            "status": "queued",
            "params": ai_tasks.validate(self.settings(**changes)),
        }

    def test_validates_task_model_saved_row_and_offer_bounds(self):
        for changes in (
            {"task": "send"},
            {"model": "https://remote.test/model"},
            {"row_index": True},
            {"row_index": 500},
            {"offer": "x" * 801},
            {"job_id": "not-a-job"},
        ):
            with self.assertRaises(ValueError):
                ai_tasks.validate(self.settings(**changes))
        with self.assertRaises(ValueError):
            ai_tasks.validate(
                {"task": "plan", "model": "qwen3.5:4b", "niche": "cleaning"}
            )

    def test_does_not_review_live_search(self):
        saved = engine.get_job(self.job_id, events=False)
        saved["status"] = "running"
        engine.save(saved)
        with self.assertRaisesRegex(ValueError, "Wait for the search"):
            ai_tasks.validate(self.settings())

    def test_review_only_adds_separate_suggestions_and_download_fields(self):
        result = {
            "analysis": {
                "status": "complete",
                "summary": "Synthetic AI suggestion",
                "reasons": [],
            },
            "draft": {"status": "draft", "body": "Synthetic unsent draft"},
        }
        task = self.task()
        with patch.object(ai_tasks.local_ai, "review", return_value=result):
            ai_tasks.run(task, threading.Event())
        saved = engine.get_job(self.job_id)
        row = saved["rows"][0]
        for key, value in self.original.items():
            if key not in ("ai_analysis", "ai_draft"):
                self.assertEqual(value, row[key], key)
        self.assertEqual(result["analysis"], json.loads(row["ai_analysis"]))
        self.assertEqual("complete", ai_tasks.get_task(task["id"])["status"])
        self.assertIn(
            "ai_analysis", engine.download(self.job_id, "csv")[0].decode("utf-8-sig")
        )
        self.assertTrue(any(e["provider"] == "local_ai" for e in saved["events"]))

    def test_unavailable_model_keeps_old_notes_and_primary_data(self):
        task = self.task()
        with patch.object(
            ai_tasks.local_ai,
            "review",
            side_effect=TimeoutError("Local model timed out"),
        ):
            ai_tasks.run(task, threading.Event())
        self.assertEqual(self.original, engine.get_job(self.job_id)["rows"][0])
        self.assertEqual("failed", ai_tasks.get_task(task["id"])["status"])

    def test_cancelled_request_does_not_mutate_lead(self):
        task = self.task()
        cancel = threading.Event()
        cancel.set()
        with patch.object(ai_tasks.local_ai, "review") as model:
            ai_tasks.run(task, cancel)
        model.assert_not_called()
        self.assertEqual(self.original, engine.get_job(self.job_id)["rows"][0])

    def test_changed_lead_is_not_annotated_under_stale_index(self):
        task = self.task()
        saved = engine.get_job(self.job_id)
        saved["rows"][0]["name"] = "Another synthetic business"
        engine.save(saved)
        with patch.object(ai_tasks.local_ai, "review") as model:
            ai_tasks.run(task, threading.Event())
        model.assert_not_called()
        self.assertEqual("failed", ai_tasks.get_task(task["id"])["status"])

    def test_queue_is_bounded_and_restart_recovery_does_not_touch_search(self):
        with patch.object(threading.Thread, "start"):
            tasks = [
                ai_tasks.start(
                    self.settings(task="plan", niche="cleaning", location="Dallas")
                )
                for _ in range(4)
            ]
            with self.assertRaisesRegex(ValueError, "queue is full"):
                ai_tasks.start(self.settings())
        ai_tasks.init(recover=False)
        self.assertEqual("queued", ai_tasks.get_task(tasks[0])["status"])
        ai_tasks.init()
        self.assertEqual("failed", ai_tasks.get_task(tasks[0])["status"])
        self.assertEqual("complete", engine.get_job(self.job_id)["status"])

    def test_plan_is_separate_from_search_and_has_no_scraping_action(self):
        settings = ai_tasks.validate(
            {
                "task": "plan",
                "model": "qwen3.5:4b",
                "niche": "Hood Cleaning",
                "location": "Dallas",
            }
        )
        task = {
            "id": "c" * 32,
            "created_at": now(),
            "status": "queued",
            "params": settings,
        }
        with patch.object(
            ai_tasks.local_ai,
            "plan",
            return_value={
                "status": "complete",
                "phrases": ["kitchen exhaust cleaning"],
            },
        ):
            ai_tasks.run(task, threading.Event())
        self.assertEqual("complete", ai_tasks.get_task(task["id"])["status"])
        self.assertFalse(ai_tasks.get_task(task["id"])["result"]["saved_to_niche_pack"])
        self.assertEqual(self.original, engine.get_job(self.job_id)["rows"][0])

    def test_batch_compiler_saves_progress_and_skips_unchanged_evidence(self):
        saved = engine.get_job(self.job_id, events=False)
        saved["rows"][0].update(entity_id="company-test", operating_entity_id="operating-test", compiler_output="")
        engine.save(saved)
        output = {
            "canonical_company_id": "company-test", "operating_location_id": "operating-test",
            "compiled_claims": [], "contact_readiness": {"primary_contact_id": None, "contact_type": "generic_role_inbox", "deliverability_state": "unverified", "eligible_for_outreach": False},
            "opportunity_signals": [], "semantic_change_summary": {"is_material_change": False, "ignored_noise_fields": [], "material_changes_detected": []},
            "next_best_action": {"queue_state": "verification", "rationale": "Verify contact", "recommended_campaign_variant_id": None},
        }
        settings = ai_tasks.validate({"task": "compile_batch", "model": "qwen3.5:4b", "job_id": self.job_id, "scope": "all"})
        task = {"id": "d" * 32, "created_at": now(), "status": "queued", "params": settings}
        with patch.object(ai_tasks.local_ai, "compile_intelligence", return_value=output) as model:
            ai_tasks.run(task, threading.Event())
        self.assertEqual("complete", task["status"])
        self.assertEqual(1, task["result"]["completed"])
        second = {"id": "e" * 32, "created_at": now(), "status": "queued", "params": settings}
        with patch.object(ai_tasks.local_ai, "compile_intelligence") as model_again:
            ai_tasks.run(second, threading.Event())
        model_again.assert_not_called()
        self.assertEqual(1, second["result"]["skipped"])

    def test_qualified_batch_excludes_generic_candidates(self):
        saved = engine.get_job(self.job_id, events=False)
        saved["rows"] = [
            {**saved["rows"][0], "match_status": "service_match", "verification": '{"status":"complete"}'},
            {**saved["rows"][0], "name": "Generic candidate", "match_status": "candidate", "verification": '{"status":"complete"}'},
        ]
        engine.save(saved)
        settings = ai_tasks.validate({"task": "compile_batch", "model": "qwen3.5:4b", "job_id": self.job_id, "scope": "qualified"})
        task = {"id": "f" * 32, "created_at": now(), "status": "queued", "params": settings}
        with patch.object(ai_tasks, "_compile_saved_row", return_value={"status": "complete"}) as compile_row:
            ai_tasks.run(task, threading.Event())
        self.assertEqual(1, task["total"])
        self.assertEqual(1, compile_row.call_count)


if __name__ == "__main__":
    unittest.main()
