"""POST /api/v1/retain — 写入一条记忆到 MindKernel."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn, ingest_memory, init_db
from plugins.api_server.auth import verify_api_key
from plugins.api_server.models import RetainRequest, RetainResponse

router = APIRouter()


def _build_payload(
    content: str,
    source: str,
    document_date: datetime | None,
    event_date: datetime | None,
    confidence: float,
    tags: list[str],
    metadata: dict,
) -> dict:
    """构建内部 schema payload，兼容现有 ingest_memory 接口。"""
    import uuid

    mem_id = f"mem_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    now_iso = now.isoformat().replace("+00:00", "Z")
    doc_date_iso = (document_date or now).isoformat().replace("+00:00", "Z")
    ev_date_iso = event_date.isoformat().replace("+00:00", "Z") if event_date else None

    risk = "low"
    impact = "low"
    if any(k in tags for k in ["important", "decision", "preference"]):
        impact = "medium"
    if any(k in tags for k in ["critical", "error", "correct"]):
        risk = "high"

    due_iso = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    return {
        "id": mem_id,
        "kind": "fact",
        "content": content,
        "source": {"source_type": "external", "source_ref": source},
        "evidence_refs": [f"ref_{mem_id}"],
        "confidence": confidence,
        "risk_tier": risk,
        "impact_tier": impact,
        "status": "candidate",
        "created_at": now_iso,
        "updated_at": now_iso,
        "review_due_at": due_iso,
        "next_action_at": due_iso,
        # 双层时间戳字段（扩展）
        "document_date": doc_date_iso,
        "event_date": ev_date_iso,
        # 透传 metadata
        "metadata": metadata,
    }


@router.post("/retain", response_model=RetainResponse)
async def retain(req: RetainRequest, _key: str = Depends(verify_api_key)):
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        payload = _build_payload(
            content=req.content,
            source=req.source,
            document_date=req.document_date,
            event_date=req.event_date,
            confidence=req.confidence,
            tags=req.tags,
            metadata=req.metadata,
        )
        result = ingest_memory(c, payload, actor_id="api")
        detail = result if isinstance(result, str) else str(result)
        return RetainResponse(ok=True, memory_id=payload["id"], detail=detail)
    finally:
        c.close()
