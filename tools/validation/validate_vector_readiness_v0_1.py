#!/usr/bin/env python3
"""Validate vector readiness evaluator (R6)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "validation" / "evaluate_vector_retrieval_readiness_v0_1.py"


def main():
    with tempfile.TemporaryDirectory(prefix="mk-vector-readiness-v01-") as td:
        tmp = Path(td)
        out_json = tmp / "vector.json"
        out_md = tmp / "vector.md"

        cmd = [
            "python3",
            str(SCRIPT),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--query-volume-per-day",
            "40",
            "--min-corpus-for-vector",
            "5000",
        ]
        p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
        if p.returncode != 0:
            raise SystemExit(f"vector readiness failed\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")

        report = json.loads(out_json.read_text(encoding="utf-8"))
        label = str(report.get("decision", {}).get("label") or "")
        assert label in {"GO_PILOT", "NO_GO_KEEP_FTS"}, "decision label invalid"
        assert out_md.exists(), "markdown output should exist"

        print(
            json.dumps(
                {
                    "ok": True,
                    "tmp": str(tmp),
                    "decision": label,
                    "out_json": str(out_json),
                    "out_md": str(out_md),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
