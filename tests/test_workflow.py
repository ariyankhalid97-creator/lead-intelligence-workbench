import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import engine
import workflow


class LinkedWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = engine.DB
        engine.DB = Path(self.temp.name) / "workbench.db"
        engine.init(recover=False)
        workflow.init(recover=False)
        self.job_id = "a" * 32
        engine.save({
            "id": self.job_id,
            "created_at": "2026-10-26T00:00:00+05:00",
            "status": "complete",
            "progress": 100,
            "message": "1 business collected",
            "params": {"niche": "Test niche"},
            "rows": [{
                "name": "Example",
                "match_status": "service_match",
                "verification": "{}",
                "email_quality": '{"recommended":[{"email":"owner@example.com","recommended":true}]}',
            }, {
                "name": "Generic candidate",
                "match_status": "candidate",
                "verification": "{}",
                "email_quality": '{"recommended":[{"email":"info@example.net","recommended":true}]}',
            }],
            "organization": {"recommended_email_records": 1, "duplicates_consolidated": 0},
        })

    def tearDown(self):
        workflow.EVENTS.clear()
        engine.DB = self.old_db
        self.temp.cleanup()

    def test_completed_search_advances_every_stage_without_sending(self):
        with patch.object(threading.Thread, "start"):
            task_id = workflow.start({"job_id": self.job_id, "model": "local-model"})
        task = workflow.get_task(task_id)
        verification_state = {"status": "complete", "progress": 100, "message": "Verification complete", "summary": {"verified": 1}}
        ai_state = {"status": "complete", "progress": 100, "message": "Compilation complete", "result": {"completed": 1}}
        with (
            patch.object(workflow.verification, "start", return_value="b" * 32),
            patch.object(workflow.verification, "get_task", return_value=verification_state),
            patch.object(workflow.local_ai, "status", return_value={"available": True, "default_model": "local-model", "models": [{"name": "local-model"}]}),
            patch.object(workflow.ai_tasks, "start", return_value="c" * 32),
            patch.object(workflow.ai_tasks, "get_task", return_value=ai_state),
        ):
            workflow._run(task, threading.Event())
        finished = workflow.get_task(task_id)
        self.assertEqual("complete", finished["status"])
        self.assertEqual(100, finished["progress"])
        self.assertEqual("complete", finished["stages"]["verification"]["status"])
        self.assertEqual("complete", finished["stages"]["compilation"]["status"])
        self.assertEqual("ready", finished["stages"]["outreach"]["status"])
        self.assertEqual(1, finished["stages"]["outreach"]["eligible"])
        self.assertEqual(1, finished["result"]["outreach_ready"])
        self.assertIn("approval", finished["stages"]["outreach"]["message"])

    def test_missing_local_model_skips_only_compilation(self):
        with patch.object(threading.Thread, "start"):
            task_id = workflow.start({"job_id": self.job_id})
        task = workflow.get_task(task_id)
        with (
            patch.object(workflow.verification, "start", return_value="d" * 32),
            patch.object(workflow.verification, "get_task", return_value={"status": "complete", "progress": 100, "message": "Done", "summary": {}}),
            patch.object(workflow.local_ai, "status", return_value={"available": False, "models": []}),
            patch.object(workflow.ai_tasks, "start") as ai_start,
        ):
            workflow._run(task, threading.Event())
        finished = workflow.get_task(task_id)
        self.assertEqual("complete", finished["status"])
        self.assertEqual("skipped", finished["stages"]["compilation"]["status"])
        ai_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
