"""Opinion 可视化面板 — 生成 HTML 页面展示置信度变化."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OPINIONS_FILE = ROOT / "data" / "opinions_v0_1.json"
OUTPUT_HTML = ROOT / "reports" / "opinion_panel.html"


def load_opinions() -> list[dict]:
    if not OPINIONS_FILE.exists():
        return []
    return json.loads(OPINIONS_FILE.read_text())


def render_opinion_item(op: dict) -> str:
    confidence = op.get("confidence", 0)
    level = "high" if confidence >= 0.7 else "medium" if confidence >= 0.4 else "low"
    date = op.get("updated_at", op.get("created_at", "unknown"))
    topics = ", ".join(op.get("topics", []))
    return f"""
    <div class="opinion {level}">
      <div class="opinion-header">
        <span class="opinion-id">{op.get('id', '?')}</span>
        <span class="confidence-badge {level}">{confidence:.0%}</span>
      </div>
      <div class="opinion-content">{op.get('summary', op.get('statement', '(empty)'))}</div>
      <div class="opinion-meta">
        <span>更新: {date}</span>
        <span>话题: {topics or '无'}</span>
        <span>规则: {op.get('rule_name', 'N/A')}</span>
      </div>
    </div>
    """


def generate_html(opinions: list[dict]) -> str:
    high = [op for op in opinions if op.get("confidence", 0) >= 0.7]
    medium = [op for op in opinions if 0.4 <= op.get("confidence", 0) < 0.7]
    low = [op for op in opinions if op.get("confidence", 0) < 0.4]

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>MindKernel Opinion Panel</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 900px; margin: 40px auto; padding: 20px; background: #0f0f1a; color: #e0e0e0; }}
  h1 {{ color: #7dd3fc; border-bottom: 1px solid #334; padding-bottom: 10px; }}
  .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 30px; }}
  .summary-card {{ background: #1a1a2e; border-radius: 12px; padding: 20px; text-align: center; }}
  .summary-card.high {{ border: 1px solid #22c55e; }}
  .summary-card.medium {{ border: 1px solid #f59e0b; }}
  .summary-card.low {{ border: 1px solid #6b7280; }}
  .summary-number {{ font-size: 3em; font-weight: bold; }}
  .summary-label {{ color: #9ca3af; margin-top: 8px; }}
  .opinion {{ background: #1a1a2e; border-radius: 10px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #555; }}
  .opinion.high {{ border-left-color: #22c55e; }}
  .opinion.medium {{ border-left-color: #f59e0b; }}
  .opinion.low {{ border-left-color: #6b7280; }}
  .opinion-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
  .opinion-id {{ font-family: monospace; color: #9ca3af; font-size: 0.85em; }}
  .confidence-badge {{ padding: 4px 10px; border-radius: 20px; font-weight: bold; font-size: 0.85em; }}
  .confidence-badge.high {{ background: #22c55e33; color: #22c55e; }}
  .confidence-badge.medium {{ background: #f59e0b33; color: #f59e0b; }}
  .confidence-badge.low {{ background: #6b728033; color: #9ca3af; }}
  .opinion-content {{ color: #d1d5db; margin-bottom: 8px; line-height: 1.5; }}
  .opinion-meta {{ font-size: 0.8em; color: #6b7280; display: flex; gap: 16px; flex-wrap: wrap; }}
  .section {{ margin-bottom: 30px; }}
  .section h2 {{ color: #a5b4fc; margin-bottom: 12px; }}
  .timestamp {{ text-align: center; color: #4b5563; font-size: 0.8em; margin-top: 40px; }}
</style>
</head>
<body>
<h1>🧠 MindKernel Opinion Panel</h1>

<div class="summary">
  <div class="summary-card high">
    <div class="summary-number" style="color:#22c55e">{len(high)}</div>
    <div class="summary-label">高置信度 (≥70%)</div>
  </div>
  <div class="summary-card medium">
    <div class="summary-number" style="color:#f59e0b">{len(medium)}</div>
    <div class="summary-label">中置信度 (40-70%)</div>
  </div>
  <div class="summary-card low">
    <div class="summary-number" style="color:#9ca3af">{len(low)}</div>
    <div class="summary-label">低置信度 (&lt;40%)</div>
  </div>
</div>

<div class="section">
  <h2>🔴 高置信度观点</h2>
  {''.join(render_opinion_item(op) for op in high) or '<p style="color:#6b7280">暂无</p>'}
</div>

<div class="section">
  <h2>🟡 中置信度观点</h2>
  {''.join(render_opinion_item(op) for op in medium) or '<p style="color:#6b7280">暂无</p>'}
</div>

<div class="section">
  <h2>⚪ 低置信度观点</h2>
  {''.join(render_opinion_item(op) for op in low) or '<p style="color:#6b7280">暂无</p>'}
</div>

<div class="timestamp">生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
</body>
</html>"""
    return html


def generate_report():
    opinions = load_opinions()
    html = generate_html(opinions)
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_HTML.write_text(html)
    return str(OUTPUT_HTML), len(opinions)


if __name__ == "__main__":
    path, count = generate_report()
    print(f"Opinion panel generated: {path} ({count} opinions)")
