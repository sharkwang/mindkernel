"""POST /api/v1/reflect — 对一条记忆执行反思流程."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn, init_db, memory_to_experience
from core.reflect_gate_v0_1 import load_gate_config, route_proposal
from plugins.api_server.auth import verify_api_key
from plugins.api_server.models import ReflectRequest, ReflectResponse

router = APIRouter()


@router.post("/reflect", response_model=ReflectResponse)
async def reflect(req: ReflectRequest, _key: str = Depends(verify_api_key)):
    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)
    init_db(c)

    try:
        # 1. 跑 reflect gate（先生成 proposal）
        cfg = load_gate_config(None)
        proposal = {
            "id": "pending",  # 临时 ID，等 exp_id 生成后再填充
            "episode_summary": req.episode_summary,
            "outcome": req.outcome,
            "memory_refs": [req.memory_id],
        }
        routed = route_proposal(proposal, cfg or {})

        # 2. 生成 experience，同时写入 decision_traces
        routed["source"] = req.source  # 透传来源，供治理引擎追踪
        exp_result = memory_to_experience(
            c,
            req.memory_id,
            req.episode_summary,
            req.outcome,
            actor_id="api",
            decision_info=routed,  # 传入 decision，写入 decision_traces
        )
        exp_id = exp_result["experience_id"]

        # 更新 proposal ID
        routed["id"] = exp_id

        return ReflectResponse(
            ok=True,
            memory_id=req.memory_id,
            experience_id=exp_id,
            reflection=routed,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"memory_id not found: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        c.close()
