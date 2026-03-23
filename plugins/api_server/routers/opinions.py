"""GET /api/v1/opinions/panel — Opinion 可视化面板."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from plugins.api_server.auth import verify_api_key

router = APIRouter()

PANEL_PATH = ROOT / "reports" / "opinion_panel.html"


@router.get("/opinions/panel")
async def opinion_panel(_key: str = Depends(verify_api_key)):
    """返回 Opinion 可视化 HTML 面板。"""
    if PANEL_PATH.exists():
        # 刷新后再返回
        import subprocess
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "inspect_opinions.py")],
            capture_output=True,
            cwd=str(ROOT),
        )
        return FileResponse(str(PANEL_PATH), media_type="text/html")
    return {"ok": False, "error": "Panel not generated yet"}
