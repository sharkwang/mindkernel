#!/usr/bin/env python3
"""
MindKernel v0.1 Experience -> Cognition path prototype with minimal Persona Gate.
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

        CREATE TABLE IF NOT EXISTS experience_records (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cognition_rules (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS persona_profiles (
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

        CREATE INDEX IF NOT EXISTS idx_experience_records_status ON experience_records(status);
        CREATE INDEX IF NOT EXISTS idx_cognition_rules_status ON cognition_rules(status);
        CREATE INDEX IF NOT EXISTS idx_persona_profiles_status ON persona_profiles(status);
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


def _extract_payload(file_path: Path, key: str) -> dict:
    data = json.loads(file_path.read_text())
    if isinstance(data, dict) and key in data and isinstance(data[key], dict):
        return data[key]
    if isinstance(data, dict):
        return data
    raise ValueError(f"{key} input must be a JSON object or scenario containing `{key}`")


def upsert_persona(c: sqlite3.Connection, persona_payload: dict, actor_id: str = "mk-ec-pipeline") -> dict:
    validate_payload("persona.schema.json", persona_payload)

    pid = persona_payload["id"]
    status = persona_payload["status"]
    now = now_iso()

    exists = c.execute("SELECT status FROM persona_profiles WHERE id=?", (pid,)).fetchone()
    if exists:
        before_status = exists["status"]
        c.execute(
            "UPDATE persona_profiles SET status=?, payload_json=?, updated_at=? WHERE id=?",
            (status, json.dumps(persona_payload, ensure_ascii=False), now, pid),
        )
    else:
        before_status = None
        c.execute(
            "INSERT INTO persona_profiles(id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (pid, status, json.dumps(persona_payload, ensure_ascii=False), now, now),
        )

    write_audit_event(
        c,
        event_type="state_transition",
        actor_type="system",
        actor_id=actor_id,
        object_type="persona",
        object_id=pid,
        before={"status": before_status},
        after={"status": status},
        reason="Persona profile upserted for Experience->Cognition gate.",
        evidence_refs=[f"persona:{pid}"],
    )

    c.commit()
    return {"persona_id": pid, "status": status, "upsert": True}


def ingest_experience(c: sqlite3.Connection, experience_payload: dict, actor_id: str = "mk-ec-pipeline") -> dict:
    validate_payload("experience.schema.json", experience_payload)

    eid = experience_payload["id"]
    status = experience_payload["status"]
    now = now_iso()

    exists = c.execute("SELECT 1 FROM experience_records WHERE id=?", (eid,)).fetchone()
    if exists:
        raise ValueError(f"experience already exists: {eid}")

    c.execute(
        "INSERT INTO experience_records(id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (eid, status, json.dumps(experience_payload, ensure_ascii=False), now, now),
    )

    write_audit_event(
        c,
        event_type="state_transition",
        actor_type="system",
        actor_id=actor_id,
        object_type="experience",
        object_id=eid,
        before={"status": None},
        after={"status": status},
        reason="Experience ingested into EC pipeline.",
        evidence_refs=experience_payload.get("memory_refs", []),
    )

    c.commit()
    return {"experience_id": eid, "status": status}


def persona_conflict_gate(persona_payload: dict, experience_payload: dict) -> tuple[str, list[str]]:
    boundaries = [str(b).strip() for b in persona_payload.get("boundaries", []) if str(b).strip()]
    text = " ".join(
        [
            str(experience_payload.get("episode_summary", "")),
            str(experience_payload.get("outcome", "")),
            str(experience_payload.get("action_taken", "")),
        ]
    ).lower()

    hits = [b for b in boundaries if b.lower() in text]
    if hits:
        return "block", hits
    return "pass", []


def _derive_cognition_payload(experience_payload: dict) -> dict:
    exp_id = experience_payload["id"]
    conf = float(experience_payload.get("confidence", 0.5))
    cog_conf = round(max(0.05, min(0.95, conf * 0.9)), 2)

    return {
        "id": f"cg_{exp_id}_{uuid.uuid4().hex[:6]}",
        "rule": f"Derived from experience: {experience_payload.get('episode_summary', 'n/a')}",
        "scope": {
            "domains": ["experience-derived"],
            "channels": ["webchat"],
            "risk_tier_max": "medium",
        },
        "epistemic_state": "uncertain",
        "unknown_type": "multipath",
        "confidence": cog_conf,
        "falsify_if": "New contradictory experience with stronger evidence appears.",
        "review_interval": "P7D",
        "decision_mode_if_uncertain": "conservative",
        "risk_tier": "medium",
        "impact_tier": "medium",
        "auto_verify_budget": 2,
        "status": "candidate",
        "evidence_refs": [exp_id],
        "created_at": now_iso(),
        "review_due_at": in_days_iso(7),
        "next_action_at": in_days_iso(7),
        "uncertainty_ttl": "P7D",
    }


def experience_to_cognition(
    c: sqlite3.Connection,
    experience_id: str,
    persona_id: str,
    actor_id: str = "mk-ec-pipeline",
) -> dict:
    exp_row = c.execute("SELECT payload_json FROM experience_records WHERE id=?", (experience_id,)).fetchone()
    if not exp_row:
        raise ValueError(f"experience not found: {experience_id}")

    persona_row = c.execute("SELECT payload_json FROM persona_profiles WHERE id=?", (persona_id,)).fetchone()
    if not persona_row:
        raise ValueError(f"persona not found: {persona_id}")

    experience_payload = json.loads(exp_row["payload_json"])
    persona_payload = json.loads(persona_row["payload_json"])

    if len(experience_payload.get("memory_refs", [])) < 1:
        raise ValueError("experience must include at least one memory_ref")

    gate, hits = persona_conflict_gate(persona_payload, experience_payload)

    if gate == "block":
        write_audit_event(
            c,
            event_type="decision_gate",
            actor_type="system",
            actor_id=actor_id,
            object_type="cognition",
            object_id=f"blocked_from_{experience_id}",
            before={"persona_conflict_gate": "pending"},
            after={"persona_conflict_gate": "block", "status": "blocked"},
            reason="Persona boundary conflict detected; cognition promotion blocked.",
            evidence_refs=[experience_id],
            metadata={"rule_id": "R-EC-02", "boundary_hits": hits, "persona_id": persona_id},
        )
        c.commit()
        return {
            "experience_id": experience_id,
            "persona_id": persona_id,
            "persona_conflict_gate": "block",
            "boundary_hits": hits,
            "cognition_created": False,
        }

    cognition_payload = _derive_cognition_payload(experience_payload)
    validate_payload("cognition.schema.json", cognition_payload)

    now = now_iso()
    c.execute(
        "INSERT INTO cognition_rules(id, status, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (
            cognition_payload["id"],
            cognition_payload["status"],
            json.dumps(cognition_payload, ensure_ascii=False),
            now,
            now,
        ),
    )

    write_audit_event(
        c,
        event_type="decision_gate",
        actor_type="system",
        actor_id=actor_id,
        object_type="cognition",
        object_id=cognition_payload["id"],
        before={"persona_conflict_gate": "pending"},
        after={"persona_conflict_gate": "pass"},
        reason="Persona gate passed for Experience->Cognition promotion.",
        evidence_refs=[experience_id],
        metadata={"rule_id": "R-EC-01", "persona_id": persona_id},
    )

    write_audit_event(
        c,
        event_type="state_transition",
        actor_type="system",
        actor_id=actor_id,
        object_type="cognition",
        object_id=cognition_payload["id"],
        before={"status": None},
        after={"status": "candidate", "epistemic_state": cognition_payload["epistemic_state"]},
        reason="Cognition candidate created from experience via R-EC-01.",
        evidence_refs=[experience_id],
        metadata={"rule_id": "R-EC-01"},
    )

    c.commit()
    return {
        "experience_id": experience_id,
        "persona_id": persona_id,
        "persona_conflict_gate": "pass",
        "cognition_created": True,
        "cognition_id": cognition_payload["id"],
        "cognition_status": cognition_payload["status"],
    }


def list_items(c: sqlite3.Connection, table: str, limit: int = 20):
    if table not in {"experience_records", "cognition_rules", "persona_profiles"}:
        raise ValueError("invalid table")
    rows = c.execute(
        f"SELECT id, status, updated_at FROM {table} ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_audits(c: sqlite3.Connection, limit: int = 20):
    rows = c.execute("SELECT payload_json FROM audit_events ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    return [json.loads(r["payload_json"]) for r in rows]


def main():
    p = argparse.ArgumentParser(description="MindKernel v0.1 Experience->Cognition prototype")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    ip = sub.add_parser("upsert-persona")
    ip.add_argument("--file", required=True, help="Persona JSON file or scenario containing `persona`")

    ie = sub.add_parser("ingest-experience")
    ie.add_argument("--file", required=True, help="Experience JSON file or scenario containing `experience`")

    e2c = sub.add_parser("experience-to-cognition")
    e2c.add_argument("--experience-id", required=True)
    e2c.add_argument("--persona-id", required=True)

    rp = sub.add_parser("run-path")
    rp.add_argument("--experience-file", required=True)
    rp.add_argument("--persona-file", required=True)

    lxp = sub.add_parser("list-experience")
    lxp.add_argument("--limit", type=int, default=20)

    lc = sub.add_parser("list-cognition")
    lc.add_argument("--limit", type=int, default=20)

    lp = sub.add_parser("list-persona")
    lp.add_argument("--limit", type=int, default=20)

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

    if args.cmd == "upsert-persona":
        payload = _extract_payload(Path(args.file), "persona")
        print(json.dumps(upsert_persona(c, payload), ensure_ascii=False))
        return

    if args.cmd == "ingest-experience":
        payload = _extract_payload(Path(args.file), "experience")
        print(json.dumps(ingest_experience(c, payload), ensure_ascii=False))
        return

    if args.cmd == "experience-to-cognition":
        print(json.dumps(experience_to_cognition(c, args.experience_id, args.persona_id), ensure_ascii=False, indent=2))
        return

    if args.cmd == "run-path":
        exp = _extract_payload(Path(args.experience_file), "experience")
        per = _extract_payload(Path(args.persona_file), "persona")
        r1 = upsert_persona(c, per)
        r2 = ingest_experience(c, exp)
        r3 = experience_to_cognition(c, r2["experience_id"], r1["persona_id"])
        print(json.dumps({"persona": r1, "experience": r2, "promote": r3}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-experience":
        print(json.dumps(list_items(c, "experience_records", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-cognition":
        print(json.dumps(list_items(c, "cognition_rules", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-persona":
        print(json.dumps(list_items(c, "persona_profiles", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-audits":
        print(json.dumps(list_audits(c, args.limit), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
