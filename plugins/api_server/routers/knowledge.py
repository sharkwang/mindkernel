"""GET /api/v1/knowledge/relations — 查询实体知识关系."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.knowledge_graph import get_relations, init_graph_db
from core.memory_experience_core_v0_1 import conn
from plugins.api_server.auth import verify_api_key

router = APIRouter()


@router.get("/knowledge/relations")
async def get_entity_relations(
    entity: str = Query(..., description="要查询的实体名称"),
    depth: int = Query(default=1, ge=1, le=3),
    _key: str = Depends(verify_api_key),
):
    """查询某实体的知识关系图谱。"""
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_graph_db(c)
    c.close()

    relations = get_relations(entity, depth=depth)
    return {
        "ok": True,
        "entity": entity,
        "count": len(relations),
        "relations": relations,
    }
