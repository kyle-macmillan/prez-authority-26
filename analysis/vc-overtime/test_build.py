import csv
import importlib.util
import json
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory


PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("vc_overtime_build", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class VestingClauseOvertimeTest(unittest.TestCase):
    def test_cutoff_includes_exactly_fifty_and_excludes_lower_values(self):
        counts = Counter()
        counts[("total", "all", MOD.CATEGORIES[0])] = 1_100
        counts[("total", "all", MOD.CATEGORIES[1])] = 1_099
        means, retained = MOD.retain_categories(counts, administration_count=22)
        self.assertEqual(means[MOD.CATEGORIES[0]], 50.0)
        self.assertIn(MOD.CATEGORIES[0], retained)
        self.assertNotIn(MOD.CATEGORIES[1], retained)

    def test_compact_labels_disambiguate_bushes_and_flag_partial_term(self):
        self.assertEqual(MOD.compact_administration_label("George Bush (First)"), "G.H.W. Bush")
        self.assertEqual(MOD.compact_administration_label("George W. Bush (Second)"), "G.W. Bush")
        self.assertEqual(
            MOD.compact_administration_label("Donald J. Trump (Second)"),
            "Trump*",
        )

    def test_plotted_and_core_categories_exclude_non_vesting_buckets(self):
        self.assertNotIn("no_vesting_clause", MOD.PLOTTED_CATEGORIES)
        self.assertNotIn("other_vesting_authority", MOD.PLOTTED_CATEGORIES)
        self.assertEqual(
            set(MOD.CORE_AUTHORITY_CATEGORIES),
            {
                "generic_constitution_and_specific_statute",
                "generic_constitution_and_generic_statute",
                "specific_statute_only",
            },
        )

    def test_filter_ceremonial_records_reasons(self):
        rows = [
            {
                "doc_type": "executive_order",
                "doc_text": "The flag shall be flown at half-staff.",
                "url": "https://example.test/memorial",
            },
            {
                "doc_type": "executive_order",
                "doc_text": "The agency shall issue regulations.",
                "url": "https://example.test/policy",
            },
        ]
        retained, reasons = MOD.filter_ceremonial(rows)
        self.assertEqual(retained, [rows[1]])
        self.assertEqual(reasons, Counter({"memorial_half_staff": 1}))

    def test_counts_csv_is_tidy_and_marks_retained_categories(self):
        counts = Counter()
        administration = "Donald J. Trump (Second)"
        category = MOD.CATEGORIES[0]
        counts[(administration, "all", category)] = 7
        means = {item: 0.0 for item in MOD.CATEGORIES}
        means[category] = 50.0
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "counts.csv"
            MOD.write_counts_csv(path, counts, [administration], means, (category,))
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), len(MOD.VIEW_ORDER) * len(MOD.CATEGORIES))
        row = next(item for item in rows if item["directive_type"] == "all" and item["category"] == category)
        self.assertEqual(row["count"], "7")
        self.assertEqual(row["partial_administration"], "true")
        self.assertEqual(row["retained_at_50"], "true")

    def test_committed_manifest_has_complete_expected_output_set(self):
        manifest_path = PATH.with_name("outputs") / "manifest.json"
        if not manifest_path.exists():
            self.skipTest("build outputs have not been generated")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["corpus_documents"], 20_232)
        self.assertEqual(manifest["ceremonial_exclusions"], 6_771)
        self.assertEqual(manifest["nonceremonial_documents"], 13_461)
        self.assertEqual(manifest["administrations"], 22)
        self.assertEqual(
            manifest["retained_categories"],
            [
                "specific_statute_only",
                "generic_constitution_and_generic_statute",
                "generic_constitution_and_specific_statute",
            ],
        )
        self.assertEqual(manifest["excluded_from_figures"], ["no_vesting_clause", "other_vesting_authority"])
        self.assertEqual(manifest["core_authority_categories"], list(MOD.CORE_AUTHORITY_CATEGORIES))
        self.assertEqual(len(manifest["figure_files"]), 40)
        for relative_path in manifest["figure_files"]:
            output = PATH.parent / relative_path
            self.assertTrue(output.is_file(), relative_path)
            self.assertGreater(output.stat().st_size, 0, relative_path)


if __name__ == "__main__":
    unittest.main()
