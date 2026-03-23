"""GET /api/v1/health — 服务健康检查 + 运行状态."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi import APIRouter, Depends

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn, init_db
from plugins.api_server.auth import verify_api_key
from plugins.api_server.models import HealthResponse

router = APIRouter()

_START_TIME = time.time()


@router.get("/health", response_model=HealthResponse)
async def health(_key: str = Depends(verify_api_key)):
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        db_size_kb = int(db_path.stat().st_size / 1024) if db_path.exists() else 0

        mem_count = c.execute(
            "SELECT COUNT(*) FROM memory_items"
        ).fetchone()[0]
        exp_count = c.execute(
            "SELECT COUNT(*) FROM experience_records"
        ).fetchone()[0]

        return HealthResponse(
            status="ok",
            version="0.3.0",
            uptime_seconds=round(time.time() - _START_TIME, 1),
            db_size_kb=db_size_kb,
            memory_items=mem_count,
            experience_records=exp_count,
        )
    finally:
        c.close()
