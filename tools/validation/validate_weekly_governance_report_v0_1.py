#!/usr/bin/env python3
"""Validate weekly governance report generator (R1)."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "tools" / "validation" / "generate_weekly_governance_report_v0_1.py"


def now_iso(offset_days: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=offset_days)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def setup_db(db: Path):
    c = sqlite3.connect(str(db))
    c.executescript(
        """
        CREATE TABLE scheduler_jobs (
            job_id TEXT PRIMARY KEY,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            action TEXT NOT NULL,
            run_at TEXT NOT NULL,
            priority TEXT NOT NULL,
            priority_rank INTEGER NOT NULL,
            attempt INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            idempotency_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            worker_id TEXT,
            last_error TEXT,
            correlation_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            lease_token TEXT,
            lease_expires_at TEXT
        );

        CREATE TABLE audit_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            correlation_id TEXT,
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )

    created = now_iso(-1)
    run_at = now_iso(-1)

    rows = [
        ("job_a", "cognition", "cg_1", "revalidate", run_at, "medium", 2, 0, 3, "idem_a", "succeeded", None, None, "corr_1", created, created, None, None),
        ("job_b", "reflect_job", "rj_1", "reflect", run_at, "high", 3, 1, 3, "idem_b", "succeeded", None, None, "corr_2", created, created, None, None),
        ("job_c", "memory", "mem_1", "archive", run_at, "low", 1, 2, 3, "idem_c", "dead_letter", None, "timeout", "corr_3", created, created, None, None),
        ("job_d", "experience", "exp_1", "decay", now_iso(1), "low", 1, 0, 3, "idem_d", "queued", None, None, "corr_4", created, created, None, None),
    ]
    c.executemany(
        """
        INSERT INTO scheduler_jobs(
          job_id, object_type, object_id, action, run_at, priority, priority_rank,
          attempt, max_attempts, idempotency_key, status, worker_id, last_error,
          correlation_id, created_at, updated_at, lease_token, lease_expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    payloads = [
        {
            "id": "aud_1",
            "event_type": "state_transition",
            "actor": {"type": "worker", "id": "w1"},
            "object_type": "memory",
            "object_id": "mem_1",
            "before": {"status": "stale"},
            "after": {"status": "active"},
            "reason": "reinstate",
            "evidence_refs": ["memory:mem_1"],
            "timestamp": now_iso(-1),
        },
        {
            "id": "aud_2",
            "event_type": "decision_gate",
            "actor": {"type": "system", "id": "gate"},
            "object_type": "decision",
            "object_id": "dec_1",
            "before": {"final_outcome": None},
            "after": {"final_outcome": "blocked", "persona_conflict_gate": "block"},
            "reason": "policy",
            "evidence_refs": ["decision:dec_1"],
            "timestamp": now_iso(-1),
        },
    ]

    for i, p in enumerate(payloads, start=1):
        c.execute(
            "INSERT INTO audit_events(id, event_type, object_type, object_id, correlation_id, timestamp, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"ae_{i}", p["event_type"], p["object_type"], p["object_id"], None, p["timestamp"], json.dumps(p, ensure_ascii=False)),
        )

    c.commit()
    c.close()


def main():
    with tempfile.TemporaryDirectory(prefix="mk-weekly-report-v01-") as td:
        tmp = Path(td)
        db = tmp / "mk.sqlite"
        out_json = tmp / "weekly.json"
        out_md = tmp / "weekly.md"
        release_json = tmp / "release_check.json"

        setup_db(db)

        release_json.write_text(
            json.dumps(
                {
                    "ok": True,
                    "release_target": "v0.1.1-review-full",
                    "generated_at": now_iso(-1),
                    "passed": 14,
                    "total": 14,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        cmd = [
            "python3",
            str(GEN),
            "--db",
            str(db),
            "--release-check-json",
            str(release_json),
            "--out-json",
            str(out_json),
            "--out-md",
            str(out_md),
            "--since-days",
            "7",
        ]
        p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
        if p.returncode != 0:
            raise SystemExit(f"generator failed\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")

        report = json.loads(out_json.read_text(encoding="utf-8"))

        assert report.get("scheduler", {}).get("window_jobs") == 4, "window job count mismatch"
        assert report.get("scheduler", {}).get("status_counts", {}).get("succeeded") == 2, "succeeded count mismatch"
        assert report.get("scheduler", {}).get("dead_letter_rate") > 0, "dead-letter rate should be > 0"
        assert report.get("audit", {}).get("blocked_count") >= 1, "blocked count should be >= 1"
        assert report.get("release_gate", {}).get("ok") is True, "release gate should be true"
        assert out_md.exists(), "markdown report should exist"

        print(
            json.dumps(
                {
                    "ok": True,
                    "tmp": str(tmp),
                    "out_json": str(out_json),
                    "out_md": str(out_md),
                    "scheduler_window_jobs": report.get("scheduler", {}).get("window_jobs"),
                    "success_rate": report.get("scheduler", {}).get("success_rate"),
                    "dead_letter_rate": report.get("scheduler", {}).get("dead_letter_rate"),
                    "learning_yield_proxy": report.get("audit", {}).get("learning_yield_proxy"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
