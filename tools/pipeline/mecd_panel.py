#!/usr/bin/env python3
"""
MindKernel MECD Panel Generator
生成可视化 HTML 面板，展示 M→E→C→D 每个步骤的实时状态
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "mindkernel_v0_1.sqlite"
OUTPUT_FILE = ROOT / "reports" / "mecd_panel.html"


@dataclass
class MECDMetrics:
    memory_total: int = 0
    memory_candidates: int = 0
    memory_active: int = 0
    memory_archived: int = 0
    experience_total: int = 0
    experience_active: int = 0
    experience_candidates: int = 0
    cognition_relations: int = 0
    decisions_total: int = 0
    decisions_auto: int = 0
    decisions_blocked: int = 0
    audit_events: int = 0


def load_metrics(db_path: Path) -> MECDMetrics:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    m = MECDMetrics()

    # Memory stats
    c.execute("SELECT COUNT(*), status FROM memory_items GROUP BY status")
    for count, status in c.fetchall():
        m.memory_total += count
        if status == "candidate":
            m.memory_candidates = count
        elif status == "active":
            m.memory_active = count
        elif status == "archived":
            m.memory_archived = count

    # Experience stats
    c.execute("SELECT COUNT(*), status FROM experience_records GROUP BY status")
    for count, status in c.fetchall():
        m.experience_total += count
        if status == "active":
            m.experience_active = count
        elif status == "candidate":
            m.experience_candidates = count

    # Cognition (knowledge relations)
    c.execute("SELECT COUNT(*) FROM knowledge_relations")
    m.cognition_relations = c.fetchone()[0]

    # Decision stats
    c.execute("SELECT COUNT(*) FROM decision_traces")
    m.decisions_total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM decision_traces WHERE final_outcome = 'auto_applied'")
    m.decisions_auto = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM decision_traces WHERE final_outcome = 'blocked'")
    m.decisions_blocked = c.fetchone()[0]

    # Audit events
    c.execute("SELECT COUNT(*) FROM audit_events")
    m.audit_events = c.fetchone()[0]

    conn.close()
    return m


def load_memory_items(db_path: Path, limit: int = 10):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT id, status, payload_json, created_at
        FROM memory_items
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = []
    for row in c.fetchall():
        payload = json.loads(row[2]) if row[2] else {}
        rows.append({
            "id": row[0],
            "status": row[1],
            "content": payload.get("content", "")[:120],
            "kind": payload.get("kind", ""),
            "confidence": payload.get("confidence", 0),
            "risk_tier": payload.get("risk_tier", ""),
            "impact_tier": payload.get("impact_tier", ""),
            "source": payload.get("source", {}).get("source_type", ""),
            "created_at": row[3],
        })
    conn.close()
    return rows


def load_experiences(db_path: Path, limit: int = 10):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT id, status, payload_json, created_at
        FROM experience_records
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = []
    for row in c.fetchall():
        payload = json.loads(row[2]) if row[2] else {}
        rows.append({
            "id": row[0],
            "status": row[1],
            "episode_summary": payload.get("episode_summary", ""),
            "outcome": payload.get("outcome", ""),
            "confidence": payload.get("confidence", 0),
            "memory_refs": payload.get("memory_refs", []),
            "action_taken": payload.get("action_taken", ""),
            "created_at": row[3],
        })
    conn.close()
    return rows


def load_decisions(db_path: Path, limit: int = 10):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT id, final_outcome, payload_json, created_at
        FROM decision_traces
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    rows = []
    for row in c.fetchall():
        payload = json.loads(row[2]) if row[2] else {}
        rows.append({
            "id": row[0],
            "outcome": row[1],
            "episode_summary": payload.get("episode_summary", ""),
            "policy_decision": payload.get("policy_decision", ""),
            "decision": payload.get("decision", ""),
            "reason_codes": payload.get("reason_codes", []),
            "confidence": payload.get("confidence", 0),
            "experience_id": payload.get("experience_id", ""),
            "created_at": row[3],
        })
    conn.close()
    return rows


def load_knowledge_relations(db_path: Path, limit: int = 20):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT id, subject, predicate, object, confidence, source, created_at
        FROM knowledge_relations
        ORDER BY confidence DESC, created_at DESC
        LIMIT ?
    """, (limit,))
    rows = []
    for row in c.fetchall():
        rows.append({
            "id": row[0],
            "subject": row[1],
            "predicate": row[2],
            "object": row[3],
            "confidence": row[4],
            "source": row[5] or "derived",
            "created_at": row[6],
        })
    conn.close()
    return rows


