import json
import sys

import embed_function_profiles


def test_incomplete_snapshot_can_be_embedded_explicitly(tmp_path, monkeypatch):
    (tmp_path / "profiles.jsonl").write_text("")
    (tmp_path / "snapshot_manifest.json").write_text(json.dumps({
        "snapshot_hash": "test-snapshot",
        "complete": False,
        "canonical_profiles": 9640,
        "operative_directives": 9762,
        "requests_remaining": 122,
    }))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "embed_function_profiles.py",
            "--snapshot-dir",
            str(tmp_path),
            "--allow-incomplete-profiles",
        ],
    )

    embed_function_profiles.main()

    manifest = json.loads((tmp_path / "function_embedding_manifest.json").read_text())
    assert manifest["source_snapshot_complete"] is False
    assert manifest["allow_incomplete_profiles"] is True
    assert manifest["canonical_profiles"] == 9640
    assert manifest["operative_directives"] == 9762
    assert manifest["profiles_missing"] == 122
