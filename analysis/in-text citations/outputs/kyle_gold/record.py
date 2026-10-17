"""Record one document's hand annotations (JSON on stdin) into annotations.jsonl.

Input: {"document_id": "...", "citations": [{"segment_id", "evidence", "instrument_key",
"provision_key" (or null), "generic" (bool), "antecedent" (text of the earlier full
citation when evidence is a short form like "the Act", else null)}], "note": "..."}
Optional "outside_links": [{"a": evidence, "b": evidence, "basis": "..."}] join citations
the annotator knows are the same authority without a textual link (codebook rule 12).
Evidence must appear verbatim in the segment; offsets are filled in here.
Re-recording a document replaces its earlier entry.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
DOCS = HERE.parent / "benchmark" / "documents.jsonl"
OUT = HERE / "annotations.jsonl"

spec = json.load(sys.stdin)
doc = next(d for d in map(json.loads, DOCS.open()) if d["document_id"] == spec["document_id"])
segments = {s["segment_id"]: s for s in doc["segments"]}
for c in spec["citations"]:
    seg = segments[c["segment_id"]]
    start = seg["text"].find(c["evidence"])
    if start < 0:
        sys.exit(f"evidence not found in {c['segment_id']}: {c['evidence']!r}")
    c.update(region=seg["region"], start=start, end=start + len(c["evidence"]))

rows = [r for r in map(json.loads, OUT.open()) if r["document_id"] != spec["document_id"]] if OUT.exists() else []
rows.append({"document_id": spec["document_id"], "citations": spec["citations"], "outside_links": spec.get("outside_links", []), "note": spec.get("note", "")})
OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))
print(f"recorded {spec['document_id']}: {len(spec['citations'])} citations; {len(rows)} documents total")
