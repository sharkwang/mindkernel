#!/usr/bin/env python3
"""
MECD Data Exporter — 导出 MECD 面板所需数据到 JSON 文件
由 launchd 定时调用，也可直接运行
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "mindkernel_v0_1.sqlite"
DEFAULT_OUTPUT = ROOT / "data" / "mecd_data.json"


def export_data(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    result = {"exported_at": datetime.now(timezone.utc).isoformat(), "stages": {}, "items": {}}

    # ── M: Memory ──────────────────────────────────────────────
    c.execute("SELECT id, status, payload_json, created_at FROM memory_items ORDER BY created_at DESC")
    memories = []
    for row in c.fetchall():
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        memories.append({
            "id": row["id"],
            "status": row["status"],
            "content": payload.get("content", ""),
            "kind": payload.get("kind", ""),
            "confidence": payload.get("confidence", 0),
            "risk_tier": payload.get("risk_tier", ""),
            "impact_tier": payload.get("impact_tier", ""),
            "source": payload.get("source", {}).get("source_type", ""),
            "created_at": row["created_at"],
        })
    result["stages"]["M"] = {
        "total": len(memories),
        "candidates": sum(1 for m in memories if m["status"] == "candidate"),
        "active": sum(1 for m in memories if m["status"] == "active"),
        "archived": sum(1 for m in memories if m["status"] == "archived"),
    }
    result["items"]["memories"] = memories[:20]  # latest 20

    # ── E: Experience ──────────────────────────────────────────
    c.execute("SELECT id, status, payload_json, created_at FROM experience_records ORDER BY created_at DESC")
    experiences = []
    for row in c.fetchall():
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        experiences.append({
            "id": row["id"],
            "status": row["status"],
            "episode_summary": payload.get("episode_summary", ""),
            "outcome": payload.get("outcome", ""),
            "confidence": payload.get("confidence", 0),
            "memory_refs": payload.get("memory_refs", []),
            "action_taken": payload.get("action_taken", ""),
            "created_at": row["created_at"],
        })
    result["stages"]["E"] = {
        "total": len(experiences),
        "active": sum(1 for e in experiences if e["status"] == "active"),
        "candidates": sum(1 for e in experiences if e["status"] == "candidate"),
    }
    result["items"]["experiences"] = experiences[:20]

    # ── C: Knowledge Relations ─────────────────────────────────
    c.execute("SELECT id, subject, predicate, object, confidence, source, created_at FROM knowledge_relations ORDER BY confidence DESC, created_at DESC")
    relations = []
    for row in c.fetchall():
        relations.append({
            "id": row["id"],
            "subject": row["subject"],
            "predicate": row["predicate"],
            "object": row["object"],
            "confidence": row["confidence"],
            "source": row["source"] or "derived",
            "created_at": row["created_at"],
        })
    result["stages"]["C"] = {"total": len(relations)}
    result["items"]["relations"] = relations[:30]

    # ── D: Decision Traces ─────────────────────────────────────
    c.execute("SELECT id, final_outcome, payload_json, created_at FROM decision_traces ORDER BY created_at DESC")
    decisions = []
    for row in c.fetchall():
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        decisions.append({
            "id": row["id"],
            "outcome": row["final_outcome"],
            "episode_summary": payload.get("episode_summary", ""),
            "policy_decision": payload.get("policy_decision", ""),
            "decision": payload.get("decision", ""),
            "reason_codes": payload.get("reason_codes", []),
            "confidence": payload.get("confidence", 0),
            "experience_id": payload.get("experience_id", ""),
            "created_at": row["created_at"],
        })
    result["stages"]["D"] = {
        "total": len(decisions),
        "auto_applied": sum(1 for d in decisions if d["outcome"] == "auto_applied"),
        "blocked": sum(1 for d in decisions if d["outcome"] == "blocked"),
    }
    result["items"]["decisions"] = decisions[:20]

    # ── Audit Summary ──────────────────────────────────────────
    c.execute("SELECT event_type, object_type, COUNT(*) as cnt FROM audit_events GROUP BY event_type, object_type ORDER BY cnt DESC")
    audit_summary = []
    total_audit = 0
    for row in c.fetchall():
        audit_summary.append({"event_type": row["event_type"], "object_type": row["object_type"], "count": row["cnt"]})
        total_audit += row["cnt"]
    result["stages"]["audit"] = {"total": total_audit, "breakdown": audit_summary}

    conn.close()
    return result


def main():
    import argparse
    p = argparse.ArgumentParser(description="MECD Data Exporter")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    p.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = p.parse_args()

    db_path = Path(args.db)
    output_path = Path(args.output)

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    data = export_data(db_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"Exported: {output_path} ({len(data['items']['memories'])} memories, {len(data['items']['experiences'])} experiences, {len(data['items']['decisions'])} decisions)")


if __name__ == "__main__":
    main()
