#!/usr/bin/env python3
"""Validate llm_memory_processor_v0_1 in mock mode."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
FIXTURE = ROOT / "data" / "fixtures" / "llm-memory" / "sample-memory-input.txt"


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return p.stdout


def main():
    if not FIXTURE.exists():
        raise SystemExit(f"fixture not found: {FIXTURE}")

    tmp = Path(tempfile.mkdtemp(prefix="mk-llm-mem-v01-"))
    out_json = tmp / "llm_extract.json"
    out_jsonl = tmp / "llm_extract.memory.jsonl"

    run(
        [
            "python3",
            str(TOOLS / "llm_memory_processor_v0_1.py"),
            "--backend",
            "mock",
            "--model",
            "mock-v0",
            "--source-ref",
            "session://sample-session-001#msg:u1",
            "--text-file",
            str(FIXTURE),
            "--max-items",
            "5",
            "--out",
            str(out_json),
            "--jsonl-out",
            str(out_jsonl),
        ]
    )

    report = json.loads(out_json.read_text())
    assert report.get("ok") is True, "report should be ok"
    assert report.get("backend") == "mock", "backend should be mock"
    assert int(report.get("count", 0)) >= 3, "should output at least 3 memory items"

    # schema validation
    import sys

    sys.path.insert(0, str(TOOLS))
    from schema_runtime import validate_payload  # noqa: WPS433

    rows = [json.loads(x) for x in out_jsonl.read_text().splitlines() if x.strip()]
    assert rows, "jsonl should not be empty"

    for idx, row in enumerate(rows, start=1):
        validate_payload("memory.schema.json", row)
        assert row.get("source", {}).get("source_ref", "").startswith(
            "session://sample-session-001"
        ), f"row {idx} source_ref mismatch"

    print(
        json.dumps(
            {
                "ok": True,
                "tmp": str(tmp),
                "count": len(rows),
                "sample_id": rows[0]["id"],
                "sample_kind": rows[0]["kind"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
