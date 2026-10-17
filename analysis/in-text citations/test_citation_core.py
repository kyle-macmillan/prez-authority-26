import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from citation_core import (
    TextSegment, build_segments, entity_set, regex_citations, validate_body_vesting_links, validate_citations,
)


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

    def test_offsets_must_locate_verbatim_evidence(self):
        request = {"document_id": "9", "segments": [{
            "segment_id": "B001", "region": "body", "text": "Executive Order 12345 applies.",
        }]}
        response = {
            "document_id": "9", "unresolved_identity_links": [],
            "citations": [{
                "region": "body", "segment_id": "B001", "evidence": "Executive Order 12345",
                "start": 1, "end": 22, "source_type": "presidential_directive",
                "instrument_label": "Executive Order 12345", "instrument_keys": ["eo:12345"],
                "provision_keys": [], "generic": False, "excluded": False,
                "exclusion_reason": "",
            }],
        }
        with self.assertRaisesRegex(ValueError, "offsets"):
            validate_citations(response, request)

    def test_unresolved_links_must_connect_cited_keys(self):
        request = {"document_id": "9", "segments": [{
            "segment_id": "B001", "region": "body", "text": "Executive Order 12345 applies.",
        }]}
        response = {
            "document_id": "9",
            "citations": [{
                "region": "body", "segment_id": "B001", "evidence": "Executive Order 12345",
                "source_type": "presidential_directive", "instrument_label": "Executive Order 12345",
                "instrument_keys": ["eo:12345"], "provision_keys": [], "generic": False,
                "excluded": False, "exclusion_reason": "",
            }],
            "unresolved_identity_links": [{
                "left_instrument_key": "eo:12345", "right_instrument_key": "eo:99999",
                "reason": "The text does not establish whether these labels are equivalent.",
            }],
        }
        with self.assertRaisesRegex(ValueError, "distinct cited instrument keys"):
            validate_citations(response, request)

    def test_body_authorities_require_explicit_valid_vesting_decisions(self):
        response = {
            "citations": [
                {"region": "vesting", "excluded": False, "instrument_keys": ["act:clean-air"]},
                {"region": "body", "excluded": False, "instrument_keys": ["act:clean-air", "eo:12345"]},
            ],
            "body_vesting_links": [
                {"body_instrument_key": "act:clean-air", "vesting_instrument_key": "act:clean-air"},
                {"body_instrument_key": "eo:12345", "vesting_instrument_key": None},
            ],
        }
        validate_body_vesting_links(response)
        response["body_vesting_links"][1]["vesting_instrument_key"] = "eo:99999"
        with self.assertRaisesRegex(ValueError, "unknown vesting key"):
            validate_body_vesting_links(response)

    def test_only_the_documents_own_invocation_is_vesting(self):
        sys.path.insert(0, str(HERE.parents[1] / "src"))
        text = (
            "On November 22, 1956, by virtue of the authority vested in me by Section 206 of the "
            "Labor Management Relations Act, 1947, I issued Executive Order 10689, creating a Board "
            "of Inquiry. Today I received the Board's written report. I therefore direct you, "
            "pursuant to the provisions of Section 208 of the Labor Management Relations Act, 1947, "
            "to petition any District Court of the United States to enjoin such strike."
        )
        segments = {segment.text[:20]: segment for segment in build_segments(text, "letter")[0]}
        self.assertEqual(segments["On November 22, 1956"].region, "vesting")
        rejected = segments["pursuant to the prov"]
        self.assertEqual((rejected.segment_id, rejected.region), ("B003", "body"))
        self.assertEqual(rejected.source_type, "rejected_vesting_clause")


if __name__ == "__main__":
    unittest.main()
