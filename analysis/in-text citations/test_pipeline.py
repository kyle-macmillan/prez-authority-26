import json
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pipeline import build_requests, score, write_jsonl
from run_models import attempted_ids


def citation(document_id: str) -> dict:
    return {
        "document_id": document_id, "region": "body", "segment_id": "B001",
        "evidence": "Executive Order 12345", "source_type": "presidential_directive",
        "instrument_label": "Executive Order 12345", "instrument_keys": ["eo:12345"],
        "provision_keys": ["eo:12345:section-1"], "generic": False, "excluded": False,
        "exclusion_reason": "", "method": "regex",
    }


class PipelineTests(unittest.TestCase):
    def test_started_attempt_is_recorded_as_spent_or_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempts.jsonl"
            write_jsonl(path, [
                {"document_id": "1", "event": "started"},
                {"document_id": "2", "event": "completed"},
            ])
            self.assertEqual(attempted_ids(path), {"1"})

    def test_perfect_locked_predictions_are_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gold = []
            predictions = []
            for value in range(100):
                document_id = str(value)
                gold.append({"document_id": document_id, "split": "evaluation", "certified": True,
                             "citations": [citation(document_id)], "unresolved_identity_links": []})
                predictions.append({"document_id": document_id, "citations": [citation(document_id)],
                                    "unresolved_identity_links": []})
            write_jsonl(root / "gold.jsonl", gold)
            write_jsonl(root / "predictions.jsonl", predictions)
            score(root / "gold.jsonl", [f"regex={root / 'predictions.jsonl'}"], root / "score.json")
            result = json.loads((root / "score.json").read_text())
            self.assertEqual(result["selected_method"], "regex")
            self.assertTrue(result["methods"]["regex"]["eligible"])

    def test_production_request_building_requires_passing_score(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_jsonl(root / "documents.jsonl", [{
                "document_id": "1", "split": "production",
                "segments": [{"segment_id": "B001", "region": "body", "text": "No citation."}],
            }])
            with self.assertRaisesRegex(ValueError, "benchmark-score"):
                build_requests(root / "documents.jsonl", "terra", root / "requests.jsonl")


if __name__ == "__main__":
    unittest.main()
