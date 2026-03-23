"""
MindKernel 参数配置层 — 所有可调参数的单一来源

使用方式：
  from core.param_config import get, update_feedback
  risk_thresh = get("candidate.risk_threshold.medium")

参数分类：
  - candidate.*    : 候选提取阈值
  - experience.*   : Experience 晋升参数
  - opinion.*      : Opinion 置信度参数
  - decision.*     : Decision 反馈权重
  - governance.*   : 治理报告调度参数
  - daemon.*       : Daemon 运行时参数

反馈回路：
  - update_feedback(decision_trace) → 更新 decision.* 权重
  - compute_source_weights() → 基于历史 decision 生成来源权重
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "data" / "governance" / "param_config.json"
FEEDBACK_HISTORY = ROOT / "data" / "governance" / "feedback_history.jsonl"

# ---------------------------------------------------------------------------
# 默认参数（系统级，不随反馈更新）
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict[str, Any] = {
    # === 候选提取阈值 ===
    "candidate.risk_threshold.high": 70,
    "candidate.risk_threshold.medium": 40,
    "candidate.min_content_length": 4,
    "candidate.max_per_event": 1,
    "candidate.min_value_score": 0,

    # === Experience 晋升 ===
    "experience.auto_promote": True,
    "experience.min_confidence": 0.45,
    "experience.confidence_scale": 0.9,
    "experience.positive_boost": 0.15,
    "experience.negative_penalty": 0.10,
    "experience.review_due_days": 7,

    # === Opinion 参数 ===
    "opinion.initial_confidence": 0.55,
    "opinion.confidence_increment": 0.05,
    "opinion.max_confidence": 0.98,
    "opinion.min_evidence": 1,

    # === Decision 反馈权重 ===
    "decision.positive_weight": 1.0,
    "decision.negative_weight": 0.6,
    "decision.neutral_weight": 0.8,
    "decision.confidence_decay": 0.95,
    "decision.recent_window_days": 7,

    # === 候选来源权重（由反馈回路更新）===
    "source.openclaw_memory_md": 0.70,
    "source.openclaw_daily": 0.65,
    "source.daemon_candidate": 0.60,
    "source.manual": 0.75,

    # === 治理报告调度 ===
    "governance.report_interval_hours": 24,
    "governance.alert_threshold_errors": 5,
    "governance.alert_threshold_dedup_rate": 0.5,
    "governance.persist_feedback": True,

    # === Daemon 入队 ===
    "daemon.enqueue_min_risk": "low",
    "daemon.max_batch": 200,
    "daemon.poll_interval_sec": 1,
    "daemon.system_repeat_threshold": 3,
}


# ---------------------------------------------------------------------------
# 加载 / 保存
# ---------------------------------------------------------------------------

def _load() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return dict(DEFAULT_PARAMS)


def _save(cfg: dict[str, Any]):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# 读取参数
# ---------------------------------------------------------------------------

def get(key: str, default: Any = None) -> Any:
    """读取一个参数，支持嵌套 key 如 'candidate.risk_threshold.medium'。"""
    cfg = _load()
    return cfg.get(key, DEFAULT_PARAMS.get(key, default))


def get_all() -> dict[str, Any]:
    """返回完整参数快照（含默认值）。"""
    merged = dict(DEFAULT_PARAMS)
    merged.update(_load())
    return merged


# ---------------------------------------------------------------------------
# 更新参数（人工或自动）
# ---------------------------------------------------------------------------

def set_param(key: str, value: Any, reason: str = ""):
    """设置一个参数（仅更新运行时内存，不持久化除非显式 save)。"""
    cfg = _load()
    old = cfg.get(key, DEFAULT_PARAMS.get(key))
    cfg[key] = value
    _save(cfg)
    _log_feedback(key, old, value, reason)


def save():
    """手动保存当前配置。"""
    _save(_load())


# ---------------------------------------------------------------------------
# Decision 反馈回路 — 核心
# ---------------------------------------------------------------------------

def _log_feedback(key: str, old: Any, new: Any, reason: str):
    """记录参数变更到历史。"""
    FEEDBACK_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "key": key,
        "old": old,
        "new": new,
        "reason": reason,
    }
    with open(FEEDBACK_HISTORY, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def update_feedback(decision_trace: dict) -> dict:
    """
    根据一条 Decision trace 更新参数。

    decision_trace 格式：
      {
        "outcome": "positive|negative|neutral",
        "confidence": 0.45,
        "episode_summary": "...",
        "source": "daemon|api|manual",
        ...
      }

    更新逻辑：
    1. 按 outcome 调整 positive/negative/neutral 计数
    2. 计数超过窗口期时，计算新权重并更新 source.* 参数
    3. 返回本次更新的参数变更
    """
    import collections

    outcome = decision_trace.get("outcome", "neutral")
    source = decision_trace.get("source", "manual")
    confidence = float(decision_trace.get("confidence", 0.5))

    cfg = _load()
    window_days = get("decision.recent_window_days", 7)

    # 读取历史反馈
    history = _load_feedback_history(window_days)

    # 统计各 outcome 数量
    counts: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
    for entry in history:
        o = entry.get("outcome", "neutral")
        counts[o] = counts.get(o, 0) + 1

    # 当前决策计入
    counts[outcome] = counts.get(outcome, 0) + 1

    # 计算新权重
    total = sum(counts.values()) or 1
    new_positive_w = 0.5 + 0.5 * (counts["positive"] / total)
    new_negative_w = 0.5 - 0.3 * (counts["negative"] / total)
    new_neutral_w = 0.5 + 0.2 * (counts["neutral"] / total)

    changes = {}

    def _apply(key: str, value: float):
        old = cfg.get(key, DEFAULT_PARAMS.get(key, 0))
        if abs(old - value) > 0.001:
            cfg[key] = round(value, 4)
            changes[key] = {"old": old, "new": round(value, 4)}
            _log_feedback(key, old, round(value, 4), f"decision_feedback:{outcome}:{source}")

    _apply("decision.positive_weight", new_positive_w)
    _apply("decision.negative_weight", max(0.1, new_negative_w))
    _apply("decision.neutral_weight", new_neutral_w)

    # 来源权重微调：source.* 参数
    source_key = f"source.{source}"
    if source_key in cfg:
        old_src_w = cfg.get(source_key, 0.7)
        if outcome == "positive":
            new_src_w = min(1.0, old_src_w + 0.05 * confidence)
        elif outcome == "negative":
            new_src_w = max(0.3, old_src_w - 0.05)
        else:
            new_src_w = old_src_w
        if abs(old_src_w - new_src_w) > 0.001:
            cfg[source_key] = round(new_src_w, 4)
            changes[source_key] = {"old": old_src_w, "new": round(new_src_w, 4)}

    _save(cfg)
    return changes


def _load_feedback_history(days: int = 7) -> list[dict]:
    """加载最近 N 天的反馈历史。"""
    if not FEEDBACK_HISTORY.exists():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    entries = []
    try:
        for line in open(FEEDBACK_HISTORY):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("ts", "")
                if ts:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if dt.timestamp() >= cutoff:
                        entries.append(entry)
            except Exception:
                pass
    except Exception:
        pass
    return entries


# ---------------------------------------------------------------------------
# 治理报告生成
# ---------------------------------------------------------------------------

def generate_status_report() -> dict:
    """生成当前参数 + 反馈状态报告（供人类阅读）。"""
    cfg = get_all()

    # 读取 feedback 历史
    window_days = get("decision.recent_window_days", 7)
    history = _load_feedback_history(window_days)

    # 按 key 聚合最近的参数变更
    latest_changes = {}
    for entry in history[-50:]:  # 最近50条
        key = entry.get("key", "")
        latest_changes[key] = entry

    lines = [
        "# MindKernel 参数治理报告",
        f"- generated_at: {datetime.now(timezone.utc).isoformat().replace('+00:00','Z')}",
        f"- 反馈历史条目: {len(history)} (最近 {window_days} 天)",
        "",
        "## 当前核心参数",
        "",
        "### 候选提取",
        f"- high 阈值: {cfg.get('candidate.risk_threshold.high')}",
        f"- medium 阈值: {cfg.get('candidate.risk_threshold.medium')}",
        f"- 最小内容长度: {cfg.get('candidate.min_content_length')}",
        "",
        "### Experience 晋升",
        f"- auto_promote: {cfg.get('experience.auto_promote')}",
        f"- min_confidence: {cfg.get('experience.min_confidence')}",
        f"- confidence_scale: {cfg.get('experience.confidence_scale')}",
        f"- positive_boost: {cfg.get('experience.positive_boost')}",
        "",
        "### Decision 反馈权重",
        f"- positive_weight: {cfg.get('decision.positive_weight'):.4f}",
        f"- negative_weight: {cfg.get('decision.negative_weight'):.4f}",
        f"- neutral_weight: {cfg.get('decision.neutral_weight'):.4f}",
        f"- confidence_decay: {cfg.get('decision.confidence_decay')}",
        "",
        "### 来源权重",
        f"- openclaw_memory_md: {cfg.get('source.openclaw_memory_md'):.4f}",
        f"- openclaw_daily: {cfg.get('source.openclaw_daily'):.4f}",
        f"- daemon_candidate: {cfg.get('source.daemon_candidate'):.4f}",
        f"- manual: {cfg.get('source.manual'):.4f}",
        "",
        "## 最近参数变更",
    ]

    if not latest_changes:
        lines.append("（无）")
    else:
        for key, entry in sorted(latest_changes.items()):
            lines.append(
                f"- **{key}**: {entry.get('old')} → {entry.get('new')} "
                f"({entry.get('ts','')[:10]}, {entry.get('reason','')})"
            )

    return {
        "report": "\n".join(lines),
        "params": cfg,
        "history_count": len(history),
        "changes": {k: {"old": v["old"], "new": v["new"]} for k, v in latest_changes.items()},
    }
