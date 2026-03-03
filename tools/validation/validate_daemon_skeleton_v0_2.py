#!/usr/bin/env python3
"""Validate v0.2 daemon skeleton (D1).

Covers minimal smoke path:
1) start (run-once) and checkpoint creation
2) restart recover from checkpoint (processes only delta events)
3) graceful shutdown on SIGTERM in continuous mode
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "tools" / "daemon" / "memory_observer_daemon_v0_2.py"


def _read_state(db_path: Path) -> dict:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    row = c.execute(
        "SELECT mode, events_file, offset, processed_total, last_event_id, started_at, updated_at FROM daemon_state WHERE id=1"
    ).fetchone()
    c.close()
    if not row:
        raise RuntimeError("daemon_state row missing")
    return {
        "mode": row["mode"],
        "events_file": row["events_file"],
        "offset": int(row["offset"]),
        "processed_total": int(row["processed_total"]),
        "last_event_id": row["last_event_id"],
        "started_at": row["started_at"],
        "updated_at": row["updated_at"],
    }


def _append_events(path: Path, start_idx: int, count: int):
    with path.open("a", encoding="utf-8") as f:
        for i in range(start_idx, start_idx + count):
            obj = {
                "event_id": f"evt_{i:03d}",
                "session_id": "sess_demo",
                "turn_id": i,
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"event-{i}",
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _run_once(events: Path, db: Path, pid: Path) -> dict:
    p = subprocess.run(
        [
            "python3",
            str(DAEMON),
            "--mode",
            "poll",
            "--events-file",
            str(events),
            "--state-db",
            str(db),
            "--pid-file",
            str(pid),
            "--run-once",
            "--max-batch",
            "100",
            "--poll-interval-sec",
            "0.05",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"run-once failed rc={p.returncode}\nstdout={p.stdout}\nstderr={p.stderr}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"invalid daemon json output: {e}\nstdout={p.stdout}") from e


def main():
    with tempfile.TemporaryDirectory(prefix="mk-daemon-v02-") as td:
        tmp = Path(td)
        events = tmp / "events.jsonl"
        db = tmp / "daemon.sqlite"
        pid = tmp / "daemon.pid"

        # Step 1: start + checkpoint
        _append_events(events, start_idx=1, count=3)
        first = _run_once(events, db, pid)
        assert first.get("ok") is True
        assert int(first.get("processed_this_run", 0)) == 3

        s1 = _read_state(db)
        assert s1["processed_total"] == 3
        assert s1["offset"] > 0

        # Step 2: restart recover (process only delta)
        _append_events(events, start_idx=4, count=2)
        second = _run_once(events, db, pid)
        assert second.get("ok") is True
        assert int(second.get("processed_this_run", 0)) == 2

        s2 = _read_state(db)
        assert s2["processed_total"] == 5
        assert s2["offset"] > s1["offset"]

        # Step 3: graceful shutdown in continuous mode
        _append_events(events, start_idx=6, count=20)
        proc = subprocess.Popen(
            [
                "python3",
                str(DAEMON),
                "--mode",
                "poll",
                "--events-file",
                str(events),
                "--state-db",
                str(db),
                "--pid-file",
                str(pid),
                "--max-batch",
                "1",
                "--poll-interval-sec",
                "0.05",
            ],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(0.8)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=10)
        if proc.returncode != 0:
            raise RuntimeError(f"continuous run failed rc={proc.returncode}\nstdout={out}\nstderr={err}")

        third = json.loads(out)
        assert third.get("ok") is True
        assert bool(third.get("stopped_by_signal")) is True
        assert not pid.exists(), "pid file should be cleaned up on graceful shutdown"

        s3 = _read_state(db)
        assert s3["processed_total"] >= 5
        assert s3["offset"] >= s2["offset"]
        assert s3["offset"] <= events.stat().st_size

        result = {
            "ok": True,
            "tmp": str(tmp),
            "first_run": {
                "processed": first.get("processed_this_run"),
                "processed_total": first.get("processed_total"),
                "offset": first.get("offset"),
            },
            "second_run": {
                "processed": second.get("processed_this_run"),
                "processed_total": second.get("processed_total"),
                "offset": second.get("offset"),
            },
            "third_run": {
                "processed": third.get("processed_this_run"),
                "processed_total": third.get("processed_total"),
                "offset": third.get("offset"),
                "stopped_by_signal": third.get("stopped_by_signal"),
            },
            "state": s3,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
