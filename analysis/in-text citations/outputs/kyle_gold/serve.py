"""Local server for annotator.html: serves the sample and saves annotations.jsonl.

python3 serve.py [port]   then open http://localhost:8765
"""
import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
DOCS = HERE.parent / "benchmark" / "documents.jsonl"
OUT = HERE / "annotations.jsonl"


def load_rows():
    return [json.loads(l) for l in OUT.open()] if OUT.exists() else []


def load_docs():
    return {d["document_id"]: d for d in map(json.loads, DOCS.open())}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.path = "/annotator.html"
        if self.path != "/api/data":
            return super().do_GET()
        ids = json.loads((HERE / "sample.json").read_text())["document_ids"]
        docs = load_docs()
        self.send_json({
            "documents": [docs[i] for i in ids],
            "annotations": {r["document_id"]: r for r in load_rows()},
        })

    def do_POST(self):
        if self.path != "/api/save":
            return self.send_error(404)
        rec = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        segments = {s["segment_id"]: s for s in load_docs()[rec["document_id"]]["segments"]}
        for c in rec["citations"]:
            if segments[c["segment_id"]]["text"][c["start"]:c["end"]] != c["evidence"]:
                return self.send_json({"error": f"offset mismatch: {c['evidence']!r}"}, 400)
        rows = [r for r in load_rows() if r["document_id"] != rec["document_id"]] + [rec]
        OUT.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.send_json({"ok": True})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
