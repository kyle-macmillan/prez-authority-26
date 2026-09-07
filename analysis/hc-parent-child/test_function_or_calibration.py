import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np


PATH = Path(__file__).with_name("calibrate_function_or_rule.py")
sys.path.insert(0, str(PATH.parent))
SPEC = importlib.util.spec_from_file_location("calibrate_function_or_rule", PATH)
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)


class FakeScorer:
    def scores(self, child_id):
        if child_id == "missing":
            return None
        return ["1", "2", "3"], np.asarray([0.8, 0.7, 0.95], dtype=np.float32)


class FunctionOrCalibrationTests(unittest.TestCase):
    def test_best_function_match_restricts_to_earlier_scoped_parents(self):
        documents = {
            "9": {"parsed_date": datetime(2020, 1, 1), "analysis_scope_reason": ""},
            "1": {"parsed_date": datetime(2010, 1, 1), "analysis_scope_reason": ""},
            "2": {"parsed_date": datetime(2015, 1, 1), "analysis_scope_reason": ""},
            "3": {"parsed_date": datetime(2021, 1, 1), "analysis_scope_reason": ""},
        }
        result = MOD.best_function_match("9", documents, FakeScorer())
        self.assertEqual(result["status"], "scored")
        self.assertEqual(result["function_parent_id"], "1")
        self.assertAlmostEqual(result["function_score"], 0.8)
        self.assertAlmostEqual(result["function_margin"], 0.1)

    def test_unique_rows_collapse_reused_controls(self):
        pairs = [
            {"hc_child_id": "10", "control_child_id": "20", "hc_word5_score": "0.3",
             "control_word5_score": "0.1", "hc_word5_margin": "0.02", "control_word5_margin": "0.01"},
            {"hc_child_id": "11", "control_child_id": "20", "hc_word5_score": "0.4",
             "control_word5_score": "0.1", "hc_word5_margin": "0.03", "control_word5_margin": "0.01"},
        ]
        rows = MOD.unique_signal_rows(pairs)
        self.assertEqual(len(rows), 3)
        self.assertEqual(sum(row["group"] == "control" for row in rows), 1)
        self.assertTrue(all(row["split"] in {"development", "holdout"} for row in rows))

    def test_cutoff_grid_enforces_incremental_control_cap(self):
        rows = []
        for group, values in (("hc", (0.9, 0.8, 0.7, 0.6)), ("control", (0.5, 0.4, 0.3, 0.2))):
            for index, value in enumerate(values):
                rows.append({
                    "group": group, "split": "development" if index < 2 else "holdout",
                    "function_status": "scored", "function_score": value,
                    "function_margin": value / 10, "text_score": 0.0,
                })
        grid, selected = MOD.cutoff_grid(rows, text_threshold=0.22, max_incremental_control_rate=0.5)
        self.assertTrue(grid)
        self.assertIsNotNone(selected)
        self.assertLessEqual(selected["control_function_only_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
