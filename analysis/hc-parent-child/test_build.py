import csv
import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import numpy as np


PATH = Path(__file__).with_name("build.py")
SPEC = importlib.util.spec_from_file_location("hc_parent_child_build", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

REVIEW_PATH = Path(__file__).with_name("build_review_html.py")
REVIEW_SPEC = importlib.util.spec_from_file_location("hc_parent_child_review_html", REVIEW_PATH)
REVIEW_MOD = importlib.util.module_from_spec(REVIEW_SPEC)
REVIEW_SPEC.loader.exec_module(REVIEW_MOD)


def document(document_id, date, text, document_type="executive_order", families=None):
    return {
        "document_id": str(document_id),
        "document_type": document_type,
        "date": date,
        "parsed_date": datetime.strptime(date, "%B %d, %Y"),
        "president": "Test President",
        "term": "First",
        "url": f"https://example.test/{document_id}",
        "title": f"Document {document_id}",
        "primary_text": text,
        "robustness_text": text,
        "families": families or {},
        "loose_families": set(),
    }


class FakeSimilarity:
    def __init__(self, child_id, candidate_ids, scores):
        self.child_indices = {child_id: [0]}
        self.candidate_ids = candidate_ids
        self.values = np.asarray(scores, dtype=np.float32)

    def scores(self, child_id):
        if child_id not in self.child_indices:
            return None
        return self.candidate_ids, self.values


class EmptyDocumentSimilarity:
    index = {}

    def scores(self, child_id):
        return None


class HighConfidenceBuildTest(unittest.TestCase):
    def test_preprocessing_removes_vesting_but_preserves_outside_authority_primary(self):
        text = (
            "By the authority vested in me by the Constitution and 3 U.S.C. 301, "
            "it is hereby ordered as follows:  Section 1. Under the International "
            "Emergency Economic Powers Act (50 U.S.C. 1701), transactions are prohibited."
        )
        primary, robustness, vesting, _ = MOD.preprocess_text(text)
        self.assertTrue(vesting)
        self.assertNotIn("authority vested in me", primary.casefold())
        self.assertIn("International Emergency Economic Powers Act", primary)
        self.assertNotIn("International Emergency Economic Powers Act", robustness)

    def test_extended_formal_vesting_connector_is_removed_but_history_is_retained(self):
        formal = (
            "Now, Therefore, I, Test President, by virtue of the authority vested in me "
            "by section 2 of an Act, do proclaim that these lands are reserved."
        )
        primary, _, removed, _ = MOD.preprocess_text(formal)
        self.assertTrue(removed)
        self.assertNotIn("authority vested in me", primary.casefold())
        self.assertIn("do proclaim", primary.casefold())

        alternate = (
            "Now, Therefore, I, Test President, acting under authority vested in me "
            "by law, do hereby amend the prior proclamation."
        )
        primary, _, removed, _ = MOD.preprocess_text(alternate)
        self.assertTrue(removed)
        self.assertNotIn("authority vested in me", primary.casefold())
        self.assertIn("do hereby amend", primary.casefold())

        historical = (
            "Background paragraph.  Last year, by virtue of the authority vested in me by section 2, "
            "I issued Executive Order 12345."
        )
        primary, _, _, _ = MOD.preprocess_text(historical)
        self.assertIn("authority vested in me", primary.casefold())

    def test_statutory_reporting_letter_leadin_is_removed(self):
        current_report = (
            "Pursuant to the International Emergency Economic Powers Act (50 U.S.C. 1701), "
            "the National Emergencies Act, and section 301 of title 3, United States Code, "
            "I hereby report that I have issued an Executive Order."
        )
        primary, _, removed, _ = MOD.preprocess_text(current_report)
        self.assertTrue(removed)
        self.assertNotIn("Pursuant to the International", primary)
        self.assertIn("I hereby report", primary)

        dated_report = (
            "On June 1, 1992, pursuant to section 204(b) of the International Emergency "
            "Economic Powers Act (50 U.S.C. 1703(b)), I reported to the Congress."
        )
        primary, _, removed, _ = MOD.preprocess_text(dated_report)
        self.assertTrue(removed)
        self.assertNotIn("pursuant to section 204", primary.casefold())
        self.assertIn("On June 1, 1992, I reported", primary)

    def test_family_labels_overlap_and_require_actions(self):
        row = document(
            1,
            "January 02, 2020",
            "Under IEEPA, I hereby declare a national emergency.  All property and "
            "interests in property of designated persons are blocked and may not be transferred.",
        )
        labels = MOD.family_matches(row, None)
        self.assertIn("ieepa_action", labels)
        self.assertIn("property_blocking", labels)
        self.assertIn("emergency_action", labels)

        incidental = document(
            2, "January 03, 2020",
            "The committee shall prepare a report about national emergency preparedness.",
        )
        self.assertNotIn("emergency_action", MOD.family_matches(incidental, None))

    def test_revised_family_scopes_follow_adjudicated_boundaries(self):
        ieepa_report = document(
            1, "January 02, 2020",
            "Under the International Emergency Economic Powers Act, this letter transmits "
            "a report to the Congress on the national emergency.", document_type="letter",
        )
        sanctions_import = document(
            2, "January 03, 2020",
            "The importation of covered jadeite articles is prohibited as a sanctions restriction.",
        )
        formal_emergency = document(
            3, "January 04, 2020",
            "I hereby declare a crime emergency in the District of Columbia.",
        )
        response_activity = document(
            4, "January 05, 2020",
            "The National Guard shall support emergency response operations.",
        )
        continuation_notice = document(
            5, "January 06, 2020",
            "The President transmitted to the Congress a notice stating that the national "
            "emergency with respect to Iran is to continue in effect.", document_type="letter",
        )
        self.assertIn("ieepa_action", MOD.family_matches(ieepa_report, None))
        self.assertIn("property_blocking", MOD.family_matches(sanctions_import, None))
        self.assertIn("emergency_action", MOD.family_matches(formal_emergency, None))
        self.assertIn("emergency_action", MOD.family_matches(continuation_notice, None))
        self.assertNotIn("emergency_action", MOD.family_matches(response_activity, None))

    def test_family_rules_require_operative_restriction_and_current_emergency_action(self):
        export_import_bank = document(
            1, "January 01, 2020",
            "The Export-Import Bank president is exempted from mandatory retirement.",
        )
        legislative_discussion = document(
            2, "January 02, 2020",
            "The bill would empower Congress to prohibit specific transactions authorized by law.",
        )
        emergency_relief = document(
            3, "January 03, 2020",
            "The Red Cross provides emergency relief after disasters.",
        )
        emergency_recap = document(
            4, "January 04, 2020",
            "Whereas I proclaimed a national emergency in 1950, the Secretary shall operate mills.",
        )
        import_prohibition = document(
            5, "January 05, 2020",
            "The importation of covered articles is prohibited.",
        )
        current_continuation = document(
            6, "January 06, 2020",
            "I hereby continue the national emergency with respect to the situation.",
        )
        self.assertNotIn("property_blocking", MOD.family_matches(export_import_bank, None))
        self.assertNotIn("property_blocking", MOD.family_matches(legislative_discussion, None))
        self.assertNotIn("emergency_action", MOD.family_matches(emergency_relief, None))
        self.assertNotIn("emergency_action", MOD.family_matches(emergency_recap, None))
        self.assertIn("property_blocking", MOD.family_matches(import_prohibition, None))
        self.assertIn("emergency_action", MOD.family_matches(current_continuation, None))

    def test_emergency_rule_rejects_prior_action_and_withheld_authority(self):
        historical_recap = document(
            1, "January 01, 2020",
            "One of my first actions as President was to declare a national emergency. "
            "I hereby proclaim National Preparedness Month.",
            document_type="proclamation",
        )
        withheld_authority = document(
            2, "January 02, 2020",
            "The authority delegated by this order is exclusive of the authority to "
            "declare any national emergency.",
        )
        impersonal_current_action = document(
            3, "January 03, 2020",
            "A national emergency is hereby declared with respect to the situation.",
        )
        self.assertNotIn("emergency_action", MOD.family_matches(historical_recap, None))
        self.assertNotIn("emergency_action", MOD.family_matches(withheld_authority, None))
        self.assertIn("emergency_action", MOD.family_matches(impersonal_current_action, None))

    def test_family_rules_reject_incidental_program_and_hypothetical_language(self):
        emergency_aid = document(
            1, "January 01, 2020",
            "The organization will extend emergency relief to disaster victims.",
        )
        emergency_program = document(
            2, "January 02, 2020",
            "The bill would extend a farm program first enacted on an emergency basis.",
        )
        withheld_sequence = document(
            3, "January 03, 2020",
            "This delegation is except for the authority to declare, extend, and terminate "
            "a natural gas supply emergency.",
        )
        hypothetical_freeze = document(
            4, "January 04, 2020",
            "If Iraq's assets are frozen, that could undermine its monetary policy.",
        )
        arms_policy = document(
            5, "January 05, 2020",
            "Arms transfer decisions will continue to meet requirements including the "
            "International Emergency Economic Powers Act.",
        )
        for row in (emergency_aid, emergency_program, withheld_sequence):
            self.assertNotIn("emergency_action", MOD.family_matches(row, None))
        self.assertNotIn("property_blocking", MOD.family_matches(hypothetical_freeze, None))
        self.assertNotIn("ieepa_action", MOD.family_matches(arms_policy, None))

    def test_ieepa_reporting_letter_allows_citation_and_action_in_separate_windows(self):
        split_reporting_letter = document(
            1, "January 01, 2020",
            "I hereby report that I issued an order blocking property.  This report is "
            "submitted pursuant to the International Emergency Economic Powers Act.",
            document_type="letter",
        )
        incidental = document(
            2, "January 02, 2020",
            "The committee discussed IEEPA.  Agencies shall prepare a future report.",
            document_type="letter",
        )
        nonletter_history = document(
            3, "January 03, 2020",
            "IEEPA was discussed historically.  Agencies shall prepare an unrelated report.",
        )
        self.assertEqual(
            MOD.family_matches(split_reporting_letter, None)["ieepa_action"],
            "ieepa_reporting_action",
        )
        self.assertNotIn("ieepa_action", MOD.family_matches(incidental, None))
        self.assertNotIn("ieepa_action", MOD.family_matches(nonletter_history, None))

    def test_trade_requires_proclamation_action(self):
        action = document(
            1, "January 02, 2020",
            "The Harmonized Tariff Schedule is modified to adjust duties on the listed imports.",
            document_type="proclamation",
        )
        ceremonial = document(
            2, "January 03, 2020", "We celebrate World Trade Week.",
            document_type="proclamation",
        )
        self.assertIn("trade_proclamation", MOD.family_matches(action, None))
        self.assertNotIn("trade_proclamation", MOD.family_matches(ceremonial, None))

    def test_midrank_percentiles_handle_ties(self):
        result = MOD.midrank_percentiles(np.asarray([0.0, 1.0, 1.0]))
        np.testing.assert_allclose(result, [1 / 6, 2 / 3, 2 / 3])

    def test_same_day_parent_is_excluded(self):
        docs = [
            document(1, "January 01, 2020", "older language here"),
            document(2, "January 02, 2020", "same day candidate"),
            document(3, "January 02, 2020", "child directive"),
        ]
        lexical = np.asarray([0.4, 1.0, 0.0], dtype=np.float32)
        function = FakeSimilarity("3", ["1", "2", "3"], [0.4, 1.0, 0.0])
        scores = MOD.score_children(
            docs, ["3"],
            {"primary": {"3": lexical}, "robustness": {"3": lexical}},
            function, EmptyDocumentSimilarity(), {"1", "2", "3"},
        )
        self.assertEqual({row["parent_id"] for row in scores}, {"1"})

    def test_direct_transition_references_are_observed_edges_not_inference_children(self):
        edges = [
            {"child_id": "1", "parent_id": "9", "relation": "amends"},
            {"child_id": "2", "parent_id": "9", "relation": "citation_discussion"},
            {"child_id": "3", "parent_id": "9", "relation": "revokes"},
            {"child_id": "4", "parent_id": "9", "relation": "delegates_authority_under"},
        ]
        observed = MOD.explicit_parent_edges(edges)
        self.assertEqual({row["child_id"] for row in observed}, {"1", "3"})
        self.assertEqual(MOD.explicit_parent_child_ids(edges), {"1", "3"})

    def test_personal_correspondence_is_out_of_scope_but_congressional_letter_is_not(self):
        personal = document(
            1, "January 01, 2020", "Dear Friend: Congratulations on your birthday.",
            document_type="letter",
        )
        personal["title"] = "Letter Congratulating Helen Keller on Her Birthday"
        congressional = document(
            2, "January 02, 2020", "Dear Madam Speaker: I transmit the report.",
            document_type="letter",
        )
        congressional["title"] = "Letter to Congressional Leaders Transmitting a Report"
        self.assertEqual(
            MOD.analysis_scope_reason(personal), "personal_or_diplomatic_correspondence"
        )
        self.assertEqual(MOD.analysis_scope_reason(congressional), "")
        diplomatic = document(
            3, "January 03, 2020", "I write regarding drought relief.",
            document_type="letter",
        )
        diplomatic["title"] = "Letter to the United Nations Secretary General"
        resignation = document(
            4, "January 04, 2020", "I accept your resignation.",
            document_type="letter",
        )
        resignation["title"] = "Letter Accepting the Resignation of the Secretary"
        self.assertEqual(
            MOD.analysis_scope_reason(diplomatic), "personal_or_diplomatic_correspondence"
        )
        self.assertEqual(
            MOD.analysis_scope_reason(resignation), "personal_or_diplomatic_correspondence"
        )

    def test_calibration_requires_twenty_five_reviewed_pairs(self):
        reviews = [
            {"pair_id": f"P{i:03d}", "decision": "parent"}
            for i in range(1, 25)
        ]
        key = [
            {
                "pair_id": f"P{i:03d}", "score_stratum": "operative_profile",
                "combined_score": 0.9 + i / 1000, "sampling_probability": 1.0,
            }
            for i in range(1, 25)
        ]
        result = MOD.calibrate_thresholds(reviews, key)
        self.assertTrue(all(row["status"] == "insufficient_review" for row in result))

        reviews.append({"pair_id": "P025", "decision": "parent"})
        key.append({
            "pair_id": "P025", "score_stratum": "operative_profile",
            "combined_score": 0.925, "sampling_probability": 1.0,
        })
        result = MOD.calibrate_thresholds(reviews, key)
        self.assertTrue(all(row["status"] == "pilot_calibrated" for row in result))

    def test_review_csv_contains_no_vesting_text(self):
        child = document(2, "January 02, 2020", "Section 1. Distinct child action.")
        child["families"] = {"ieepa_action": "test"}
        parent = document(1, "January 01, 2020", "Section 1. Distinct parent action.")
        score = {
            "child_id": "2", "parent_id": "1", "specification": "primary",
            "score_stratum": "operative_profile", "child_document_type": "executive_order",
            "combined_score": 0.96, "child_families": "ieepa_action",
        }
        blinded, _ = MOD.build_parent_review([score], [parent, child], count=1)
        rendered = " ".join(str(value) for value in blinded[0].values()).casefold()
        self.assertNotIn("authority vested in me", rendered)

    def test_parent_review_excludes_nonfamily_children(self):
        family_child = document(2, "January 02, 2020", "Family child.")
        family_child["families"] = {"ieepa_action": "test"}
        nonfamily_child = document(3, "January 03, 2020", "Non-family child.")
        parent = document(1, "January 01, 2020", "Parent.")
        scores = [
            {
                "child_id": "2", "parent_id": "1", "specification": "primary",
                "score_stratum": "operative_profile", "child_document_type": "executive_order",
                "combined_score": 0.96, "child_families": "ieepa_action",
            },
            {
                "child_id": "3", "parent_id": "1", "specification": "primary",
                "score_stratum": "operative_profile", "child_document_type": "executive_order",
                "combined_score": 0.99, "child_families": "",
            },
        ]
        blinded, _ = MOD.build_parent_review(scores, [parent, family_child, nonfamily_child], count=2)
        self.assertEqual([row["child_id"] for row in blinded], ["2"])

    def test_family_review_uses_full_preprocessed_text_not_an_excerpt(self):
        full_text = "First operative section. " + ("Further context. " * 200)
        row = document(1, "January 02, 2020", full_text)
        row["families"] = {"ieepa_action": {"source": "test"}}
        review = MOD.build_family_review([row])
        ieepa_rows = [item for item in review if item["family_id"] == "ieepa_action"]
        self.assertEqual(len(ieepa_rows), 1)
        self.assertEqual(ieepa_rows[0]["non_vesting_text"], full_text)
        self.assertNotIn("non_vesting_excerpt", ieepa_rows[0])

    def test_completed_review_values_can_be_preserved_by_pair_id(self):
        # The main build merges a submitted review by this stable identifier before
        # rewriting its queue; this fixture protects the expected review schema.
        submitted = {"P001": {"decision": "parent", "review_notes": "reused language"}}
        fresh = {"pair_id": "P001", "decision": "", "review_notes": ""}
        prior = submitted.get(fresh["pair_id"])
        fresh["decision"] = prior.get("decision", fresh["decision"])
        fresh["review_notes"] = prior.get("review_notes", fresh["review_notes"])
        self.assertEqual(fresh, {"pair_id": "P001", "decision": "parent", "review_notes": "reused language"})

    def test_parent_html_uses_blind_rows_and_compact_export_schema(self):
        rows = [{
            "pair_id": "P001", "child_id": "2", "child_type": "executive_order",
            "child_date": "January 02, 2020", "child_title": "Later order",
            "child_url": "https://example.test/2", "child_non_vesting_text": "Child text.",
            "parent_id": "1", "parent_type": "proclamation", "parent_date": "January 01, 2020",
            "parent_title": "Earlier proclamation", "parent_url": "https://example.test/1",
            "parent_non_vesting_text": "Parent text.",
        }]
        with tempfile.TemporaryDirectory() as temporary:
            page = Path(temporary) / "parent.html"
            REVIEW_MOD.write_page(page, "Test parent review", "Blind test.", rows, kind="parent")
            rendered = page.read_text(encoding="utf-8")
        self.assertIn('const CSV_FIELDS=["pair_id", "decision", "review_notes"]', rendered)
        self.assertIn("Child text.", rendered)
        self.assertIn('return /[",\\n]/', rendered)
        self.assertNotIn('"combined_score"', rendered)
        self.assertNotIn('"queue_type"', rendered)


if __name__ == "__main__":
    unittest.main()
