"""MCP tool definitions for MindKernel core operations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools"
for _p in [str(ROOT), str(TOOLS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.memory_experience_core_v0_1 import (
    conn,
    ingest_memory,
    list_items,
    memory_to_experience,
    init_db,
)
from core.reflect_gate_v0_1 import route_proposal

# ---------------------------------------------------------------------------
# Tool: retain_memory
# ---------------------------------------------------------------------------

RETAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "记忆内容原文",
        },
        "source": {
            "type": "string",
            "description": "记忆来源标识，如 'telegram', 'feishu', 'mindkernel'",
            "default": "openclaw",
        },
        "confidence": {
            "type": "number",
            "description": "置信度 0.0~1.0",
            "default": 0.5,
        },
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "证据引用列表",
            "default": [],
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "标签列表",
            "default": [],
        },
    },
    "required": ["text"],
}


def _build_mcp_payload(text: str, source: str, confidence: float, evidence_refs: list, tags: list) -> dict:
    """将 MCP 外部格式转换为 MindKernel 内部 schema 格式。"""
    import uuid
    from datetime import datetime, timedelta, timezone

    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.isoformat().replace("+00:00", "Z")
    due_iso = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    # evidence_refs 至少要有一条；如果为空，用一个占位符
    refs = evidence_refs if evidence_refs else [f"ref_{mem_id}"]

    # 风险/影响等级默认 low，可由 tags 推导（未来扩展）
    risk = "low"
    impact = "low"
    if any(k in tags for k in ["important", "decision", "preference"]):
        impact = "medium"
    if any(k in tags for k in ["critical", "error", "correct"]):
        risk = "high"

    return {
        "id": mem_id,
        "kind": "fact",
        "content": text,
        "source": {
            "source_type": "tool",
            "source_ref": source,
        },
        "evidence_refs": refs,
        "confidence": confidence,
        "risk_tier": risk,
        "impact_tier": impact,
        "status": "candidate",
        "created_at": now_iso,
        "updated_at": now_iso,
        "review_due_at": due_iso,
        "next_action_at": due_iso,
    }


def retain_memory(args: dict) -> dict:
    """将一段文本记忆写入 MindKernel 数据库。

    外部格式（MCP）→ 内部 schema 格式的转换在这里完成，
    不污染 core 模块。
    """
    import traceback

    text = args["text"]
    source = args.get("source", "openclaw")
    confidence = args.get("confidence", 0.5)
    evidence_refs = args.get("evidence_refs", [])
    tags = args.get("tags", [])

    # 转换为内部 schema
    payload = _build_mcp_payload(text, source, confidence, evidence_refs, tags)
    mem_id = payload["id"]

    db_path = Path(__file__).resolve().parents[2] / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        result = ingest_memory(c, payload, actor_id="openclaw-mcp")
        return {"ok": True, "memory_id": mem_id, "detail": result}
    except Exception as e:
        tb = traceback.format_exc()
        return {"error": str(e), "trace": tb}
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Tool: recall_memories
# ---------------------------------------------------------------------------

RECALL_SCHEMA = {
    "type": "object",
    "properties": {
        "table": {
            "type": "string",
            "enum": ["memory_items", "experience_records"],
            "description": "查询类型：memory_items 或 experience_records",
            "default": "memory_items",
        },
        "limit": {
            "type": "integer",
            "description": "最多返回条数",
            "default": 20,
        },
    },
}


def recall_memories(args: dict) -> dict:
    """查询 MindKernel 中的记忆或经验记录。"""
    table = args.get("table", "memory_items")
    limit = args.get("limit", 20)

    db_path = Path(__file__).resolve().parents[2] / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        rows = list_items(c, table, limit)
        return {"ok": True, "table": table, "count": len(rows), "items": rows}
    except Exception as e:
        return {"error": str(e)}
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Tool: reflect_on_memory
# ---------------------------------------------------------------------------

REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "memory_id": {
            "type": "string",
            "description": "要反思的记忆 ID",
        },
        "episode_summary": {
            "type": "string",
            "description": "对该记忆对应事件的摘要描述",
        },
        "outcome": {
            "type": "string",
            "description": "事件结果：positive / neutral / negative",
        },
        "proposals_path": {
            "type": "string",
            "description": "可选：reflect gate 配置文件路径",
        },
    },
    "required": ["memory_id", "episode_summary", "outcome"],
}


def reflect_on_memory(args: dict) -> dict:
    """对一条记忆执行 reflect 流程，输出经验卡片。"""
    memory_id = args["memory_id"]
    episode_summary = args["episode_summary"]
    outcome = args["outcome"]
    config_path = args.get("proposals_path")

    db_path = Path(__file__).resolve().parents[2] / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        # 1. 跑 reflect gate
        from core.reflect_gate_v0_1 import load_gate_config as _load_cfg
        cfg = _load_cfg(config_path) if config_path else _load_cfg(None)
        proposal = {
            "id": "pending",
            "episode_summary": episode_summary,
            "outcome": outcome,
            "memory_refs": [memory_id],
        }
        routed = route_proposal(proposal, cfg or {})

        # 2. 生成 experience，同时写入 decision_traces + 更新 opinions
        exp_result = memory_to_experience(
            c, memory_id, episode_summary, outcome,
            actor_id="openclaw-mcp",
            decision_info=routed,
        )
        exp_id = exp_result["experience_id"]
        routed["id"] = exp_id

        return {
            "ok": True,
            "memory_id": memory_id,
            "experience_id": exp_id,
            "reflection": routed,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "mindkernel_retain",
        "description": "将一段文本写入 MindKernel 记忆库（retain 操作）",
        "inputSchema": RETAIN_SCHEMA,
        "fn": retain_memory,
    },
    {
        "name": "mindkernel_recall",
        "description": "查询 MindKernel 中的记忆或经验记录（recall 操作）",
        "inputSchema": RECALL_SCHEMA,
        "fn": recall_memories,
    },
    {
        "name": "mindkernel_reflect",
        "description": "对一条记忆执行反思流程，生成经验卡片（reflect 操作）",
        "inputSchema": REFLECT_SCHEMA,
        "fn": reflect_on_memory,
    },
]
