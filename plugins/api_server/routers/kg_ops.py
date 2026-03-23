"""POST /api/v1/knowledge/relations — 添加知识关系；extract — 从文本抽取关系."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.knowledge_graph import add_relation, auto_extract_and_store, init_graph_db
from core.memory_experience_core_v0_1 import conn
from plugins.api_server.auth import verify_api_key

router = APIRouter()


class AddRelationRequest(BaseModel):
    subject: str
    predicate: str
    object: str
    confidence: float = 0.8
    source: str | None = None


class ExtractRequest(BaseModel):
    content: str
    memory_id: str | None = None
    source: str | None = None


@router.post("/knowledge/relations")
async def add_kg_relation(req: AddRelationRequest, _key: str = Depends(verify_api_key)):
    """手动添加一条知识关系。"""
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_graph_db(c)
    c.close()

    rel_id = add_relation(
        subject=req.subject,
        predicate=req.predicate,
        obj=req.object,
        confidence=req.confidence,
        source=req.source,
    )
    return {"ok": True, "relation_id": rel_id}


@router.post("/knowledge/extract")
async def extract_relations(req: ExtractRequest, _key: str = Depends(verify_api_key)):
    """从文本内容中 LLM 抽取知识关系并自动写入图谱。"""
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_graph_db(c)
    c.close()

    stored_ids = auto_extract_and_store(
        content=req.content,
        memory_id=req.memory_id,
        source=req.source,
    )
    return {
        "ok": True,
        "extracted_count": len(stored_ids),
        "relation_ids": stored_ids,
    }
