#!/usr/bin/env python3
"""Generate a runnable smoke-test report for MindKernel v0.1."""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
REPORTS = ROOT / "reports"
DATA = ROOT / "data"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_step(name: str, cmd: list[str]) -> dict:
    start = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    end = time.time()
    return {
        "name": name,
        "cmd": cmd,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "duration_sec": round(end - start, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"smoke-v0.1-{ts}"
    db_path = DATA / f"{run_id}.sqlite"

    steps = []

    # 1) full fixture validation
    steps.append(
        run_step(
            "validate-critical-paths",
            ["python3", str(TOOLS / "validate_scenarios_v0_1.py")],
        )
    )

    # 2) full-path pass
    steps.append(
        run_step(
            "full-path-pass",
            [
                "python3",
                str(TOOLS / "full_path_v0_1.py"),
                "--db",
                str(db_path),
                "run-full-path",
                "--memory-file",
                str(ROOT / "data/fixtures/critical-paths/12-full-path-pass.json"),
                "--persona-file",
                str(ROOT / "data/fixtures/critical-paths/12-full-path-pass.json"),
                "--episode-summary",
                "Planning support signal appears stable and useful.",
                "--outcome",
                "candidate generated",
                "--request-ref",
                f"req://report/{run_id}/pass",
            ],
        )
    )

    # 3) full-path block
    steps.append(
        run_step(
            "full-path-block",
            [
                "python3",
                str(TOOLS / "full_path_v0_1.py"),
                "--db",
                str(db_path),
                "run-full-path",
                "--memory-file",
                str(ROOT / "data/fixtures/critical-paths/13-full-path-block.json"),
                "--persona-file",
                str(ROOT / "data/fixtures/critical-paths/13-full-path-block.json"),
                "--episode-summary",
                "User asks for forbidden behavior in repeated attempts.",
                "--outcome",
                "forbidden path recognized",
                "--request-ref",
                f"req://report/{run_id}/block",
                "--risk-tier",
                "high",
            ],
        )
    )

    all_ok = all(s["ok"] for s in steps)

    validated_objects = None
    m = re.search(r"All good\. Validated objects/events: (\d+)", steps[0]["stdout"])
    if m:
        validated_objects = int(m.group(1))

    pass_outcome = None
    block_outcome = None
    for s, key in [(steps[1], "pass_outcome"), (steps[2], "block_outcome")]:
        if s["ok"]:
            try:
                payload = json.loads(s["stdout"])
                if key == "pass_outcome":
                    pass_outcome = payload.get("decision", {}).get("final_outcome")
                else:
                    block_outcome = payload.get("decision", {}).get("final_outcome")
            except Exception:
                pass

    report = {
        "run_id": run_id,
        "generated_at": now_utc_iso(),
        "ok": all_ok,
        "validated_objects_events": validated_objects,
        "full_path_pass_outcome": pass_outcome,
        "full_path_block_outcome": block_outcome,
        "db_path": str(db_path),
        "steps": steps,
    }

    json_path = REPORTS / f"{run_id}.json"
    md_path = REPORTS / f"{run_id}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    md = []
    md.append(f"# MindKernel Smoke Report ({run_id})")
    md.append("")
    md.append(f"- Generated at: `{report['generated_at']}`")
    md.append(f"- Overall: `{'PASS' if all_ok else 'FAIL'}`")
    md.append(f"- Validated objects/events: `{validated_objects}`")
    md.append(f"- Full-path pass outcome: `{pass_outcome}`")
    md.append(f"- Full-path block outcome: `{block_outcome}`")
    md.append("")
    md.append("## Steps")
    md.append("")
    md.append("| Step | Status | Duration(s) |")
    md.append("|---|---|---:|")
    for s in steps:
        md.append(f"| {s['name']} | {'PASS' if s['ok'] else 'FAIL'} | {s['duration_sec']} |")
    md.append("")
    md.append("## Notes")
    md.append("")
    md.append(f"- JSON detail: `{json_path}`")
    md.append(f"- SQLite used: `{db_path}`")
    md_path.write_text("\n".join(md) + "\n")

    print(json.dumps({
        "ok": all_ok,
        "run_id": run_id,
        "json_report": str(json_path),
        "md_report": str(md_path),
        "validated_objects_events": validated_objects,
        "full_path_pass_outcome": pass_outcome,
        "full_path_block_outcome": block_outcome,
    }, ensure_ascii=False, indent=2))

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
