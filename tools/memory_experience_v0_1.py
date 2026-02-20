#!/usr/bin/env python3
"""
MindKernel v0.1 Memory -> Experience path prototype.

Goal: run the first half of core pipeline with schema-validated objects + audit events.
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


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def in_days_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def conn(db_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def init_db(c: sqlite3.Connection):
    c.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS memory_items (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS experience_records (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            correlation_id TEXT,
            timestamp TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_items_status ON memory_items(status);
        CREATE INDEX IF NOT EXISTS idx_experience_records_status ON experience_records(status);
        CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(timestamp DESC);
        """
    )
    c.commit()


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
    if correlation_id:
        payload["correlation_id"] = correlation_id
    if metadata:
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
        (event_id, event_type, object_type, object_id, correlation_id, ts, json.dumps(payload, ensure_ascii=False)),
    )


def _extract_memory_payload(file_path: Path) -> dict:
    data = json.loads(file_path.read_text())
    if isinstance(data, dict) and "memory" in data and isinstance(data["memory"], dict):
        return data["memory"]
    if isinstance(data, dict):
        return data
    raise ValueError("memory input json must be an object or scenario object containing `memory`")


def ingest_memory(c: sqlite3.Connection, memory_payload: dict, actor_id: str = "mk-me-pipeline") -> dict:
    validate_payload("memory.schema.json", memory_payload)

    mem_id = memory_payload["id"]
    status = memory_payload["status"]
    exists = c.execute("SELECT 1 FROM memory_items WHERE id=?", (mem_id,)).fetchone()
    if exists:
        raise ValueError(f"memory already exists: {mem_id}")

    t = now_iso()
    c.execute(
        "INSERT INTO memory_items(id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (mem_id, status, json.dumps(memory_payload, ensure_ascii=False), t, t),
    )

    write_audit_event(
        c,
        event_type="state_transition",
        actor_type="system",
        actor_id=actor_id,
        object_type="memory",
        object_id=mem_id,
        before={"status": None},
        after={"status": status},
        reason="Memory ingested into v0.1 pipeline.",
        evidence_refs=memory_payload.get("evidence_refs", []),
    )

    c.commit()
    return {"memory_id": mem_id, "status": status}


def memory_to_experience(
    c: sqlite3.Connection,
    memory_id: str,
    episode_summary: str,
    outcome: str,
    actor_id: str = "mk-me-pipeline",
) -> dict:
    row = c.execute("SELECT payload_json FROM memory_items WHERE id=?", (memory_id,)).fetchone()
    if not row:
        raise ValueError(f"memory not found: {memory_id}")

    memory_payload = json.loads(row["payload_json"])
    if len(memory_payload.get("evidence_refs", [])) < 1:
        raise ValueError("memory must include at least one evidence_ref")

    exp_id = f"exp_{memory_id}_{uuid.uuid4().hex[:6]}"
    experience_payload = {
        "id": exp_id,
        "memory_refs": [memory_id],
        "episode_summary": episode_summary,
        "action_taken": "derive_from_memory",
        "outcome": outcome,
        "confidence": round(max(0.05, min(0.95, memory_payload.get("confidence", 0.5) * 0.9)), 2),
        "status": "candidate",
        "created_at": now_iso(),
        "review_due_at": in_days_iso(7),
        "next_action_at": in_days_iso(7),
    }

    validate_payload("experience.schema.json", experience_payload)

    c.execute(
        "INSERT INTO experience_records(id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (
            exp_id,
            experience_payload["status"],
            json.dumps(experience_payload, ensure_ascii=False),
            now_iso(),
            now_iso(),
        ),
    )

    old_status = memory_payload.get("status")
    if old_status != "active":
        memory_payload["status"] = "active"
        c.execute(
            "UPDATE memory_items SET status=?, payload_json=?, updated_at=? WHERE id=?",
            ("active", json.dumps(memory_payload, ensure_ascii=False), now_iso(), memory_id),
        )

        write_audit_event(
            c,
            event_type="state_transition",
            actor_type="system",
            actor_id=actor_id,
            object_type="memory",
            object_id=memory_id,
            before={"status": old_status},
            after={"status": "active"},
            reason="Memory consumed by experience pipeline and promoted to active evidence.",
            evidence_refs=memory_payload.get("evidence_refs", []),
        )

    write_audit_event(
        c,
        event_type="state_transition",
        actor_type="system",
        actor_id=actor_id,
        object_type="experience",
        object_id=exp_id,
        before={"status": None},
        after={"status": "candidate", "memory_refs": [memory_id]},
        reason="Experience created from memory via R-ME-01.",
        evidence_refs=memory_payload.get("evidence_refs", []),
        metadata={"rule_id": "R-ME-01"},
    )

    c.commit()
    return {
        "memory_id": memory_id,
        "memory_status": memory_payload.get("status"),
        "experience_id": exp_id,
        "experience_status": "candidate",
    }


def list_items(c: sqlite3.Connection, table: str, limit: int = 20):
    if table not in {"memory_items", "experience_records"}:
        raise ValueError("invalid table")
    rows = c.execute(
        f"SELECT id, status, updated_at FROM {table} ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_audits(c: sqlite3.Connection, limit: int = 20):
    rows = c.execute(
        "SELECT payload_json FROM audit_events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def main():
    p = argparse.ArgumentParser(description="MindKernel v0.1 Memory->Experience prototype")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    ing = sub.add_parser("ingest-memory")
    ing.add_argument("--file", required=True, help="Memory JSON file or scenario file containing `memory`")

    m2e = sub.add_parser("memory-to-experience")
    m2e.add_argument("--memory-id", required=True)
    m2e.add_argument("--episode-summary", required=True)
    m2e.add_argument("--outcome", required=True)

    rp = sub.add_parser("run-path")
    rp.add_argument("--file", required=True, help="Memory JSON file or scenario file containing `memory`")
    rp.add_argument("--episode-summary", required=True)
    rp.add_argument("--outcome", required=True)

    lm = sub.add_parser("list-memory")
    lm.add_argument("--limit", type=int, default=20)

    le = sub.add_parser("list-experience")
    le.add_argument("--limit", type=int, default=20)

    la = sub.add_parser("list-audits")
    la.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = conn(db)
    init_db(c)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "db": str(db)}))
        return

    if args.cmd == "ingest-memory":
        payload = _extract_memory_payload(Path(args.file))
        print(json.dumps(ingest_memory(c, payload), ensure_ascii=False))
        return

    if args.cmd == "memory-to-experience":
        print(
            json.dumps(
                memory_to_experience(c, args.memory_id, args.episode_summary, args.outcome),
                ensure_ascii=False,
            )
        )
        return

    if args.cmd == "run-path":
        payload = _extract_memory_payload(Path(args.file))
        ing = ingest_memory(c, payload)
        res = memory_to_experience(c, ing["memory_id"], args.episode_summary, args.outcome)
        print(json.dumps({"ingest": ing, "promote": res}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-memory":
        print(json.dumps(list_items(c, "memory_items", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-experience":
        print(json.dumps(list_items(c, "experience_records", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-audits":
        print(json.dumps(list_audits(c, args.limit), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
