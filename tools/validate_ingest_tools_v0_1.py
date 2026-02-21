#!/usr/bin/env python3
"""Validate ingest tooling v0.1 (migration + session parser)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
FIXTURE_WS = ROOT / "data" / "fixtures" / "memory-workspace"
FIXTURE_SESSION = ROOT / "data" / "fixtures" / "session-logs" / "sample-session.jsonl"


def run(cmd: list[str]):
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return p.stdout


def main():
    if not FIXTURE_WS.exists():
        raise SystemExit(f"fixture workspace missing: {FIXTURE_WS}")
    if not FIXTURE_SESSION.exists():
        raise SystemExit(f"fixture session missing: {FIXTURE_SESSION}")

    tmp = Path(tempfile.mkdtemp(prefix="mk-ingest-v01-"))
    migrate_out = tmp / "migrate_report.json"
    parse_out = tmp / "parse_report.json"
    memory_jsonl = tmp / "memory_rows.jsonl"

    run(
        [
            "python3",
            str(TOOLS / "migrate_memory_md_to_objects_v0_1.py"),
            "--workspace",
            str(FIXTURE_WS),
            "--input",
            "memory.md",
            "--out",
            str(migrate_out),
        ]
    )

    migrate = json.loads(migrate_out.read_text())
    assert migrate.get("ok") is True, "migrate dry-run should be ok"
    assert int(migrate.get("summary", {}).get("total_candidates", 0)) >= 1, "should produce at least one candidate"

    run(
        [
            "python3",
            str(TOOLS / "parse_session_jsonl_v0_1.py"),
            "--session-file",
            str(FIXTURE_SESSION),
            "--out",
            str(parse_out),
            "--memory-jsonl-out",
            str(memory_jsonl),
            "--review-due-days",
            "7",
            "--next-action-days",
            "7",
        ]
    )

    parsed = json.loads(parse_out.read_text())
    assert parsed.get("ok") is True, "parse report should be ok"
    assert int(parsed.get("summary", {}).get("count", 0)) >= 3, "should extract >=3 events"
    by_type = parsed.get("summary", {}).get("by_type", {})
    assert "workflow_directive" in by_type, "should include workflow_directive"
    assert "milestone_completed" in by_type, "should include milestone_completed"
    assert "user_request" in by_type, "should include user_request"

    # Validate emitted memory rows against memory schema
    import sys

    sys.path.insert(0, str(TOOLS))
    from schema_runtime import validate_payload  # noqa: WPS433

    rows = [json.loads(x) for x in memory_jsonl.read_text().splitlines() if x.strip()]
    assert rows, "memory jsonl should not be empty"

    for idx, row in enumerate(rows, start=1):
        validate_payload("memory.schema.json", row)
        assert row.get("source", {}).get("source_ref", "").startswith(
            "session://sample-session-001#msg:"
        ), f"row {idx} source_ref should point to sample session"

    out = {
        "ok": True,
        "tmp": str(tmp),
        "migrate_candidates": int(migrate.get("summary", {}).get("total_candidates", 0)),
        "parsed_events": int(parsed.get("summary", {}).get("count", 0)),
        "memory_rows": len(rows),
        "by_type": by_type,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
