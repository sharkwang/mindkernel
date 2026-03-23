"""Pydantic models for MindKernel API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Retain
# ---------------------------------------------------------------------------

class RetainRequest(BaseModel):
    content: str = Field(..., description="记忆内容原文")
    source: str = Field(default="api", description="来源标识")
    document_date: Optional[datetime] = Field(
        default=None,
        description="文档/对话发生时间（用户输入时间）",
    )
    event_date: Optional[datetime] = Field(
        default=None,
        description="事件实际发生时间（可空，由 reflect 阶段填充）",
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class RetainResponse(BaseModel):
    ok: bool
    memory_id: str
    detail: str


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------

class RecallRequest(BaseModel):
    q: str = Field(..., description="语义检索查询")
    top_k: int = Field(default=5, ge=1, le=50)
    include_opinions: bool = Field(default=False)
    table: str = Field(default="memory_items")


class RecallResultItem(BaseModel):
    id: str
    content: str
    source: str
    score: float
    document_date: Optional[datetime] = None
    event_date: Optional[datetime] = None
    created_at: datetime
    status: str


class RecallResponse(BaseModel):
    ok: bool
    query: str
    count: int
    results: list[RecallResultItem]


# ---------------------------------------------------------------------------
# Reflect
# ---------------------------------------------------------------------------

class ReflectRequest(BaseModel):
    memory_id: str = Field(..., description="要反思的记忆 ID")
    episode_summary: str = Field(..., description="事件摘要")
    outcome: str = Field(..., pattern="^(positive|neutral|negative)$")


class ReflectResponse(BaseModel):
    ok: bool
    memory_id: str
    experience_id: str
    reflection: dict


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

class EntityResponse(BaseModel):
    name: str
    created_at: datetime
    last_updated: datetime
    opinions: list[dict]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    db_size_kb: int
    memory_items: int
    experience_records: int
