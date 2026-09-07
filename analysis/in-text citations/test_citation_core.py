import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from citation_core import TextSegment, entity_set, regex_citations, validate_citations


class CitationCoreTests(unittest.TestCase):
    def test_extracts_vesting_and_body_sources(self):
        segments = [
            TextSegment("V001", "vesting", "under the Clean Air Act (42 U.S.C. 7401)", "vesting_clause"),
            TextSegment("B001", "body", "Executive Order 12345 and 40 C.F.R. 1.2 apply.", "order_action"),
        ]
        rows = regex_citations("7", segments)
        included = [row for row in rows if not row["excluded"]]
        self.assertTrue(any(row["region"] == "vesting" and row["source_type"] == "statute_or_code" for row in included))
        self.assertTrue(any(row["source_type"] == "presidential_directive" for row in included))
        self.assertTrue(any(row["source_type"] == "regulation" for row in included))

    def test_vague_reference_is_audited_but_excluded(self):
        rows = regex_citations("8", [TextSegment(
            "B001", "body", "This order shall be implemented consistent with applicable law.", "boilerplate",
        )])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["excluded"])
        self.assertEqual(entity_set(rows, "instrument"), set())

    def test_format_variants_share_instrument_but_subsections_do_not(self):
        rows = regex_citations("10", [
            TextSegment("V001", "vesting", "42 U.S.C. 7401(a)", "vesting_clause"),
            TextSegment("B001", "body", "42 USC 7401(b)", "order_action"),
        ])
        vest = {key for region, key in entity_set(rows, "instrument") if region == "vesting"}
        body = {key for region, key in entity_set(rows, "instrument") if region == "body"}
        self.assertEqual(vest, body)
        vest_provision = {key for region, key in entity_set(rows, "provision") if region == "vesting"}
        body_provision = {key for region, key in entity_set(rows, "provision") if region == "body"}
        self.assertFalse(vest_provision & body_provision)

    def test_response_evidence_must_be_verbatim(self):
        request = {"document_id": "9", "segments": [{"segment_id": "B001", "region": "body", "text": "Executive Order 12345 applies."}]}
        response = {
            "document_id": "9", "unresolved_identity_links": [],
            "citations": [{
                "region": "body", "segment_id": "B001", "evidence": "Executive Order 99999",
                "source_type": "presidential_directive", "instrument_label": "Executive Order 99999",
                "instrument_keys": ["eo:99999"], "provision_keys": [], "generic": False,
                "excluded": False, "exclusion_reason": "",
            }],
        }
        with self.assertRaisesRegex(ValueError, "verbatim"):
            validate_citations(response, request)


if __name__ == "__main__":
    unittest.main()
