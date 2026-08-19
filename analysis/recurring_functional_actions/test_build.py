import importlib.util
import unittest
from pathlib import Path

PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("recurring_build", PATH)
MOD = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MOD)


class RecurringFamiliesTest(unittest.TestCase):
    def test_emergency_requires_action(self):
        incidental = {"label": "Emergency preparedness", "action": "prepare a report", "target": "future emergencies", "mechanism": "study", "effect": "", "evidence": ""}
        self.assertNotIn("emergency_action", [x[0] for x in MOD.seed_matches(incidental)])
        declaration = {**incidental, "action": "declare a national emergency", "target": "the specified threat"}
        self.assertIn(("emergency_action", "declaration"), MOD.seed_matches(declaration))

    def test_emergency_subtypes(self):
        base = {"label": "", "target": "national emergency", "mechanism": "", "effect": "", "evidence": ""}
        self.assertIn(("emergency_action", "continuation"), MOD.seed_matches({**base, "action": "continue the national emergency in effect"}))
        self.assertIn(("emergency_action", "termination"), MOD.seed_matches({**base, "action": "terminate the national emergency"}))

    def test_authority_is_not_in_function_text(self):
        function = {"action": "block", "target": "property", "mechanism": "order", "effect": "freeze", "authority": "IEEPA"}
        self.assertNotIn("IEEPA", MOD.function_text(function))


if __name__ == "__main__": unittest.main()