def load_audit_summary(db_path: Path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        SELECT event_type, object_type, COUNT(*) as cnt
        FROM audit_events
        GROUP BY event_type, object_type
        ORDER BY cnt DESC
    """)
    rows = []
    for row in c.fetchall():
        rows.append({"event_type": row[0], "object_type": row[1], "count": row[2]})
    conn.close()
    return rows


def status_color(status: str) -> str:
    colors = {
        "active": "#22c55e",
        "candidate": "#f59e0b",
        "archived": "#6b7280",
        "blocked": "#ef4444",
        "auto_applied": "#22c55e",
    }
    return colors.get(status, "#9ca3af")


def confidence_color(confidence: float) -> str:
    if confidence >= 0.7:
        return "#22c55e"
    elif confidence >= 0.4:
        return "#f59e0b"
    else:
        return "#6b7280"


def render_knowledge_relation(rel: dict) -> str:
    conf_pct = int(rel["confidence"] * 100)
    conf_color = confidence_color(rel["confidence"])
    return f'''
    <div class="relation-card">
      <div class="relation-main">
        <span class="entity">{rel["subject"]}</span>
        <span class="predicate">{rel["predicate"]}</span>
        <span class="entity">{rel["object"]}</span>
      </div>
      <div class="relation-meta">
        <span class="confidence" style="color:{conf_color}">{conf_pct}%</span>
        <span class="source">{rel["source"]}</span>
        <span class="date">{rel["created_at"][:10]}</span>
      </div>
    </div>'''


def render_decision_card(d: dict) -> str:
    outcome = d["outcome"] or "unknown"
    conf_pct = int((d.get("confidence") or 0) * 100)
    conf_color = confidence_color(d.get("confidence") or 0)
    outcome_color = status_color(outcome)
    reasons = ", ".join(d.get("reason_codes", [])[:3]) or "—"
    summary = d.get("episode_summary", "")[:100] or d.get("decision", "")[:100] or "—"
    return f'''
    <div class="decision-card">
      <div class="decision-header">
        <span class="decision-id">{d["id"][:16]}…</span>
        <span class="outcome-badge" style="background:{outcome_color}33;color:{outcome_color}">{outcome}</span>
        <span class="confidence" style="color:{conf_color}">�置信{conf_pct}%</span>
      </div>
      <div class="decision-summary">{summary}</div>
      <div class="decision-meta">
        <span>理由: {reasons}</span>
        <span>{d["created_at"][:16]}</span>
      </div>
    </div>'''


def generate_panel(
    db_path: Path,
    output_path: Path,
    title: str = "MindKernel MECD Panel",
):
    metrics = load_metrics(db_path)
    memories = load_memory_items(db_path)
    experiences = load_experiences(db_path)
    decisions = load_decisions(db_path)
    relations = load_knowledge_relations(db_path)
    audit_summary = load_audit_summary(db_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Pipeline flow stages
    mecd_stages = [
        ("M", "Memory", metrics.memory_total, metrics.memory_candidates, "#7dd3fc"),
        ("E", "Experience", metrics.experience_total, metrics.experience_candidates, "#a5b4fc"),
        ("C", "Cognition", metrics.cognition_relations, 0, "#c4b5fd"),
        ("D", "Decision", metrics.decisions_total, metrics.decisions_blocked, "#fbbf24"),
    ]

    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0e0; min-height: 100vh; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  
  /* Header */
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
  .header h1 {{ color: #7dd3fc; font-size: 1.8em; font-weight: 700; }}
  .header .timestamp {{ color: #6b7280; font-size: 0.85em; }}
  
  /* Pipeline Flow */
  .pipeline {{ display: flex; align-items: center; gap: 0; margin-bottom: 32px; background: #1a1a2e; border-radius: 16px; padding: 20px; overflow-x: auto; }}
  .pipeline-stage {{ flex: 1; min-width: 140px; text-align: center; padding: 16px 12px; border-radius: 12px; position: relative; }}
  .pipeline-arrow {{ font-size: 1.5em; color: #4b5563; padding: 0 8px; }}
  .stage-letter {{ font-size: 2em; font-weight: 900; opacity: 0.9; }}
  .stage-name {{ font-size: 0.9em; opacity: 0.8; margin: 4px 0; }}
  .stage-total {{ font-size: 1.4em; font-weight: 700; }}
  .stage-pending {{ font-size: 0.75em; opacity: 0.7; margin-top: 4px; }}
  
  /* Metrics Grid */
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 32px; }}
  .metric-card {{ background: #1a1a2e; border-radius: 12px; padding: 20px; text-align: center; }}
  .metric-value {{ font-size: 2.5em; font-weight: 700; }}
  .metric-label {{ color: #9ca3af; font-size: 0.85em; margin-top: 4px; }}
  
  /* Sections */
  .section {{ margin-bottom: 32px; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .section-header h2 {{ color: #e2e8f0; font-size: 1.2em; }}
  .section-badge {{ background: #334; color: #9ca3af; padding: 2px 10px; border-radius: 20px; font-size: 0.8em; }}
  
  /* Memory Cards */
  .memory-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
  .memory-card {{ background: #1a1a2e; border-radius: 10px; padding: 14px; border-left: 3px solid #334; }}
  .memory-card.active {{ border-left-color: #22c55e; }}
  .memory-card.candidate {{ border-left-color: #f59e0b; }}
  .memory-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }}
  .memory-id {{ font-family: monospace; font-size: 0.75em; color: #6b7280; }}
  .memory-status {{ font-size: 0.75em; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
  .memory-status.active {{ background: #22c55e22; color: #22c55e; }}
  .memory-status.candidate {{ background: #f59e0b22; color: #f59e0b; }}
  .memory-content {{ font-size: 0.88em; color: #d1d5db; line-height: 1.5; margin-bottom: 8px; word-break: break-all; }}
  .memory-meta {{ display: flex; gap: 12px; font-size: 0.75em; color: #6b7280; flex-wrap: wrap; }}
  .memory-meta span {{ background: #252538; padding: 1px 6px; border-radius: 4px; }}
  
  /* Experience Cards */
  .experience-list {{ display: flex; flex-direction: column; gap: 12px; }}
  .experience-card {{ background: #1a1a2e; border-radius: 10px; padding: 16px; border-left: 3px solid #a5b4fc; }}
  .experience-card.candidate {{ border-left-color: #f59e0b; }}
  .experience-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .experience-id {{ font-family: monospace; font-size: 0.75em; color: #6b7280; }}
  .experience-outcome {{ font-size: 0.8em; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
  .experience-outcome.positive {{ background: #22c55e22; color: #22c55e; }}
  .experience-outcome.neutral {{ background: #6b728022; color: #9ca3af; }}
  .experience-outcome.negative {{ background: #ef444422; color: #ef4444; }}
  .experience-summary {{ font-size: 0.9em; color: #d1d5db; line-height: 1.5; margin-bottom: 8px; }}
  .experience-meta {{ display: flex; gap: 12px; font-size: 0.75em; color: #6b7280; flex-wrap: wrap; }}
  
  /* Knowledge Relations */
  .relations-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
  .relation-card {{ background: #1a1a2e; border-radius: 8px; padding: 12px; }}
  .relation-main {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }}
  .entity {{ color: #c4b5fd; font-weight: 500; }}
  .predicate {{ color: #6b7280; font-size: 0.85em; }}
  .relation-meta {{ display: flex; gap: 10px; font-size: 0.75em; color: #6b7280; }}
  .confidence {{ font-weight: 600; }}
  
  /* Decision Cards */
  .decision-list {{ display: flex; flex-direction: column; gap: 10px; }}
  .decision-card {{ background: #1a1a2e; border-radius: 10px; padding: 14px; }}
  .decision-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }}
  .decision-id {{ font-family: monospace; font-size: 0.75em; color: #6b7280; }}
  .outcome-badge {{ font-size: 0.75em; padding: 2px 8px; border-radius: 10px; font-weight: 600; }}
  .decision-summary {{ font-size: 0.88em; color: #d1d5db; line-height: 1.4; margin-bottom: 8px; }}
  .decision-meta {{ display: flex; justify-content: space-between; font-size: 0.75em; color: #6b7280; flex-wrap: wrap; gap: 8px; }}
  
  /* Audit Summary */
  .audit-grid {{ display: flex; flex-wrap: wrap; gap: 12px; }}
  .audit-item {{ background: #1a1a2e; border-radius: 8px; padding: 10px 16px; display: flex; align-items: center; gap: 10px; }}
  .audit-count {{ font-size: 1.3em; font-weight: 700; color: #7dd3fc; }}
  .audit-label {{ font-size: 0.85em; color: #9ca3af; }}
  
  /* Footer */
  .footer {{ text-align: center; color: #4b5563; font-size: 0.8em; margin-top: 40px; padding-top: 20px; border-top: 1px solid #1f1f35; }}
  
  /* Empty state */
  .empty {{ color: #4b5563; font-size: 0.9em; padding: 20px; text-align: center; background: #1a1a2e; border-radius: 10px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🧠 MindKernel MECD Panel</h1>
    <div class="timestamp">Updated: {now}</div>
  </div>

  <!-- Pipeline Flow -->
  <div class="pipeline">
'''

    for i, (letter, name, total, pending, color) in enumerate(mecd_stages):
        if i > 0:
            html += '<div class="pipeline-arrow">→</div>'
        pending_str = f'<div class="stage-pending">⏳ {pending} pending</div>' if pending > 0 else ""
        html += f'''
    <div class="pipeline-stage">
      <div class="stage-letter" style="color:{color}">{letter}</div>
      <div class="stage-name">{name}</div>
      <div class="stage-total" style="color:{color}">{total}</div>
      {pending_str}
    </div>'''

    html += '''
  </div>

  <!-- Metrics Grid -->
  <div class="metrics-grid">
    <div class="metric-card">
      <div class="metric-value" style="color:#7dd3fc">{m.memory_total}</div>
      <div class="metric-label">Memory Items</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:#f59e0b">{m.memory_candidates}</div>
      <div class="metric-label">Candidates</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:#22c55e">{m.experience_total}</div>
      <div class="metric-label">Experience</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:#a5b4fc">{m.cognition_relations}</div>
      <div class="metric-label">Knowledge Relations</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:#fbbf24">{m.decisions_total}</div>
      <div class="metric-label">Decisions</div>
    </div>
    <div class="metric-card">
      <div class="metric-value" style="color:#ef4444">{m.decisions_blocked}</div>
      <div class="metric-label">Blocked</div>
    </div>
  </div>
'''.format(m=metrics)

    # Memory Section
    html += '''
  <!-- Memory Section (M) -->
  <div class="section">
    <div class="section-header">
      <h2>📝 Memory (M)</h2>
      <span class="section-badge">''' + str(len(memories)) + ''' recent</span>
    </div>
    <div class="memory-grid">
'''
    if memories:
        for mem in memories:
            status_class = mem["status"]
            status_html = f'<span class="memory-status {status_class}">{mem["status"]}</span>'
            conf_pct = int(mem.get("confidence", 0) * 100)
            html += f'''
      <div class="memory-card {status_class}">
        <div class="memory-header">
          <span class="memory-id">{mem["id"][:20]}…</span>
          {status_html}
        </div>
        <div class="memory-content">{'📋 ' if mem.get('kind') == 'fact' else '💬 '}{mem["content"]}</div>
        <div class="memory-meta">
          <span>置信 {conf_pct}%</span>
          <span>风险:{mem.get("risk_tier","—")}</span>
          <span>影响:{mem.get("impact_tier","—")}</span>
          <span>{mem["created_at"][:16]}</span>
        </div>
      </div>'''
    else:
        html += '<div class="empty">No memory items yet</div>'
    html += '</div></div>'

    # Experience Section
    html += '''
  <!-- Experience Section (E) -->
  <div class="section">
    <div class="section-header">
      <h2>✨ Experience (E)</h2>
      <span class="section-badge">''' + str(len(experiences)) + ''' recent</span>
    </div>
    <div class="experience-list">
'''
    if experiences:
        for exp in experiences:
            outcome_class = exp.get("outcome", "neutral")
            outcome_html = f'<span class="experience-outcome {outcome_class}">{exp.get("outcome","—")}</span>'
            mem_refs = ", ".join(exp.get("memory_refs", [])[:2])
            html += f'''
      <div class="experience-card {exp["status"]}">
        <div class="experience-header">
          <span class="experience-id">{exp["id"][:30]}…</span>
          {outcome_html}
        </div>
        <div class="experience-summary">📖 {exp.get("episode_summary", "—")}</div>
        <div class="experience-meta">
          <span>action: {exp.get("action_taken", "—")}</span>
          <span>refs: {mem_refs or "—"}</span>
          <span>{exp["created_at"][:16]}</span>
        </div>
      </div>'''
    else:
        html += '<div class="empty">No experience records yet</div>'
    html += '</div></div>'

    # Cognition Section (Knowledge Graph)
    html += '''
  <!-- Cognition Section (C) -->
  <div class="section">
    <div class="section-header">
      <h2>🧩 Cognition (C)</h2>
      <span class="section-badge">''' + str(len(relations)) + ''' relations</span>
    </div>
    <div class="relations-grid">
'''
    if relations:
        for rel in relations:
            html += render_knowledge_relation(rel)
    else:
        html += '<div class="empty">No knowledge relations yet</div>'
    html += '</div></div>'

    # Decision Section
    html += '''
  <!-- Decision Section (D) -->
  <div class="section">
    <div class="section-header">
      <h2>🎯 Decision (D)</h2>
      <span class="section-badge">''' + str(len(decisions)) + ''' recent</span>
    </div>
    <div class="decision-list">
'''
    if decisions:
        for d in decisions:
            html += render_decision_card(d)
    else:
        html += '<div class="empty">No decision traces yet</div>'
    html += '</div></div>'

    # Audit Summary
    html += '''
  <!-- Audit Summary -->
  <div class="section">
    <div class="section-header">
      <h2>📊 Audit Trail</h2>
      <span class="section-badge">''' + str(metrics.audit_events) + ''' total events</span>
    </div>
    <div class="audit-grid">
'''
    if audit_summary:
        for item in audit_summary:
            html += f'''
      <div class="audit-item">
        <span class="audit-count">{item["count"]}</span>
        <span class="audit-label">{item["event_type"]} / {item["object_type"]}</span>
      </div>'''
    else:
        html += '<div class="empty">No audit events</div>'
    html += '</div></div>'

    # Footer
    html += f'''
  <div class="footer">
    MindKernel MECD Panel · {now} · DB: {db_path.name}
  </div>
</div>
</body>
</html>'''

    output_path.write_text(html)
    print(f"MECD Panel generated: {output_path}")
    return output_path


def main():
    p = argparse.ArgumentParser(description="MindKernel MECD Panel Generator")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path")
    p.add_argument("--output", default=str(OUTPUT_FILE), help="Output HTML path")
    p.add_argument("--title", default="MindKernel MECD Panel", help="Panel title")
    args = p.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        return

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generate_panel(db_path, output_path, title=args.title)


if __name__ == "__main__":
    main()
