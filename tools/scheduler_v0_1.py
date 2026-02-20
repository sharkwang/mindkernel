#!/usr/bin/env python3
"""
MindKernel v0.1 minimal scheduler prototype (SQLite).

Implements the interface in docs/02-design/scheduler-interface-v0.1.md:
- enqueue
- pull
- ack
- fail
- stats

Also records scheduler audit events aligned with schemas/audit-event.schema.json.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from schema_runtime import SchemaValidationError, validate_payload

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mindkernel_v0_1.sqlite"

ALLOWED_OBJECT_TYPES = {"memory", "experience", "cognition"}
ALLOWED_ACTIONS = {"verify", "revalidate", "decay", "archive", "reinstate-check"}
ALLOWED_PRIORITIES = {"low", "medium", "high"}
ALLOWED_STATUS = {"queued", "running", "succeeded", "failed", "dead_letter"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(v: str) -> datetime:
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


def priority_rank(p: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}[p]


def conn(db_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def init_db(c: sqlite3.Connection):
    c.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS scheduler_jobs (
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
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_status_runat
        ON scheduler_jobs(status, run_at, priority_rank);

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            correlation_id TEXT,
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audit_events_ts
        ON audit_events(timestamp DESC);
        """
    )
    c.commit()


def validate_enum(name: str, value: str, allowed: set[str]):
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got: {value}")


