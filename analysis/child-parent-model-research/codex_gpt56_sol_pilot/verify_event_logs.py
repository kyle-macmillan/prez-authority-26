#!/usr/bin/env python3
"""Fail when a Codex JSON event log records a tool invocation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FORBIDDEN = ("tool", "command_execution", "web_search", "mcp")


def values(value):
    if isinstance(value, dict):
        if isinstance(value.get("type"), str):
            yield value["type"]
        for child in value.values():
            yield from values(child)
    elif isinstance(value, list):
        for child in value:
            yield from values(child)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_dir", type=Path)
    args = parser.parse_args()
    violations = []
    for path in sorted(args.log_dir.glob("*.events.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            types = set(values(json.loads(line)))
            found = sorted(kind for kind in types if any(flag in kind.lower() for flag in FORBIDDEN))
            if found:
                violations.append({"file": str(path), "line": line_number, "event_types": found})
    report = {"logs_checked": len(list(args.log_dir.glob("*.events.jsonl"))), "tool_violations": violations}
    print(json.dumps(report, indent=2))
    if violations:
        raise SystemExit("tool activity detected; reject the affected run(s)")


if __name__ == "__main__":
    main()
