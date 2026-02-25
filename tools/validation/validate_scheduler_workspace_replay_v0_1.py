#!/usr/bin/env python3
"""Replay reflect worker on real workspace (non-fixture) with recovery check."""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_SCHED = ROOT / "tools" / "scheduler"


def run(cmd: list[str], cwd: Path = ROOT):
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return p.stdout


def now_iso(offset_sec: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_sec)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mk-workspace-replay-v01-"))
    db = tmp / "scheduler.sqlite"
    idx = tmp / "index.sqlite"
    reports = tmp / "reports"

    workspace = ROOT

    run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "init-db"])

    run_at = now_iso(offset_sec=2)
    for i in range(2):
        run(
            [
                "python3",
                str(TOOLS_SCHED / "scheduler_v0_1.py"),
                "--db",
                str(db),
                "enqueue",
                "--object-type",
                "reflect_job",
                "--object-id",
                f"workspace_replay_{i+1}",
                "--action",
                "reflect",
                "--run-at",
                run_at,
                "--priority",
                "high",
                "--idempotency-key",
                f"workspace-replay:v01:{i+1}",
            ]
        )

    time.sleep(2.2)

    # run-1: intentionally fail once (bad gate config), to verify retry path in real workspace replay
    t1 = time.time()
    out_fail = run(
        [
            "python3",
            str(TOOLS_SCHED / "reflect_scheduler_worker_v0_1.py"),
            "--db",
            str(db),
            "--workspace",
            str(workspace),
            "--memory-index-db",
            str(idx),
            "--reports-dir",
            str(reports),
            "--gate-config",
            str(tmp / "missing-gate-config.json"),
            "--retry-delay-sec",
            "1",
            "--run-once",
            "--pull-limit",
            "10",
        ]
    )
    fail_run = json.loads(out_fail)
    fail_elapsed = round(time.time() - t1, 3)

    assert int(fail_run.get("failed", 0)) >= 1, "first replay run should fail for recovery test"

    time.sleep(1.2)

    # run-2: normal replay on real workspace
    t2 = time.time()
    out_ok = run(
        [
            "python3",
            str(TOOLS_SCHED / "reflect_scheduler_worker_v0_1.py"),
            "--db",
            str(db),
            "--workspace",
            str(workspace),
            "--memory-index-db",
            str(idx),
            "--reports-dir",
            str(reports),
            "--run-once",
            "--pull-limit",
            "10",
        ]
    )
    ok_run = json.loads(out_ok)
    ok_elapsed = round(time.time() - t2, 3)

    assert ok_run.get("ok") is True, "second replay run should recover and succeed"
    assert int(ok_run.get("processed", 0)) >= 1, "second run should process retried jobs"

    stats = json.loads(run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "stats"]))
    assert int(stats.get("succeeded", 0)) >= 2, "replayed jobs should eventually succeed"

    summary_files = sorted(reports.rglob("summary.json"))
    assert summary_files, "workspace replay should produce summary artifacts"

    sample = json.loads(summary_files[-1].read_text(encoding="utf-8"))

    out = {
        "ok": True,
        "tmp": str(tmp),
        "workspace": str(workspace),
        "run_fail_then_recover": {
            "first_run": {
                "processed": fail_run.get("processed"),
                "succeeded": fail_run.get("succeeded"),
                "failed": fail_run.get("failed"),
                "elapsed_sec": fail_elapsed,
            },
            "second_run": {
                "processed": ok_run.get("processed"),
                "succeeded": ok_run.get("succeeded"),
                "failed": ok_run.get("failed"),
                "elapsed_sec": ok_elapsed,
            },
        },
        "scheduler": {
            "queued": stats.get("queued"),
            "running": stats.get("running"),
            "succeeded": stats.get("succeeded"),
            "dead_letter": stats.get("dead_letter"),
        },
        "artifacts": {
            "summary_count": len(summary_files),
            "sample_summary": {
                "path": str(summary_files[-1]),
                "proposals": sample.get("proposals"),
                "apply_count": sample.get("apply_plan", {}).get("apply_count"),
                "blocked_count": sample.get("apply_plan", {}).get("blocked_count"),
            },
        },
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
