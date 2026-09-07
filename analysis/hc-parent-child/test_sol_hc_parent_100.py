import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def load(name):
    path = HERE / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = load("run_sol_hc_parent_100")
SCORER = load("score_sol_hc_parent_100")


class SolHcParentTests(unittest.TestCase):
    def test_response_validation(self):
        request = {"case_id": "SHC001", "candidates": [{"candidate_label": "C01"}]}
        response = {
            "case_id": "SHC001", "decision": "candidate", "selected_candidate_label": "C01",
            "candidate_ranking": ["C01", "C02", "C03"], "confidence": 0.8,
        }
        request["candidates"].extend([
            {"candidate_label": "C02"}, {"candidate_label": "C03"},
        ])
        RUNNER.validate_response(response, request)
        with self.assertRaises(ValueError):
            RUNNER.validate_response({**response, "selected_candidate_label": "C99"}, request)
        with self.assertRaises(ValueError):
            RUNNER.validate_response({**response, "decision": "none"}, request)
        with self.assertRaises(ValueError):
            RUNNER.validate_response({**response, "candidate_ranking": ["C02", "C01", "C03"]}, request)

    def test_retrieval_summary_uses_accepted_denominator(self):
        rows = [{"word5_rank": "1"}, {"word5_rank": "5"}, {"word5_rank": ""}]
        result = SCORER.retrieval_summary(rows, "word5")
        self.assertEqual(result["rank_available"], 2)
        self.assertEqual(result["recall_at_1"], 1 / 3)
        self.assertEqual(result["recall_at_5"], 2 / 3)
        self.assertAlmostEqual(result["mean_reciprocal_rank"], 0.4)

    def test_hybrid_summary_reports_incremental_function_retrieval(self):
        rows = [
            {"assigned_family": "a", "word5_rank": "1", "function_rank": ""},
            {"assigned_family": "a", "word5_rank": "8", "function_rank": "3"},
            {"assigned_family": "a", "word5_rank": "2", "function_rank": "4"},
        ]
        all_top_five = next(
            row for row in SCORER.hybrid_retrieval_summary(rows)
            if row["sol_assigned_family"] == "all" and row["rank_cutoff"] == 5
        )
        self.assertEqual(all_top_five["word5_n"], 2)
        self.assertEqual(all_top_five["function_n"], 2)
        self.assertEqual(all_top_five["word5_only_n"], 1)
        self.assertEqual(all_top_five["function_only_n"], 1)
        self.assertEqual(all_top_five["word5_or_function_n"], 3)


if __name__ == "__main__":
    unittest.main()
