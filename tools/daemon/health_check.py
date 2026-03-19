#!/usr/bin/env python3
"""MindKernel daemon health check — run as heartbeat or cron."""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON_PID_FILE = ROOT / "data" / "daemon" / "memory_observer_v0_2.pid"
DAEMON_LOCK_FILE = ROOT / "data" / "daemon" / "memory_observer_v0_2.lock"
DAEMON_DB = ROOT / "data" / "daemon" / "memory_observer_v0_2.sqlite"
SCHEDULER_DB = ROOT / "data" / "scheduler.sqlite"
EVENTS_FILE = ROOT / "data" / "fixtures" / "daemon_events_openclaw.jsonl"


def check_pid_file(pid_file: Path) -> dict:
    result = {"ok": True, "pid": None, "running": False, "stale": False}
    if not pid_file.exists():
        result["ok"] = False
        result["reason"] = "pid_file_missing"
        return result
    try:
        pid = int(pid_file.read_text().strip())
        result["pid"] = pid
    except (ValueError, OSError):
        result["ok"] = False
        result["reason"] = "pid_file_corrupt"
        return result

    try:
        os.kill(pid, 0)
        result["running"] = True
    except ProcessLookupError:
        result["stale"] = True
        result["ok"] = False
        result["reason"] = "pid_file_stale"
    except PermissionError:
        result["running"] = True  # owned by another user — assume OK
    return result


def check_lock_file(pid_info: dict, lock_file: Path) -> dict:
    result = {"ok": True}
    if not lock_file.exists():
        result["ok"] = False
        result["reason"] = "lock_file_missing"
        return result
    # If daemon is running and holds the lock (expected), that's fine.
    # Only flag as bad if a DIFFERENT process holds the lock.
    if pid_info.get("running") and pid_info.get("pid"):
        # Daemon is alive — assume lock is daemon's own lock (OK)
        result["locked"] = False
        result["note"] = "daemon_running_assumed_lock_holder"
        return result
    try:
        lock_fd = os.open(str(lock_file), os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            result["locked"] = False
        except (IOError, OSError):
            result["locked"] = True
            result["ok"] = False
            result["reason"] = "lock_held_by_unknown_process"
        finally:
            os.close(lock_fd)
    except OSError as e:
        result["ok"] = False
        result["reason"] = f"lock_file_error: {e}"
    return result


def check_daemon_db(db_path: Path) -> dict:
    result = {"ok": True, "batches": 0, "candidates_total": 0, "candidates_enqueued": 0, "latest_batch": None}
    if not db_path.exists():
        result["ok"] = False
        result["reason"] = "db_missing"
        return result
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM daemon_batches")
        result["batches"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM daemon_candidates")
        result["candidates_total"] = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM daemon_candidates WHERE status='enqueued'")
        result["candidates_enqueued"] = c.fetchone()[0]
        c.execute("SELECT started_at, processed, candidates FROM daemon_batches ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row:
            result["latest_batch"] = {"started_at": row[0], "processed": row[1], "candidates": row[2]}
        conn.close()
    except sqlite3.Error as e:
        result["ok"] = False
        result["reason"] = f"sqlite_error: {e}"
    return result


def check_scheduler(sched_path: Path) -> dict:
    result = {"ok": True, "jobs": 0, "queued": 0, "succeeded": 0}
    if not sched_path.exists():
        result["ok"] = False
        result["reason"] = "scheduler_db_missing"
        return result
    try:
        conn = sqlite3.connect(str(sched_path))
        c = conn.cursor()
        c.execute("SELECT status, COUNT(*) FROM scheduler_jobs GROUP BY status")
        for status, count in c.fetchall():
            result["jobs"] += count
            if status == "queued":
                result["queued"] = count
            elif status == "succeeded":
                result["succeeded"] = count
        conn.close()
    except sqlite3.Error as e:
        result["ok"] = False
        result["reason"] = f"sqlite_error: {e}"
    return result


def check_events_file(events_file: Path) -> dict:
    result = {"ok": True, "lines": 0, "size_bytes": 0}
    if not events_file.exists():
        result["ok"] = False
        result["reason"] = "events_file_missing"
        return result
    try:
        lines = events_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        result["lines"] = len(lines)
        result["size_bytes"] = events_file.stat().st_size
    except OSError as e:
        result["ok"] = False
        result["reason"] = f"read_error: {e}"
    return result


def main():
    pid_info = check_pid_file(DAEMON_PID_FILE)
    lock_info = check_lock_file(pid_info, DAEMON_LOCK_FILE)
    db_info = check_daemon_db(DAEMON_DB)
    sched_info = check_scheduler(SCHEDULER_DB)
    events_info = check_events_file(EVENTS_FILE)

    overall_ok = (
        pid_info["running"] and
        not lock_info.get("locked", False) and
        db_info["ok"] and
        sched_info["ok"] and
        events_info["ok"]
    )

    out = {
        "ok": overall_ok,
        "pid_file": pid_info,
        "lock_file": lock_info,
        "daemon_db": db_info,
        "scheduler": sched_info,
        "events_file": events_info,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    raise SystemExit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
