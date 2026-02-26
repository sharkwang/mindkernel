#!/usr/bin/env python3
"""Validate scheduler benchmark script (R5)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "tools" / "validation" / "benchmark_scheduler_throughput_v0_1.py"


def main():
    with tempfile.TemporaryDirectory(prefix="mk-bench-validate-v01-") as td:
        tmp = Path(td)
        out_json = tmp / "bench.json"
        out_md = tmp / "bench.md"

        cmd = [
            "python3",
            str(BENCH),
            "--jobs",
            "120",
            "--workers",
            "3",
            "--batch",
            "25",
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--profile",
            "validate",
        ]
        p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
        if p.returncode != 0:
            raise SystemExit(f"benchmark failed\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")

        report = json.loads(out_json.read_text(encoding="utf-8"))
        throughput = float(report.get("benchmark", {}).get("throughput_jobs_per_min", 0.0) or 0.0)
        retry_rate = float(report.get("benchmark", {}).get("retry_rate_percent", 0.0) or 0.0)

        assert throughput > 0, "throughput must be > 0"
        assert retry_rate == 0.0, "retry rate should be 0 in benchmark validation"
        assert out_md.exists(), "benchmark markdown must exist"

        print(
            json.dumps(
                {
                    "ok": True,
                    "tmp": str(tmp),
                    "out_json": str(out_json),
                    "out_md": str(out_md),
                    "throughput_jobs_per_min": throughput,
                    "retry_rate_percent": retry_rate,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
