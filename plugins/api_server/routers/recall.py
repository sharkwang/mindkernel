"""GET /api/v1/recall — 语义检索 MindKernel 记忆."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn, init_db
from plugins.api_server.auth import verify_api_key
from plugins.api_server.models import RecallResponse, RecallResultItem

router = APIRouter()


def _parse_date(val) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.get("/recall", response_model=RecallResponse)
async def recall(
    q: str = Query(..., description="语义检索查询"),
    top_k: int = Query(default=5, ge=1, le=50),
    include_opinions: bool = Query(default=False),
    table: str = Query(default="memory_items"),
    _key: str = Depends(verify_api_key),
):
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        # 关键词匹配：content 包含查询词即命中
        # 后续替换为向量检索以提升语义匹配质量
        rows = c.execute(
            f"SELECT id, status, updated_at, payload_json FROM {table} ORDER BY updated_at DESC LIMIT ?",
            (top_k * 10,),
        ).fetchall()

        q_lower = q.lower()
        scored = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, KeyError):
                continue
            content = payload.get("content", "")
            if q_lower in content.lower():
                item = RecallResultItem(
                    id=row["id"],
                    content=content,
                    source=payload.get("source", {}).get("source_ref", "unknown"),
                    score=float(content.lower().count(q_lower)),
                    document_date=_parse_date(payload.get("document_date")),
                    event_date=_parse_date(payload.get("event_date")),
                    created_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
                    status=row["status"],
                )
                scored.append((content.lower().count(q_lower), item))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [item for _, item in scored[:top_k]]

        return RecallResponse(
            ok=True,
            query=q,
            count=len(results),
            results=results,
        )
    finally:
        c.close()
