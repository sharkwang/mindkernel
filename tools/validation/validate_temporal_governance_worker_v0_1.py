#!/usr/bin/env python3
"""Validate temporal governance worker (decay/archive/reinstate-check)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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


def upsert_item(db: Path, table: str, item_id: str, status: str, payload: dict):
    import sqlite3

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
    import sqlite3

    c = sqlite3.connect(str(db))
    rows = c.execute(f"SELECT id, status FROM {table} ORDER BY id").fetchall()
    c.close()
    return {str(r[0]): str(r[1]) for r in rows}


def main():
    tmp = Path(tempfile.mkdtemp(prefix="mk-temporal-worker-v01-"))
    db = tmp / "mk.sqlite"

    # init scheduler + object tables
    run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "init-db"])
    run(["python3", str(ROOT / "tools" / "pipeline" / "memory_experience_v0_1.py"), "--db", str(db), "init-db"])

    t_now = now_iso()

    # memory fixtures
    upsert_item(
        db,
        "memory_items",
        "mem_decay",
        "active",
        {
            "id": "mem_decay",
            "kind": "fact",
            "content": "active memory should decay",
            "source": {"source_type": "file", "source_ref": "fixture://mem_decay"},
            "evidence_refs": ["fixture://mem_decay#1"],
            "confidence": 0.8,
            "risk_tier": "low",
            "impact_tier": "low",
            "status": "active",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    upsert_item(
        db,
        "memory_items",
        "mem_archive",
        "stale",
        {
            "id": "mem_archive",
            "kind": "fact",
            "content": "stale memory should archive",
            "source": {"source_type": "file", "source_ref": "fixture://mem_archive"},
            "evidence_refs": ["fixture://mem_archive#1"],
            "confidence": 0.7,
            "risk_tier": "low",
            "impact_tier": "low",
            "status": "stale",
            "stale_since": t_now,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    upsert_item(
        db,
        "memory_items",
        "mem_reinstate",
        "stale_uncertain",
        {
            "id": "mem_reinstate",
            "kind": "fact",
            "content": "stale memory with new evidence should reinstate",
            "source": {"source_type": "file", "source_ref": "fixture://mem_reinstate"},
            "evidence_refs": ["fixture://mem_reinstate#1"],
            "confidence": 0.65,
            "risk_tier": "medium",
            "impact_tier": "low",
            "status": "stale_uncertain",
            "stale_since": t_now,
            "reinforcement_count": 2,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    # experience fixtures
    upsert_item(
        db,
        "experience_records",
        "exp_decay",
        "active",
        {
            "id": "exp_decay",
            "memory_refs": ["mem_decay"],
            "episode_summary": "active experience should decay to review",
            "outcome": "ok",
            "confidence": 0.7,
            "status": "active",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    upsert_item(
        db,
        "experience_records",
        "exp_archive",
        "needs_review",
        {
            "id": "exp_archive",
            "memory_refs": ["mem_archive"],
            "episode_summary": "reviewed experience should archive",
            "outcome": "ok",
            "confidence": 0.66,
            "status": "needs_review",
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    upsert_item(
        db,
        "experience_records",
        "exp_reinstate",
        "needs_review",
        {
            "id": "exp_reinstate",
            "memory_refs": ["mem_reinstate"],
            "episode_summary": "reviewed experience with signal should reinstate",
            "outcome": "ok",
            "confidence": 0.72,
            "status": "needs_review",
            "reinstate_signal": True,
            "created_at": t_now,
            "review_due_at": t_now,
            "next_action_at": t_now,
        },
    )

    run_at = now_iso(offset_sec=2)

    jobs = [
        ("memory", "mem_decay", "decay", "high"),
        ("memory", "mem_archive", "archive", "high"),
        ("memory", "mem_reinstate", "reinstate-check", "high"),
        ("experience", "exp_decay", "decay", "medium"),
        ("experience", "exp_archive", "archive", "medium"),
        ("experience", "exp_reinstate", "reinstate-check", "medium"),
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
                f"temporal:v01:{i}",
            ]
        )

    # wait until due
    import time

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

    assert worker.get("ok") is True, "temporal worker should finish successfully"
    assert int(worker.get("processed", 0)) >= 6, "should process all temporal jobs"

    mem = read_statuses(db, "memory_items")
    exp = read_statuses(db, "experience_records")

    assert mem.get("mem_decay") == "stale", "mem_decay should become stale"
    assert mem.get("mem_archive") == "archived", "mem_archive should become archived"
    assert mem.get("mem_reinstate") == "active", "mem_reinstate should become active"

    assert exp.get("exp_decay") == "needs_review", "exp_decay should become needs_review"
    assert exp.get("exp_archive") == "archived", "exp_archive should become archived"
    assert exp.get("exp_reinstate") == "active", "exp_reinstate should become active"

    stats_out = run(["python3", str(TOOLS_SCHED / "scheduler_v0_1.py"), "--db", str(db), "stats"])
    stats = json.loads(stats_out)
    assert int(stats.get("succeeded", 0)) >= 6, "scheduler should ack temporal jobs"

    out = {
        "ok": True,
        "tmp": str(tmp),
        "worker": {
            "processed": worker.get("processed"),
            "succeeded": worker.get("succeeded"),
            "failed": worker.get("failed"),
            "transitioned": worker.get("transitioned"),
            "noops": worker.get("noops"),
        },
        "memory_status": {
            "mem_decay": mem.get("mem_decay"),
            "mem_archive": mem.get("mem_archive"),
            "mem_reinstate": mem.get("mem_reinstate"),
        },
        "experience_status": {
            "exp_decay": exp.get("exp_decay"),
            "exp_archive": exp.get("exp_archive"),
            "exp_reinstate": exp.get("exp_reinstate"),
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
