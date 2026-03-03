#!/usr/bin/env python3
"""Validate v0.2 daemon feature-flag rollout and rollback behavior (D5)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "tools" / "daemon" / "memory_observer_daemon_v0_2.py"


def _run(cmd: list[str], cwd: Path = ROOT) -> dict:
    p = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return json.loads(p.stdout)


def _write_events(path: Path):
    rows = [
        {
            "session_id": "sess_allow_1",
            "turn_id": "1",
            "role": "user",
            "timestamp": "2026-03-03T02:32:01Z",
            "content": "记住：每周一提醒我同步项目周报。",
        }
    ]
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _run_flag(mode: str, events: Path, daemon_db: Path, scheduler_db: Path, pid: Path, allow: Path | None = None) -> dict:
    cmd = [
        "python3",
        str(DAEMON),
        "--run-once",
        "--mode",
        "poll",
        "--events-file",
        str(events),
        "--state-db",
        str(daemon_db),
        "--scheduler-db",
        str(scheduler_db),
        "--pid-file",
        str(pid),
        "--feature-flag",
        mode,
    ]
    if allow is not None:
        cmd.extend(["--partial-session-allowlist", str(allow)])
    return _run(cmd)


def main():
    with tempfile.TemporaryDirectory(prefix="mk-daemon-flag-v02-") as td:
        tmp = Path(td)
        events = tmp / "events.jsonl"
        _write_events(events)

        allow = tmp / "allow.txt"
        allow.write_text("sess_allow_1\n", encoding="utf-8")

        # off => no enqueue (rollback mode)
        off = _run_flag("off", events, tmp / "off_daemon.sqlite", tmp / "off_sched.sqlite", tmp / "off.pid")
        assert off.get("ok") is True
        assert int(off.get("enqueued_this_run", 0)) == 0

        # shadow => no enqueue, still extracts candidates
        shadow = _run_flag("shadow", events, tmp / "shadow_daemon.sqlite", tmp / "shadow_sched.sqlite", tmp / "shadow.pid")
        assert shadow.get("ok") is True
        assert int(shadow.get("candidates_this_run", 0)) >= 1
        assert int(shadow.get("enqueued_this_run", 0)) == 0

        # partial without allowlist => no enqueue
        partial_skip = _run_flag(
            "partial",
            events,
            tmp / "partial_skip_daemon.sqlite",
            tmp / "partial_skip_sched.sqlite",
            tmp / "partial_skip.pid",
            allow=None,
        )
        assert partial_skip.get("ok") is True
        assert int(partial_skip.get("enqueued_this_run", 0)) == 0

        # partial with allowlist => enqueue
        partial_allow = _run_flag(
            "partial",
            events,
            tmp / "partial_allow_daemon.sqlite",
            tmp / "partial_allow_sched.sqlite",
            tmp / "partial_allow.pid",
            allow=allow,
        )
        assert partial_allow.get("ok") is True
        assert int(partial_allow.get("enqueued_this_run", 0)) >= 1

        # on => enqueue
        on = _run_flag("on", events, tmp / "on_daemon.sqlite", tmp / "on_sched.sqlite", tmp / "on.pid")
        assert on.get("ok") is True
        assert int(on.get("enqueued_this_run", 0)) >= 1

        out = {
            "ok": True,
            "tmp": str(tmp),
            "off": {
                "candidates": off.get("candidates_this_run"),
                "enqueued": off.get("enqueued_this_run"),
                "feature_flag": off.get("feature_flag"),
            },
            "shadow": {
                "candidates": shadow.get("candidates_this_run"),
                "enqueued": shadow.get("enqueued_this_run"),
                "feature_flag": shadow.get("feature_flag"),
            },
            "partial_skip": {
                "candidates": partial_skip.get("candidates_this_run"),
                "enqueued": partial_skip.get("enqueued_this_run"),
                "feature_flag": partial_skip.get("feature_flag"),
            },
            "partial_allow": {
                "candidates": partial_allow.get("candidates_this_run"),
                "enqueued": partial_allow.get("enqueued_this_run"),
                "feature_flag": partial_allow.get("feature_flag"),
            },
            "on": {
                "candidates": on.get("candidates_this_run"),
                "enqueued": on.get("enqueued_this_run"),
                "feature_flag": on.get("feature_flag"),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