def write_audit_event(
    c: sqlite3.Connection,
    *,
    event_type: str,
    actor_type: str,
    actor_id: str,
    object_type: str,
    object_id: str,
    before: dict,
    after: dict,
    reason: str,
    evidence_refs: list[str],
    risk_tier: str | None = None,
    decision_trace_id: str | None = None,
    job_id: str | None = None,
    correlation_id: str | None = None,
    metadata: dict | None = None,
):
    ts = now_iso()
    event_id = f"aud_{uuid.uuid4().hex[:12]}"
    payload = {
        "id": event_id,
        "event_type": event_type,
        "actor": {"type": actor_type, "id": actor_id},
        "object_type": object_type,
        "object_id": object_id,
        "before": before,
        "after": after,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "timestamp": ts,
    }
    if risk_tier is not None:
        payload["risk_tier"] = risk_tier
    if decision_trace_id is not None:
        payload["decision_trace_id"] = decision_trace_id
    if job_id is not None:
        payload["job_id"] = job_id
    if correlation_id is not None:
        payload["correlation_id"] = correlation_id
    if metadata is not None:
        payload["metadata"] = metadata

    try:
        validate_payload("audit-event.schema.json", payload)
    except SchemaValidationError as e:
        raise ValueError(f"audit event schema validation failed: {e}") from e

    c.execute(
        """
        INSERT INTO audit_events(id, event_type, object_type, object_id, correlation_id, timestamp, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            object_type,
            object_id,
            correlation_id,
            ts,
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def enqueue(
    c: sqlite3.Connection,
    object_type: str,
    object_id: str,
    action: str,
    run_at: str,
    priority: str,
    max_attempts: int,
    idempotency_key: str | None,
    correlation_id: str | None,
):
    validate_enum("object_type", object_type, ALLOWED_OBJECT_TYPES)
    validate_enum("action", action, ALLOWED_ACTIONS)
    validate_enum("priority", priority, ALLOWED_PRIORITIES)
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    run_at_dt = parse_dt(run_at)
    if run_at_dt < parse_dt(now_iso()):
        raise ValueError("run_at must be >= current time")

    idem = idempotency_key or f"{object_id}:{action}:{run_at}"
    cur = c.execute("SELECT job_id, status FROM scheduler_jobs WHERE idempotency_key=?", (idem,)).fetchone()
    if cur:
        return {"deduplicated": True, "job_id": cur["job_id"], "status": cur["status"]}

    t = now_iso()
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    c.execute(
        """
        INSERT INTO scheduler_jobs(
            job_id, object_type, object_id, action, run_at, priority, priority_rank,
            attempt, max_attempts, idempotency_key, status, worker_id, last_error,
            correlation_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'queued', NULL, NULL, ?, ?, ?)
        """,
        (
            job_id,
            object_type,
            object_id,
            action,
            run_at,
            priority,
            priority_rank(priority),
            max_attempts,
            idem,
            correlation_id,
            t,
            t,
        ),
    )

    write_audit_event(
        c,
        event_type="scheduler_job",
        actor_type="system",
        actor_id="scheduler-cli",
        object_type="scheduler_job",
        object_id=job_id,
        before={"status": None},
        after={
            "status": "queued",
            "object_type": object_type,
            "object_id": object_id,
            "action": action,
            "run_at": run_at,
            "priority": priority,
            "attempt": 0,
            "max_attempts": max_attempts,
        },
        reason="Scheduler job enqueued.",
        evidence_refs=[f"scheduler_job:{job_id}"],
        job_id=job_id,
        correlation_id=correlation_id,
    )

    c.commit()
    return {"deduplicated": False, "job_id": job_id, "status": "queued", "idempotency_key": idem}


def pull_due(c: sqlite3.Connection, worker_id: str, now: str, limit: int):
    if limit < 1:
        raise ValueError("limit must be >= 1")

    jobs = c.execute(
        """
        SELECT * FROM scheduler_jobs
        WHERE status='queued' AND run_at <= ?
        ORDER BY run_at ASC, priority_rank DESC
        LIMIT ?
        """,
        (now, limit),
    ).fetchall()

    out = []
    for job in jobs:
        c.execute(
            "UPDATE scheduler_jobs SET status='running', worker_id=?, updated_at=? WHERE job_id=? AND status='queued'",
            (worker_id, now_iso(), job["job_id"]),
        )
        row = dict(job)
        row["status"] = "running"
        row["worker_id"] = worker_id
        out.append(row)

        write_audit_event(
            c,
            event_type="scheduler_job",
            actor_type="worker",
            actor_id=worker_id,
            object_type="scheduler_job",
            object_id=job["job_id"],
            before={"status": "queued", "attempt": job["attempt"]},
            after={"status": "running", "attempt": job["attempt"]},
            reason="Worker pulled due job.",
            evidence_refs=[f"scheduler_job:{job['job_id']}"],
            job_id=job["job_id"],
            correlation_id=job["correlation_id"],
        )

    c.commit()
    return out


def ack(c: sqlite3.Connection, job_id: str):
    cur = c.execute("SELECT * FROM scheduler_jobs WHERE job_id=?", (job_id,)).fetchone()
    if not cur:
        raise ValueError(f"job not found: {job_id}")
    if cur["status"] != "running":
        raise ValueError(f"job {job_id} must be running to ack, current={cur['status']}")

    c.execute(
        "UPDATE scheduler_jobs SET status='succeeded', updated_at=?, last_error=NULL WHERE job_id=?",
        (now_iso(), job_id),
    )

    write_audit_event(
        c,
        event_type="scheduler_job",
        actor_type="worker" if cur["worker_id"] else "system",
        actor_id=cur["worker_id"] or "scheduler-cli",
        object_type="scheduler_job",
        object_id=job_id,
        before={"status": "running", "attempt": cur["attempt"]},
        after={"status": "succeeded", "attempt": cur["attempt"]},
        reason="Job acknowledged as succeeded.",
        evidence_refs=[f"scheduler_job:{job_id}"],
        job_id=job_id,
        correlation_id=cur["correlation_id"],
    )

    c.commit()


def fail(c: sqlite3.Connection, job_id: str, error: str, retry_delay_sec: int):
    row = c.execute(
        "SELECT attempt, max_attempts, status, correlation_id, worker_id FROM scheduler_jobs WHERE job_id=?",
        (job_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"job not found: {job_id}")
    if row["status"] != "running":
        raise ValueError(f"job {job_id} must be running to fail, current={row['status']}")

    attempt = row["attempt"] + 1
    max_attempts = row["max_attempts"]

    if attempt >= max_attempts:
        status = "dead_letter"
        run_at = None
    else:
        status = "queued"
        run_at = (datetime.now(timezone.utc) + timedelta(seconds=retry_delay_sec)).replace(microsecond=0)
        run_at = run_at.isoformat().replace("+00:00", "Z")

    c.execute(
        """
        UPDATE scheduler_jobs
        SET status=?, attempt=?, run_at=COALESCE(?, run_at), last_error=?, updated_at=?, worker_id=NULL
        WHERE job_id=?
        """,
        (status, attempt, run_at, error, now_iso(), job_id),
    )

    after = {"status": status, "attempt": attempt}
    if run_at is not None:
        after["run_at"] = run_at

    write_audit_event(
        c,
        event_type="scheduler_job",
        actor_type="worker" if row["worker_id"] else "system",
        actor_id=row["worker_id"] or "scheduler-cli",
        object_type="scheduler_job",
        object_id=job_id,
        before={"status": "running", "attempt": row["attempt"]},
        after=after,
        reason=f"Job failed: {error}",
        evidence_refs=[f"scheduler_job:{job_id}"],
        job_id=job_id,
        correlation_id=row["correlation_id"],
        metadata={"retry_delay_sec": retry_delay_sec},
    )

    c.commit()
    return {"job_id": job_id, "status": status, "attempt": attempt, "max_attempts": max_attempts}


def stats(c: sqlite3.Connection):
    rows = c.execute(
        "SELECT status, COUNT(*) AS cnt FROM scheduler_jobs GROUP BY status ORDER BY status"
    ).fetchall()
    out = {r["status"]: r["cnt"] for r in rows}
    for s in ALLOWED_STATUS:
        out.setdefault(s, 0)

    oldest = c.execute(
        "SELECT run_at FROM scheduler_jobs WHERE status='queued' ORDER BY run_at ASC LIMIT 1"
    ).fetchone()
    out["oldest_queued_run_at"] = oldest["run_at"] if oldest else None

    out["audit_event_count"] = c.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
    return out


def list_audits(c: sqlite3.Connection, limit: int):
    if limit < 1:
        raise ValueError("limit must be >= 1")
    rows = c.execute(
        "SELECT payload_json FROM audit_events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def main():
    p = argparse.ArgumentParser(description="MindKernel v0.1 scheduler prototype")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    enq = sub.add_parser("enqueue")
    enq.add_argument("--object-type", required=True)
    enq.add_argument("--object-id", required=True)
    enq.add_argument("--action", required=True)
    enq.add_argument("--run-at", required=True, help="ISO date-time, e.g. 2026-02-20T12:00:00Z")
    enq.add_argument("--priority", default="medium", choices=sorted(ALLOWED_PRIORITIES))
    enq.add_argument("--max-attempts", type=int, default=3)
    enq.add_argument("--idempotency-key")
    enq.add_argument("--correlation-id")

    pull = sub.add_parser("pull")
    pull.add_argument("--worker-id", required=True)
    pull.add_argument("--now", default=now_iso())
    pull.add_argument("--limit", type=int, default=100)

    ack_p = sub.add_parser("ack")
    ack_p.add_argument("--job-id", required=True)

    fail_p = sub.add_parser("fail")
    fail_p.add_argument("--job-id", required=True)
    fail_p.add_argument("--error", required=True)
    fail_p.add_argument("--retry-delay-sec", type=int, default=300)

    sub.add_parser("stats")

    audits_p = sub.add_parser("list-audits")
    audits_p.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)

    c = conn(db)
    init_db(c)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "db": str(db)}))
        return

    if args.cmd == "enqueue":
        result = enqueue(
            c,
            args.object_type,
            args.object_id,
            args.action,
            args.run_at,
            args.priority,
            args.max_attempts,
            args.idempotency_key,
            args.correlation_id,
        )
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.cmd == "pull":
        jobs = pull_due(c, args.worker_id, args.now, args.limit)
        print(json.dumps(jobs, ensure_ascii=False, indent=2))
        return

    if args.cmd == "ack":
        ack(c, args.job_id)
        print(json.dumps({"ok": True, "job_id": args.job_id, "status": "succeeded"}))
        return

    if args.cmd == "fail":
        result = fail(c, args.job_id, args.error, args.retry_delay_sec)
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.cmd == "stats":
        print(json.dumps(stats(c), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-audits":
        print(json.dumps(list_audits(c, args.limit), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
