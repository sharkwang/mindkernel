#!/usr/bin/env python3
"""Validate daemon observation report generation (v0.2)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "tools" / "daemon" / "memory_observer_daemon_v0_2.py"
REPORT = ROOT / "tools" / "validation" / "generate_daemon_observation_report_v0_2.py"


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return p.stdout


def main():
    with tempfile.TemporaryDirectory(prefix="mk-daemon-report-v02-") as td:
        tmp = Path(td)
        events = tmp / "events.jsonl"
        events.write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "session_id": "sess_report",
                            "turn_id": "1",
                            "role": "user",
                            "timestamp": "2026-03-03T03:00:01Z",
                            "content": "记住：这是一条观测报告测试消息。",
                        },
                        ensure_ascii=False,
                    )
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        daemon_db = tmp / "daemon.sqlite"
        sched_db = tmp / "sched.sqlite"
        pid = tmp / "daemon.pid"

        _run(
            [
                "python3",
                str(DAEMON),
                "--run-once",
                "--events-file",
                str(events),
                "--state-db",
                str(daemon_db),
                "--pid-file",
                str(pid),
                "--scheduler-db",
                str(sched_db),
                "--feature-flag",
                "on",
                "--enable-enqueue",
            ]
        )

        out_json = tmp / "observation.json"
        out_md = tmp / "observation.md"

        out = json.loads(
            _run(
                [
                    "python3",
                    str(REPORT),
                    "--daemon-db",
                    str(daemon_db),
                    "--window-hours",
                    "48",
                    "--out-json",
                    str(out_json),
                    "--out-md",
                    str(out_md),
                ]
            )
        )

        assert out.get("ok") is True
        assert Path(out["out_json"]).exists()
        assert Path(out["out_md"]).exists()
        m = out.get("metrics", {})
        assert int(m.get("batches", 0)) >= 1
        assert int(m.get("processed", 0)) >= 1

        print(
            json.dumps(
                {
                    "ok": True,
                    "tmp": str(tmp),
                    "batches": m.get("batches"),
                    "processed": m.get("processed"),
                    "alerts": out.get("alerts"),
                    "out_json": out.get("out_json"),
                    "out_md": out.get("out_md"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
