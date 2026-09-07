import csv
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("first_100_days_build", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class First100DaysTest(unittest.TestCase):
    def test_window_boundaries(self):
        start = date(2025, 1, 20)
        self.assertEqual(MOD.window_membership(date(2025, 1, 19), start), (-1, False, False, False))
        self.assertEqual(MOD.window_membership(start, start), (0, True, True, True))
        self.assertEqual(MOD.window_membership(date(2025, 1, 26), start), (6, False, True, True))
        self.assertEqual(MOD.window_membership(date(2025, 1, 27), start), (7, False, False, True))
        self.assertEqual(MOD.window_membership(date(2025, 4, 29), start), (99, False, False, True))
        self.assertEqual(MOD.window_membership(date(2025, 4, 30), start), (100, False, False, False))

    def test_nonconsecutive_return_is_included(self):
        self.assertIn(("trump_2025", "Donald J. Trump", "2025-01-20"), MOD.STARTS)

    def test_issue_proposals_are_multilabel(self):
        issues = MOD.proposed_issues("Climate-related immigration and refugee policy")
        self.assertIn("climate_environment_energy", issues)
        self.assertIn("immigration_borders", issues)

    def test_no_flip_flop_field(self):
        source = PATH.read_text(encoding="utf-8").lower()
        self.assertNotIn('"flip_flop"', source)

    def test_build_keeps_all_document_types_and_review_proposals(self):
        rows = [
            ("1", "January 20, 2025", "executive_order", "A substantive climate action"),
            ("2", "January 26, 2025", "memorandum", "Flags at half-staff"),
            ("3", "January 27, 2025", "proclamation", "An immigration action"),
            ("4", "April 29, 2025", "letter", "Order of succession"),
            ("5", "April 30, 2025", "executive_order", "Outside the window"),
            ("6", "January 20, 2017", "executive_order", "Prior Trump administration"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            corpus = temporary / "corpus.csv"
            with corpus.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["", "url", "date", "president", "doc_text", "doc_type", "term"],
                )
                writer.writeheader()
                for document_id, document_date, document_type, text in rows:
                    writer.writerow(
                        {
                            "": document_id,
                            "url": f"https://example.test/{document_id}",
                            "date": document_date,
                            "president": "Donald J. Trump",
                            "doc_text": text,
                            "doc_type": document_type,
                            "term": "First",
                        }
                    )

            output = temporary / "outputs"
            manifest = MOD.build([corpus], output)
            with (output / "directive_inventory.csv").open(newline="", encoding="utf-8") as handle:
                inventory = list(csv.DictReader(handle))

            trump_2025 = [row for row in inventory if row["administration_id"] == "trump_2025"]
            self.assertEqual([row["document_id"] for row in trump_2025], ["1", "2", "3", "4"])
            self.assertEqual({row["document_type"] for row in trump_2025}, {
                "executive_order", "memorandum", "proclamation", "letter"
            })
            self.assertEqual([row["administration_day"] for row in trump_2025], ["1", "7", "8", "100"])
            self.assertEqual(trump_2025[1]["eligibility_proposal"], "exclude_ceremonial")
            self.assertEqual(trump_2025[3]["eligibility_proposal"], "exclude_internal_management")
            self.assertEqual(manifest["cohort_documents"], 5)

            with (output / "administration_summary.csv").open(newline="", encoding="utf-8") as handle:
                summaries = {row["administration_id"]: row for row in csv.DictReader(handle)}
            self.assertEqual(summaries["trump_2025"]["day_1_documents"], "1")
            self.assertEqual(summaries["trump_2025"]["week_1_documents"], "2")
            self.assertEqual(summaries["trump_2025"]["first_100_days_documents"], "4")

            with (output / "archive_audit.csv").open(newline="", encoding="utf-8") as handle:
                audits = list(csv.DictReader(handle))
            self.assertEqual(len(audits), len(MOD.STARTS))
            self.assertTrue(all(row["archive_check_status"] == "pending" for row in audits))

            saved_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_manifest["window_days"], 100)

    def test_duplicate_corpus_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            paths = []
            for name in ("one.csv", "two.csv"):
                path = temporary / name
                path.write_text(
                    ",url,date,president,doc_text,doc_type,term\n"
                    "1,https://example.test,January 20 2025,Donald J. Trump,text,memorandum,First\n",
                    encoding="utf-8",
                )
                paths.append(path)
            with self.assertRaisesRegex(ValueError, "unique"):
                MOD.read_corpus(paths)


if __name__ == "__main__":
    unittest.main()
