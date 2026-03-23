"""POST /api/v1/adapters/poll — 触发所有适配器执行并写入记忆."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from plugins.api_server.auth import verify_api_key
from plugins.api_server.routers.retain import _build_payload
from core.memory_experience_core_v0_1 import conn, ingest_memory, init_db

router = APIRouter()

ADAPTERS = {}


def _register_adapters():
    """延迟注册，避免循环导入。"""
    if ADAPTERS:
        return
    try:
        from adapters.browser_bookmark_adapter import poll as bm_poll
        ADAPTERS["browser_bookmark"] = bm_poll
    except Exception:
        pass
    try:
        from adapters.filesystem_adapter import poll as fs_poll
        ADAPTERS["filesystem"] = fs_poll
    except Exception:
        pass


@router.post("/adapters/poll")
async def poll_adapters(
    adapter: str | None = None,  # None = 全部
    _key: str = Depends(verify_api_key),
):
    """
    触发一个或全部适配器，将结果写入记忆库。

    adapter= 全部（默认）
    adapter=browser_bookmark
    adapter=filesystem
    """
    _register_adapters()

    if adapter and adapter not in ADAPTERS:
        return {"ok": False, "error": f"Unknown adapter: {adapter}"}

    targets = {adapter: ADAPTERS[adapter]} if adapter else ADAPTERS
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    total_written = 0
    results = {}

    try:
        for name, poll_fn in targets.items():
            try:
                events = poll_fn()
            except Exception as e:
                results[name] = {"error": str(e), "written": 0}
                continue

            written = 0
            for ev in events:
                payload = _build_payload(
                    content=ev["content"],
                    source=ev["source"],
                    document_date=_parse_dt(ev.get("document_date")),
                    event_date=None,
                    confidence=0.5,
                    tags=ev.get("tags", []),
                    metadata=ev.get("metadata", {}),
                )
                try:
                    ingest_memory(c, payload, actor_id=f"adapter:{name}")
                    written += 1
                except Exception:
                    pass

            results[name] = {"found": len(events), "written": written}
            total_written += written
    finally:
        c.close()

    return {"ok": True, "total_written": total_written, "results": results}


def _parse_dt(val):
    if not val:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return None
