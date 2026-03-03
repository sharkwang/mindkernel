#!/usr/bin/env python3
"""Validate v0.2 daemon closed-loop prototype.

Closed loop (prototype):
conversation events -> daemon normalize/dedupe/extract -> scheduler enqueue reflect jobs
-> reflect worker consumes queued jobs in dry-run mode.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "tools" / "daemon" / "memory_observer_daemon_v0_2.py"
REFLECT_WORKER = ROOT / "tools" / "scheduler" / "reflect_scheduler_worker_v0_1.py"
FIXTURE_WS = ROOT / "data" / "fixtures" / "memory-workspace-evolution"


def _run(cmd: list[str], cwd: Path = ROOT) -> str:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
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

    with tempfile.TemporaryDirectory(prefix="mk-daemon-closed-v02-") as td:
        tmp = Path(td)
        events = tmp / "events.jsonl"
        daemon_db = tmp / "daemon.sqlite"
        scheduler_db = tmp / "scheduler.sqlite"
        pid_file = tmp / "daemon.pid"
        reports_dir = tmp / "reports"
        index_db = tmp / "index.sqlite"
        workspace = tmp / "workspace"

        shutil.copytree(FIXTURE_WS, workspace)

        rows = [
            {
                "session_id": "sess_omx_001",
                "turn_id": "1",
                "role": "user",
                "timestamp": "2026-03-03T02:20:01Z",
                "content": "记住：我希望每周一上午输出项目风险清单。",
            },
            {
                "session_id": "sess_omx_001",
                "turn_id": "2",
                "role": "assistant",
                "timestamp": "2026-03-03T02:20:02Z",
                "content": "收到。",
            },
            {
                "session_id": "sess_omx_001",
                "turn_id": "3",
                "role": "user",
                "timestamp": "2026-03-03T02:20:05Z",
                "content": "下周提醒我复盘 D1 到 D3 的推进结果。",
            },
            {
                # duplicate semantic event for dedupe check
                "session_id": "sess_omx_001",
                "turn_id": "3",
                "role": "user",
                "timestamp": "2026-03-03T02:20:06Z",
                "content": "下周提醒我复盘 D1 到 D3 的推进结果。",
            },
        ]
        with events.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        daemon_out = _run(
            [
                "python3",
                str(DAEMON),
                "--mode",
                "poll",
                "--events-file",
                str(events),
                "--state-db",
                str(daemon_db),
                "--pid-file",
                str(pid_file),
                "--scheduler-db",
                str(scheduler_db),
                "--enable-enqueue",
                "--enqueue-min-risk-level",
                "low",
                "--session-rate-limit-per-min",
                "20",
                "--max-candidates-per-event",
                "1",
                "--run-once",
                "--max-batch",
                "50",
            ]
        )
        daemon = json.loads(daemon_out)

        assert daemon.get("ok") is True
        assert int(daemon.get("processed_this_run", 0)) >= 3
        assert int(daemon.get("normalized_this_run", 0)) >= 3
        assert int(daemon.get("candidates_this_run", 0)) >= 1
        assert int(daemon.get("enqueued_this_run", 0)) >= 1
        assert int(daemon.get("deduped_events_this_run", 0)) >= 1

        # daemon enqueue uses run_at=now+1s; wait to ensure jobs become due
        time.sleep(1.2)

        worker_out = _run(
            [
                "python3",
                str(REFLECT_WORKER),
                "--db",
                str(scheduler_db),
                "--workspace",
                str(workspace),
                "--memory-index-db",
                str(index_db),
                "--reports-dir",
                str(reports_dir),
                "--run-once",
            ]
        )
        worker = json.loads(worker_out)

        assert worker.get("ok") is True
        assert int(worker.get("processed", 0)) >= 1
        assert int(worker.get("succeeded", 0)) >= 1

        summary_files = list(reports_dir.rglob("summary.json"))
        assert summary_files, "reflect worker should emit summary artifacts"

        out = {
            "ok": True,
            "tmp": str(tmp),
            "daemon": {
                "processed": daemon.get("processed_this_run"),
                "normalized": daemon.get("normalized_this_run"),
                "deduped_events": daemon.get("deduped_events_this_run"),
                "candidates": daemon.get("candidates_this_run"),
                "enqueued": daemon.get("enqueued_this_run"),
            },
            "worker": {
                "processed": worker.get("processed"),
                "succeeded": worker.get("succeeded"),
                "failed": worker.get("failed"),
            },
            "artifacts": [str(p) for p in summary_files[:3]],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
