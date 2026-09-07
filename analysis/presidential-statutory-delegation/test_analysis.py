import csv
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUILD = load("presidential_delegation_build", "build.py")
WORKFLOW = load("presidential_delegation_workflow", "workflow.py")
RUNNER = load("presidential_delegation_runner", "run_gpt56.py")


class PresidentialDelegationAnalysisTest(unittest.TestCase):
    def test_parallel_act_and_code_form_collapse_without_capturing_next_cite(self):
        clause = (
            "authority vested in me by section 604 of the Trade Act of 1974 "
            "(19 U.S.C. 2483), and section 301 of title 3, United States Code"
        )
        items, audit = BUILD.parse_statutory_clause(clause, "1:1")
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertEqual(set(by_id), {"usc:19:2483", "usc:3:301"})
        self.assertIn("Trade Act", by_id["usc:19:2483"]["parallel_aliases"])
        self.assertNotIn("Trade Act", by_id["usc:3:301"]["parallel_aliases"])
        self.assertFalse([row for row in audit if row["disposition"] == "unmapped_statutory_signal"])

    def test_broad_named_act_and_usc_range_are_one_unit(self):
        items, _ = BUILD.parse_statutory_clause(
            "under the International Emergency Economic Powers Act (50 U.S.C. 1701 et seq.)", "2:1"
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["is_broad"], "true")
        self.assertIn("International Emergency", items[0]["parallel_aliases"])

    def test_section_of_named_act_is_not_an_alias_of_following_code_citation(self):
        clause = (
            "including section 3 of the Suspending Normal Trade Relations with Russia and Belarus Act; "
            "section 301 of title 3, United States Code"
        )
        items, _ = BUILD.parse_statutory_clause(clause, "5:1")
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertIn("act:the-suspending-normal-trade-relations-with-russia-and-belarus-act:3", by_id)
        self.assertNotIn("Belarus", by_id["usc:3:301"]["parallel_aliases"])

    def test_act_section_with_amended_parenthetical_code_is_parallel_not_duplicate(self):
        items, _ = BUILD.parse_statutory_clause(
            "under section 604 of the Trade Act of 1974, as amended (19 U.S.C. 2483)", "6:1"
        )
        self.assertEqual([row["canonical_authority_id"] for row in items], ["usc:19:2483"])

    def test_known_act_to_code_equivalent_is_not_duplicated_without_printed_code(self):
        items, _ = BUILD.parse_statutory_clause("under section 604 of the Trade Act of 1974", "7:1")
        self.assertEqual([row["canonical_authority_id"] for row in items], ["usc:19:2483"])

    def test_named_act_near_code_citation_is_not_assumed_to_be_an_alias(self):
        items, _ = BUILD.parse_statutory_clause(
            "including the National Quantum Initiative Act and section 301 of title 3, United States Code", "8:1"
        )
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertIn("act-broad:the-national-quantum-initiative-act", by_id)
        self.assertNotIn("NQI", by_id["usc:3:301"]["parallel_aliases"])

    def test_legacy_nearby_act_aliases_are_stripped_from_three_usc_301(self):
        clause = (
            "including section 621 of the Foreign Assistance Act of 1961; section 14 of the Export-Import "
            "Bank Act of 1945; and section 301 of title 3, United States Code"
        )
        items, _ = BUILD.parse_statutory_clause(clause, "9:1")
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertEqual(by_id["usc:3:301"]["parallel_aliases"], "")
        self.assertIn("usc:22:2381", by_id)
        self.assertIn("act:the-export-import-bank-act-of-1945:14", by_id)

    def test_grouped_code_citation_has_individual_display_cites(self):
        items, _ = BUILD.parse_statutory_clause("under 3 U.S.C. 301 and 46", "10:1")
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertEqual(by_id["usc:3:301"]["raw_citation"], "3 U.S.C. 301")
        self.assertEqual(by_id["usc:3:46"]["raw_citation"], "3 U.S.C. 46")

    def test_generic_act_section_is_contextual_not_pooled_across_acts(self):
        first, _ = BUILD.parse_statutory_clause("under section 2 of the Act", "11:1")
        second, _ = BUILD.parse_statutory_clause("under section 2 of the Act", "12:1")
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["citation_kind"], "contextual_act_section")
        self.assertNotEqual(first[0]["canonical_authority_id"], second[0]["canonical_authority_id"])
        self.assertNotIn("act:the-act:2", first[0]["canonical_authority_id"])

    def test_act_of_full_date_is_not_truncated_to_generic_act(self):
        items, _ = BUILD.parse_statutory_clause(
            "under section 2 of the Act of June 8, 1906 (34 Stat. 225, 16 U.S.C. 431)", "13:1"
        )
        by_id = {row["canonical_authority_id"]: row for row in items}
        self.assertEqual(set(by_id), {"usc:16:431"})
        self.assertNotIn("contextual-act-section:13-1:the-act:2", by_id)
        self.assertIn("section 2 of the Act of June 8, 1906", by_id["usc:16:431"]["parallel_aliases"])
        self.assertIn("34 Stat. 225", by_id["usc:16:431"]["parallel_aliases"])
        self.assertEqual(by_id["usc:16:431"]["equivalence_basis"], "explicit_parenthetical")

    def test_named_act_public_law_and_stat_are_one_printed_bundle(self):
        items, audit = BUILD.parse_statutory_clause(
            "under the Example Administration Act (Public Law 94 - 580, 90 Stat. 2865)", "13b:1"
        )
        self.assertEqual([row["canonical_authority_id"] for row in items], ["public-law:94-580"])
        self.assertIn("Example Administration Act", items[0]["parallel_aliases"])
        self.assertIn("90 Stat. 2865", items[0]["parallel_aliases"])
        self.assertTrue(any(row["equivalence_basis"] == "explicit_parenthetical" for row in audit))

    def test_whole_act_and_separate_act_section_remain_distinct(self):
        items, _ = BUILD.parse_statutory_clause(
            "under the Example Administration Act and section 2 of the Example Administration Act", "13c:1"
        )
        ids = {row["canonical_authority_id"] for row in items}
        self.assertEqual(ids, {
            "act-broad:the-example-administration-act",
            "act:the-example-administration-act:2",
        })

    def test_precise_alias_ids_excludes_whole_act_but_resolves_act_section(self):
        self.assertEqual(
            BUILD._precise_alias_ids("section 2 of the Act of June 8, 1906"),
            {"act:the-act-of-june-8-1906:2"},
        )
        self.assertEqual(BUILD._precise_alias_ids("the Act of June 8, 1906"), set())

    def test_public_law_with_spaced_dash_retains_full_number(self):
        items, _ = BUILD.parse_statutory_clause("under Public Law 94 - 580", "14:1")
        self.assertEqual([row["canonical_authority_id"] for row in items], ["public-law:94-580"])
        self.assertEqual(items[0]["raw_citation"], "Public Law 94 - 580")

    def test_named_act_with_connector_is_not_reduced_to_title_tail(self):
        items, _ = BUILD.parse_statutory_clause(
            "under the Resource Conservation and Recovery Act (RCRA)", "15:1"
        )
        self.assertEqual(
            [row["canonical_authority_id"] for row in items],
            ["act-broad:the-resource-conservation-and-recovery-act"],
        )
        self.assertEqual(items[0]["raw_citation"], "the Resource Conservation and Recovery Act")

    def test_bare_act_label_is_not_a_statutory_citation(self):
        items, audit = BUILD.parse_statutory_clause("under the Act", "16:1")
        self.assertEqual(items, [])
        self.assertEqual(audit[0]["disposition"], "excluded_nonidentifying_act_reference")

    def test_printed_act_section_and_code_parallel_form_keeps_section_locator(self):
        items, _ = BUILD.parse_statutory_clause(
            "under section 10 of the Railway Labor Act, as amended (45 U.S.C. 160)", "17:1"
        )
        self.assertEqual([row["canonical_authority_id"] for row in items], ["usc:45:160"])
        self.assertIn("section 10 of the Railway Labor Act", items[0]["parallel_aliases"])

    def test_nonstatutory_specific_authority_is_audited_not_counted(self):
        items, audit = BUILD.parse_statutory_clause(
            "under Article II and Executive Order 12345", "3:1"
        )
        self.assertEqual(items, [])
        self.assertTrue(audit)
        self.assertTrue(all(row["disposition"] == "excluded_nonstatutory_specific_authority" for row in audit))

    def test_revised_statutes_is_retained(self):
        items, _ = BUILD.parse_statutory_clause("under section 1753 of the Revised Statutes", "4:1")
        self.assertIn("revised-statutes:1753", {row["canonical_authority_id"] for row in items})

    def test_response_validation_enforces_headline_derivation(self):
        packet = {"canonical_authority_id": "usc:3:301", "observed_dates": ["2000-01-01"]}
        answer = {
            "canonical_authority_id": "usc:3:301",
            "classifications": [{
                "version_start": "1951-10-31", "version_end": None,
                "presidential_authorization": True, "presidential_required_duty": False,
                "presidential_condition_precedent": False,
                "standalone_presidential_constraint": False,
                "classification": "nondelegation", "confidence": "high",
                "operative_excerpt": "The President may", "rationale": "test",
                "official_sources": ["https://uscode.house.gov/"],
            }],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "answer.json"
            path.write_text(json.dumps(answer), encoding="utf-8")
            parsed, errors = RUNNER.validate_answer(path, packet)
        self.assertIsNone(parsed)
        self.assertIn("headline derivation", " ".join(errors))

    def test_directive_rollup_preserves_mixed_and_unresolved(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            occurrences = root / "occurrences.csv"
            fields = ["occurrence_id", "document_id", "date", "president", "term", "doc_type", "url",
                      "clause_index", "raw_clause", "raw_citation", "citation_kind",
                      "canonical_authority_id", "is_broad", "parallel_aliases", "specific_rules", "extraction_status"]
            rows = []
            for index, authority in enumerate(("usc:3:1", "usc:3:2"), 1):
                rows.append(dict.fromkeys(fields, "") | {
                    "occurrence_id": str(index), "document_id": "1", "date": "January 01, 2000",
                    "canonical_authority_id": authority,
                })
            with occurrences.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
            responses = root / "responses.jsonl"
            answers = []
            for authority, label, authorization in (("usc:3:1", "delegation", True), ("usc:3:2", "nondelegation", False)):
                answers.append({"ok": True, "answer": {"canonical_authority_id": authority, "classifications": [{
                    "version_start": "1900-01-01", "version_end": None,
                    "presidential_authorization": authorization, "presidential_required_duty": False,
                    "presidential_condition_precedent": False, "standalone_presidential_constraint": False,
                    "classification": label, "confidence": "high", "operative_excerpt": "x",
                    "rationale": "x", "official_sources": ["https://example.test"],
                }]}})
            responses.write_text("".join(json.dumps(row) + "\n" for row in answers), encoding="utf-8")
            args = type("Args", (), {"occurrences": occurrences, "responses": responses, "output": root,
                                     "allow_incomplete": False})
            WORKFLOW.compile_results(args)
            with (root / "classified_directives.csv").open(newline="", encoding="utf-8") as handle:
                directives = list(csv.DictReader(handle))
            self.assertEqual(directives[0]["directive_classification"], "mixed")


if __name__ == "__main__":
    unittest.main()
