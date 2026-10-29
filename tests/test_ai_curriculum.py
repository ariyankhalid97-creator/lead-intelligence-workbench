import unittest

import ai_benchmark
import ai_curriculum


class AICurriculumTests(unittest.TestCase):
    def test_curriculum_covers_core_research_disciplines(self):
        lesson = ai_curriculum.lesson(
            "planning", "evidence", "contacts", "qualification", "outreach"
        )
        self.assertEqual(ai_curriculum.VERSION, lesson["curriculum_version"])
        self.assertEqual(5, len(lesson["lessons"]))
        self.assertTrue(
            any("Missing evidence" in rule for rule in lesson["foundations"])
        )

    def test_benchmark_scoring_rewards_correct_bounded_answers(self):
        raw = {
            "phrases": [
                {"id": "p1", "suggestions": ["restaurant hood cleaning"]},
                {"id": "p2", "suggestions": ["employment law attorney"]},
                {"id": "p3", "suggestions": ["multifamily property management"]},
            ],
            "evidence": [
                {"id": row["id"], "answer": row["answer"]}
                for row in ai_benchmark.EVIDENCE_CASES
            ],
            "contacts": [
                {"id": row["id"], "answer": row["answer"]}
                for row in ai_benchmark.CONTACT_CASES
            ],
            "identity": [
                {"id": row["id"], "answer": row["answer"]}
                for row in ai_benchmark.IDENTITY_CASES
            ],
            "outreach": [
                {"id": row["id"], "answer": row["answer"]}
                for row in ai_benchmark.OUTREACH_CASES
            ],
        }
        overall, tasks = ai_benchmark._score(raw)
        self.assertEqual(100, overall)
        self.assertEqual(100, tasks["planning"])

    def test_bad_adjacent_phrase_loses_planning_points(self):
        raw = {
            "phrases": [
                {"id": "p1", "suggestions": ["air duct repair"]},
                {"id": "p2", "suggestions": ["staffing agency"]},
                {"id": "p3", "suggestions": ["real estate photography"]},
            ],
            "evidence": [],
            "contacts": [],
            "identity": [],
            "outreach": [],
        }
        _, tasks = ai_benchmark._score(raw)
        self.assertEqual(0, tasks["planning"])


if __name__ == "__main__":
    unittest.main()
