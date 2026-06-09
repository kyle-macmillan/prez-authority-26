"""
Parse exported annotation files from the segment viewer.

The viewer exports a JSON file (via the "Export annotations" button) with this shape:

  {
    "annotator": "Kyle",          # optional
    "EO1": {
      "status": "correct",        # optional: "correct" | "needs-revision"
      "comment": "...",           # optional
      "annotations": [
        {"start": 10, "end": 50, "label": "section"},
        ...
      ]
    },
    ...
  }

Char offsets (start/end) are into the display text for that document.  The display
text is double-space-separated chunks joined with blank lines:

  "\n\n".join(chunk.strip() for chunk in re.split(r"  +", doc_text) if chunk.strip())

Usage:
  records = load_annotations("seg-annotations.json", "data/4_28_2026_build_dev.csv",
                              "data/sample_segmentation/doc_id_map.json")
  for r in records:
      print(r["doc_id"], r["label"], repr(r["text"][:60]))
"""

import csv
import json
import re
from pathlib import Path


VALID_LABELS = {
    "preamble", "order_action", "vesting_clause",
    "metadata", "boilerplate", "section", "paragraph",
}


def display_text(doc_text: str) -> str:
    return "\n\n".join(c.strip() for c in re.split(r"  +", doc_text) if c.strip())


def load_annotations(
    annotations_path: str | Path,
    data_path: str | Path,
    doc_id_map_path: str | Path,
) -> list[dict]:
    """Load and resolve an annotation export file.

    Returns a list of records, one per annotation span:
      {
        "doc_id":    str,   # e.g. "EO1"
        "row_index": int,   # original CSV index (the '' column)
        "url":       str,
        "president": str,
        "date":      str,
        "doc_type":  str,
        "start":     int,   # char offset in display text
        "end":       int,
        "label":     str,
        "text":      str,   # the annotated span
        "status":    str | None,
        "comment":   str | None,
      }
    """
    export = json.loads(Path(annotations_path).read_text())
    doc_id_map: dict[str, int] = json.loads(Path(doc_id_map_path).read_text())

    # Build lookup by original CSV index column (stable across file splits)
    rows_by_index: dict[int, dict] = {}
    with open(data_path) as f:
        for row in csv.DictReader(f):
            rows_by_index[int(row[""])] = row

    records = []
    for doc_id, doc_data in export.items():
        if doc_id == "annotator":
            continue
        if not isinstance(doc_data, dict):
            continue

        row_index = doc_id_map.get(doc_id)
        if row_index is None:
            raise KeyError(f"doc_id {doc_id!r} not found in doc_id_map")
        if row_index not in rows_by_index:
            raise KeyError(f"doc_id {doc_id!r} (csv index {row_index}) not found in data file")

        row = rows_by_index[row_index]
        dtext = display_text(row["doc_text"])
        status = doc_data.get("status")
        comment = doc_data.get("comment") or None

        for ann in doc_data.get("annotations", []):
            start, end, label = ann["start"], ann["end"], ann["label"]
            records.append({
                "doc_id":    doc_id,
                "row_index": row_index,
                "url":       row["url"],
                "president": row["president"],
                "date":      row["date"],
                "doc_type":  row["doc_type"],
                "start":     start,
                "end":       end,
                "label":     label,
                "text":      dtext[start:end],
                "status":    status,
                "comment":   comment,
            })

    return records


def validate_export(
    export: dict,
    doc_id_map: dict[str, int],
    all_display_texts: dict[str, str],
) -> list[str]:
    """Validate an annotation export dict.  Returns a list of error strings (empty = OK)."""
    errors = []
    for doc_id, doc_data in export.items():
        if doc_id == "annotator":
            continue
        if not isinstance(doc_data, dict):
            errors.append(f"{doc_id}: expected dict, got {type(doc_data).__name__}")
            continue
        if doc_id not in doc_id_map:
            errors.append(f"{doc_id}: not in doc_id_map")
            continue

        dtext = all_display_texts.get(doc_id, "")
        text_len = len(dtext)

        for i, ann in enumerate(doc_data.get("annotations", [])):
            prefix = f"{doc_id} ann[{i}]"
            if not isinstance(ann.get("start"), int):
                errors.append(f"{prefix}: 'start' must be int")
            if not isinstance(ann.get("end"), int):
                errors.append(f"{prefix}: 'end' must be int")
            if not isinstance(ann.get("label"), str):
                errors.append(f"{prefix}: 'label' must be str")
                continue
            start, end = ann.get("start", 0), ann.get("end", 0)
            if start < 0 or end > text_len or start >= end:
                errors.append(
                    f"{prefix}: offsets [{start}:{end}] invalid for text length {text_len}"
                )
            if ann["label"] not in VALID_LABELS:
                errors.append(f"{prefix}: unknown label {ann['label']!r}")

    return errors
