import csv
import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("delegation_recipient_build", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class DelegationRecipientTest(unittest.TestCase):
    def test_parallel_act_and_usc_citation_is_one_authority_unit(self):
        clause = (
            "By authority vested in me by sections 2 and 4(a)(1) of the Migration and "
            "Refugee Assistance Act of 1962 (22 U.S.C. 2601 and 2603), I determine"
        )
        pinpoint, broad = MOD.parse_clause(clause)
        self.assertEqual(
            [row["canonical_authority_id"] for row in pinpoint],
            ["usc:22:2601", "usc:22:2603"],
        )
        self.assertEqual(broad, [])
        self.assertTrue(all("sections 2 and 4(a)(1)" in row["parallel_aliases"] for row in pinpoint))

    def test_subsection_is_part_of_canonical_key(self):
        pinpoint, broad = MOD.parse_clause("Pursuant to 42 U.S.C. § 6961(a), I exempt the facility.")
        self.assertEqual(len(pinpoint), 1)
        self.assertEqual(pinpoint[0]["canonical_authority_id"], "usc:42:6961(a)")
        self.assertEqual(broad, [])

    def test_section_of_title_code_form_is_parsed(self):
        pinpoint, broad = MOD.parse_clause("under section 301 of title 3, United States Code")
        self.assertEqual([row["canonical_authority_id"] for row in pinpoint], ["usc:3:301"])
        self.assertEqual(broad, [])

    def test_range_and_et_seq_are_broad(self):
        pinpoint, broad = MOD.parse_clause("under 10 U.S.C. 801-946 and 50 U.S.C. 1701 et seq.")
        self.assertEqual(pinpoint, [])
        self.assertEqual(len(broad), 2)

    def test_agency_authority_is_not_presidential_merely_because_clause_is_presidential(self):
        self.assertIn("agency_or_officer_only", MOD.RECIPIENT_CLASSES)
        self.assertNotEqual("agency_or_officer_only", "president_only")

    def test_authority_core_drops_recital_citations(self):
        clause = (
            "Section 5 of the Example Act supplied background. Now, therefore, I, Example Person, "
            "President of the United States, by virtue of the authority vested in me by 3 U.S.C. 301"
        )
        core = MOD.authority_core(clause)
        self.assertNotIn("Section 5", core)
        self.assertIn("3 U.S.C. 301", core)

    def test_shared_grants_are_not_forced_into_exclusive_comparison(self):
        rows = ([{"recipient_class": "president_only"}] * 8
                + [{"recipient_class": "agency_or_officer_only"}]
                + [{"recipient_class": "both"}])
        metrics = MOD.recipient_metrics(rows)
        self.assertAlmostEqual(metrics["exclusive_recipient_presidential_percent"], 800 / 9)
        self.assertEqual(metrics["president_only_share_resolved_power_conferrals_percent"], 80.0)
        self.assertEqual(metrics["any_presidential_share_resolved_power_conferrals_percent"], 90.0)

    def test_duplicate_same_clause_authority_does_not_inflate_count(self):
        pinpoint, _ = MOD.parse_clause("under 3 U.S.C. 301 and again 3 U.S.C. § 301")
        self.assertEqual(len(pinpoint), 1)

    def test_census_version_matching_is_date_bounded(self):
        census = [{
            "canonical_authority_id": "usc:3:301", "version_start": "1951-10-31",
            "version_end": "", "recipient_class": "president_only",
        }]
        self.assertIsNone(MOD.census_match(census, "usc:3:301", "January 01, 1950"))
        self.assertEqual(
            MOD.census_match(census, "usc:3:301", "January 01, 1960")["recipient_class"],
            "president_only",
        )

    def test_committed_manifest_reconciles_population(self):
        manifest = PATH.with_name("outputs") / "manifest.json"
        if not manifest.exists():
            self.skipTest("outputs not built")
        import json
        data = json.loads(manifest.read_text())
        self.assertEqual(data["corpus_documents"], 20_232)
        self.assertEqual(data["ceremonial_exclusions"], 6_771)
        self.assertEqual(data["nonceremonial_documents"], 13_461)


if __name__ == "__main__":
    unittest.main()
