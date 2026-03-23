"""POST /api/v1/prune — 触发 TTL 遗忘策略执行."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from plugins.api_server.auth import verify_api_key
from core.ttl_strategy import run_prune

router = APIRouter()


@router.post("/prune")
async def prune(apply: bool = False, _key: str = Depends(verify_api_key)):
    """
    触发 TTL 遗忘策略。

    apply=false（默认）：干跑模式，只报告会清理哪些，不实际删除
    apply=true：实际执行删除
    """
    result = run_prune(dry_run=not apply)
    return result
