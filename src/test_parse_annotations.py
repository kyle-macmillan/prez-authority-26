"""
Tests for annotation export parsing.

Run from the project root:
  python3 src/test_parse_annotations.py
"""

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_annotations import display_text, load_annotations, validate_export, VALID_LABELS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent
DATA_FILE   = ROOT / "data" / "4_28_2026_build_dev.csv"
DOC_ID_MAP  = ROOT / "data" / "sample_segmentation" / "doc_id_map.json"


def _make_export(doc_id: str, dtext: str, label: str, start: int, end: int) -> dict:
    return {
        "annotator": "tester",
        doc_id: {
            "status": "correct",
            "annotations": [{"start": start, "end": end, "label": label}],
        },
    }


# ---------------------------------------------------------------------------
# Unit tests (synthetic data, no CSV needed)
# ---------------------------------------------------------------------------

def test_display_text_roundtrip():
    """Double-space-separated chunks become \n\n-separated display text."""
    doc_text = "Hello world  Second paragraph  Third"
    dt = display_text(doc_text)
    assert dt == "Hello world\n\nSecond paragraph\n\nThird"


def test_display_text_extra_spaces():
    """Three or more spaces are treated the same as two."""
    assert display_text("A   B    C") == "A\n\nB\n\nC"


def test_validate_export_valid():
    dtext = "The quick brown fox jumps over the lazy dog."
    doc_id_map = {"EO1": 0}
    display_texts = {"EO1": dtext}
    export = _make_export("EO1", dtext, "paragraph", 4, 15)
    errors = validate_export(export, doc_id_map, display_texts)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_validate_export_unknown_label():
    dtext = "Some document text here."
    doc_id_map = {"EO1": 0}
    display_texts = {"EO1": dtext}
    export = {"EO1": {"annotations": [{"start": 0, "end": 4, "label": "unknown_label"}]}}
    errors = validate_export(export, doc_id_map, display_texts)
    assert any("unknown label" in e for e in errors), f"Expected unknown-label error, got: {errors}"


def test_validate_export_out_of_bounds():
    dtext = "Short text."
    doc_id_map = {"M1": 0}
    display_texts = {"M1": dtext}
    export = {"M1": {"annotations": [{"start": 0, "end": 9999, "label": "paragraph"}]}}
    errors = validate_export(export, doc_id_map, display_texts)
    assert any("invalid" in e for e in errors), f"Expected offset error, got: {errors}"


def test_validate_export_inverted_offsets():
    dtext = "Some text."
    doc_id_map = {"P1": 0}
    display_texts = {"P1": dtext}
    export = {"P1": {"annotations": [{"start": 5, "end": 2, "label": "paragraph"}]}}
    errors = validate_export(export, doc_id_map, display_texts)
    assert any("invalid" in e for e in errors), f"Expected inverted-offset error, got: {errors}"


def test_validate_export_missing_doc_id():
    export = {"ZZ99": {"annotations": []}}
    errors = validate_export(export, doc_id_map={}, all_display_texts={})
    assert any("not in doc_id_map" in e for e in errors)


def test_validate_export_annotator_key_skipped():
    """Top-level 'annotator' key should not be treated as a doc entry."""
    export = {"annotator": "Kyle"}
    errors = validate_export(export, doc_id_map={}, all_display_texts={})
    assert errors == []


def test_all_labels_are_valid():
    """Every label in VALID_LABELS passes its own validation."""
    dtext = "x" * 200
    doc_id_map = {"EO1": 0}
    display_texts = {"EO1": dtext}
    for label in VALID_LABELS:
        export = {"EO1": {"annotations": [{"start": 0, "end": 10, "label": label}]}}
        errors = validate_export(export, doc_id_map, display_texts)
        assert errors == [], f"Label {label!r} unexpectedly failed: {errors}"


# ---------------------------------------------------------------------------
# Integration tests (require the CSV and doc_id_map.json)
# ---------------------------------------------------------------------------

def test_load_annotations_roundtrip():
    """Write a synthetic export for a real doc, load it, verify text spans."""
    if not DATA_FILE.exists():
        print("  SKIP test_load_annotations_roundtrip: data file not found")
        return
    if not DOC_ID_MAP.exists():
        print("  SKIP test_load_annotations_roundtrip: doc_id_map.json not found (run view_segments.py first)")
        return

    doc_id_map = json.loads(DOC_ID_MAP.read_text())
    doc_id = next(iter(doc_id_map))  # first doc in the map

    import csv as _csv
    with open(DATA_FILE) as f:
        rows_by_index = {int(r[""]): r for r in _csv.DictReader(f)}
    row_index = doc_id_map[doc_id]
    dtext = display_text(rows_by_index[row_index]["doc_text"])

    # Annotate the first 20 chars with label "paragraph"
    start, end = 0, min(20, len(dtext))
    export = _make_export(doc_id, dtext, "paragraph", start, end)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(export, f)
        tmp_path = f.name

    try:
        records = load_annotations(tmp_path, DATA_FILE, DOC_ID_MAP)
    finally:
        Path(tmp_path).unlink()

    assert len(records) == 1
    r = records[0]
    assert r["doc_id"] == doc_id
    assert r["label"] == "paragraph"
    assert r["text"] == dtext[start:end]
    assert r["row_index"] == row_index


def test_validate_export_against_real_map():
    """Validate a synthetic export against the real doc_id_map."""
    if not DATA_FILE.exists() or not DOC_ID_MAP.exists():
        print("  SKIP test_validate_export_against_real_map: files not found")
        return

    doc_id_map = json.loads(DOC_ID_MAP.read_text())

    import csv as _csv
    with open(DATA_FILE) as f:
        rows_by_index = {int(r[""]): r for r in _csv.DictReader(f)}

    display_texts = {
        doc_id: display_text(rows_by_index[row_index]["doc_text"])
        for doc_id, row_index in doc_id_map.items()
    }

    # Build a synthetic export with one valid annotation per doc
    export: dict = {"annotator": "tester"}
    for doc_id, dtext in display_texts.items():
        end = min(30, len(dtext))
        export[doc_id] = {"annotations": [{"start": 0, "end": end, "label": "paragraph"}]}

    errors = validate_export(export, doc_id_map, display_texts)
    assert errors == [], f"Unexpected errors: {errors}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
