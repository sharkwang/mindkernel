#!/usr/bin/env python3
"""Validate temporal worker verify/revalidate extensions (R3)."""

from __future__ import annotations

import json
import sqlite3
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
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_sec)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_item(db: Path, table: str, item_id: str, status: str, payload: dict):
    c = sqlite3.connect(str(db))
    t = now_iso()
    c.execute(
        f"""
        INSERT INTO {table}(id, status, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            updated_at=excluded.updated_at
        """,
        (item_id, status, json.dumps(payload, ensure_ascii=False), t, t),
    )
    c.commit()
    c.close()


def read_statuses(db: Path, table: str) -> dict[str, str]:
    c = sqlite3.connect(str(db))
    rows = c.execute(f"SELECT id, status FROM {table} ORDER BY id").fetchall()
    c.close()
    return {str(r[0]): str(r[1]) for r in rows}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mk-temporal-verify-v01-"))
    db = tmp / "mk.sqlite"

    run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "init-db"])
    run(["python3", str(ROOT / "tools" / "pipeline" / "memory_experience_v0_1.py"), "--db", str(db), "init-db"])

    t_now = now_iso()

    # memory fixtures
    upsert_item(
        db,
        "memory_items",
        "mem_verify",
        "candidate",
        {
            "id": "mem_verify",
            "kind": "fact",
            "content": "candidate memory should verify",
            "source": {"source_type": "file", "source_ref": "fixture://mem_verify"},
            "evidence_refs": ["fixture://mem_verify#1"],
            "confidence": 0.84,
            "risk_tier": "low",
            "impact_tier": "low",
            "status": "candidate",
            "investigation_status": "cleared",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )
    upsert_item(
        db,
        "memory_items",
        "mem_revalidate_up",
        "stale_uncertain",
        {
            "id": "mem_revalidate_up",
            "kind": "fact",
            "content": "stale uncertain with signal should activate",
            "source": {"source_type": "file", "source_ref": "fixture://mem_revalidate_up"},
            "evidence_refs": ["fixture://mem_revalidate_up#1"],
            "confidence": 0.7,
            "risk_tier": "low",
            "impact_tier": "low",
            "status": "stale_uncertain",
            "reinforcement_count": 2,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )
    upsert_item(
        db,
        "memory_items",
        "mem_revalidate_down",
        "stale",
        {
            "id": "mem_revalidate_down",
            "kind": "fact",
            "content": "stale without signal should stay uncertain",
            "source": {"source_type": "file", "source_ref": "fixture://mem_revalidate_down"},
            "evidence_refs": ["fixture://mem_revalidate_down#1"],
            "confidence": 0.4,
            "risk_tier": "medium",
            "impact_tier": "low",
            "status": "stale",
            "reinforcement_count": 0,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    # experience fixtures
    upsert_item(
        db,
        "experience_records",
        "exp_verify",
        "candidate",
        {
            "id": "exp_verify",
            "memory_refs": ["mem_verify"],
            "episode_summary": "candidate experience should verify to active",
            "outcome": "ok",
            "confidence": 0.8,
            "status": "candidate",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )
    upsert_item(
        db,
        "experience_records",
        "exp_revalidate_up",
        "needs_review",
        {
            "id": "exp_revalidate_up",
            "memory_refs": ["mem_revalidate_up"],
            "episode_summary": "reviewed experience should activate on signal",
            "outcome": "ok",
            "confidence": 0.72,
            "status": "needs_review",
            "reinstate_signal": True,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )
    upsert_item(
        db,
        "experience_records",
        "exp_revalidate_down",
        "invalidated",
        {
            "id": "exp_revalidate_down",
            "memory_refs": ["mem_revalidate_down"],
            "episode_summary": "invalidated experience without signal stays review",
            "outcome": "ok",
            "confidence": 0.3,
            "status": "invalidated",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    run_at = now_iso(offset_sec=2)
    jobs = [
        ("memory", "mem_verify", "verify", "high"),
        ("memory", "mem_revalidate_up", "revalidate", "high"),
        ("memory", "mem_revalidate_down", "revalidate", "high"),
        ("experience", "exp_verify", "verify", "medium"),
        ("experience", "exp_revalidate_up", "revalidate", "medium"),
        ("experience", "exp_revalidate_down", "revalidate", "medium"),
    ]

    for i, (otype, oid, action, priority) in enumerate(jobs):
        run(
            [
                "python3",
                str(TOOLS_SCHED / "scheduler_v0_1.py"),
                "--db",
                str(db),
                "enqueue",
                "--object-type",
                otype,
                "--object-id",
                oid,
                "--action",
                action,
                "--run-at",
                run_at,
                "--priority",
                priority,
                "--idempotency-key",
                f"temporal-verify:v01:{i}",
            ]
        )

    time.sleep(2.2)

    worker_out = run(
        [
            "python3",
            str(TOOLS_SCHED / "temporal_governance_worker_v0_1.py"),
            "--db",
            str(db),
            "--run-once",
            "--pull-limit",
            "20",
        ]
    )
    worker = json.loads(worker_out)

    assert worker.get("ok") is True, "worker should finish successfully"
    assert int(worker.get("processed", 0)) >= 6, "should process all verify/revalidate jobs"

    mem = read_statuses(db, "memory_items")
    exp = read_statuses(db, "experience_records")

    assert mem.get("mem_verify") == "verified", "mem_verify should be verified"
    assert mem.get("mem_revalidate_up") == "active", "mem_revalidate_up should be active"
    assert mem.get("mem_revalidate_down") == "stale_uncertain", "mem_revalidate_down should be stale_uncertain"

    assert exp.get("exp_verify") == "active", "exp_verify should be active"
    assert exp.get("exp_revalidate_up") == "active", "exp_revalidate_up should be active"
    assert exp.get("exp_revalidate_down") == "needs_review", "exp_revalidate_down should be needs_review"

    stats = json.loads(run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "stats"]))
    assert int(stats.get("succeeded", 0)) >= 6, "scheduler should ack all jobs"

    out = {
        "ok": True,
        "tmp": str(tmp),
        "worker": {
            "processed": worker.get("processed"),
            "succeeded": worker.get("succeeded"),
            "failed": worker.get("failed"),
        },
        "memory_status": {
            "mem_verify": mem.get("mem_verify"),
            "mem_revalidate_up": mem.get("mem_revalidate_up"),
            "mem_revalidate_down": mem.get("mem_revalidate_down"),
        },
        "experience_status": {
            "exp_verify": exp.get("exp_verify"),
            "exp_revalidate_up": exp.get("exp_revalidate_up"),
            "exp_revalidate_down": exp.get("exp_revalidate_down"),
        },
        "scheduler": {
            "queued": stats.get("queued"),
            "running": stats.get("running"),
            "succeeded": stats.get("succeeded"),
            "dead_letter": stats.get("dead_letter"),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
