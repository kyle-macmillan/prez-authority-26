import importlib.util
import unittest
from datetime import date
from pathlib import Path

PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("day_one_build", PATH)
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


class DayOneWeekOneTest(unittest.TestCase):
    def test_window_boundaries(self):
        start = date(2025, 1, 20)
        self.assertEqual(MOD.window_membership(start, start), (0, True, True))
        self.assertEqual(MOD.window_membership(date(2025, 1, 26), start), (6, False, True))
        self.assertEqual(MOD.window_membership(date(2025, 1, 27), start), (7, False, False))

    def test_nonconsecutive_return_is_included(self):
        self.assertIn(("trump_2025", "Donald J. Trump", "2025-01-20"), MOD.STARTS)

    def test_issue_proposals_are_multilabel(self):
        issues = MOD.proposed_issues("Climate-related immigration and refugee policy")
        self.assertIn("climate_environment_energy", issues)
        self.assertIn("immigration_borders", issues)

    def test_no_flip_flop_field(self):
        source = PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn('"flip_flop"', source)


if __name__ == "__main__": unittest.main()
