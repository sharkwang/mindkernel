#!/usr/bin/env python3
"""
MindKernel v0.1 full path prototype:
Memory -> Experience -> Cognition -> DecisionTrace (with Persona Gate)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cognition_decision_v0_1 import (
    cognition_to_decision,
    gate_block_to_decision,
    init_db as cd_init_db,
)
from experience_cognition_v0_1 import (
    _extract_payload as extract_payload,
    experience_to_cognition,
    init_db as ec_init_db,
    upsert_persona,
)
from memory_experience_v0_1 import (
    _extract_memory_payload,
    conn,
    ingest_memory,
    init_db as me_init_db,
    memory_to_experience,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "mindkernel_v0_1.sqlite"


def init_all_tables(c):
    me_init_db(c)
    ec_init_db(c)
    cd_init_db(c)


def run_full_path(
    c,
    memory_file: Path,
    persona_file: Path,
    episode_summary: str,
    outcome: str,
    request_ref: str,
    risk_tier: str | None = None,
    actor_id: str = "mk-full-path",
):
    memory_payload = _extract_memory_payload(memory_file)
    persona_payload = extract_payload(persona_file, "persona")

    r_mem = ingest_memory(c, memory_payload, actor_id=actor_id)
    r_exp = memory_to_experience(c, r_mem["memory_id"], episode_summary, outcome, actor_id=actor_id)
    r_per = upsert_persona(c, persona_payload, actor_id=actor_id)
    r_cog = experience_to_cognition(c, r_exp["experience_id"], r_per["persona_id"], actor_id=actor_id)

    if r_cog.get("cognition_created"):
        r_dec = cognition_to_decision(
            c,
            r_cog["cognition_id"],
            request_ref=request_ref,
            risk_tier=risk_tier,
            actor_id=actor_id,
        )
    else:
        r_dec = gate_block_to_decision(
            c,
            experience_id=r_exp["experience_id"],
            persona_id=r_per["persona_id"],
            request_ref=request_ref,
            boundary_hits=r_cog.get("boundary_hits", []),
            risk_tier=risk_tier or "high",
            actor_id=actor_id,
        )

    return {
        "memory": r_mem,
        "experience": r_exp,
        "persona": r_per,
        "cognition": r_cog,
        "decision": r_dec,
    }


def main():
    p = argparse.ArgumentParser(description="MindKernel v0.1 full path prototype")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    rp = sub.add_parser("run-full-path")
    rp.add_argument("--memory-file", required=True, help="Memory JSON/scenario or Markdown file")
    rp.add_argument("--persona-file", required=True, help="Persona JSON/scenario file")
    rp.add_argument("--episode-summary", required=True)
    rp.add_argument("--outcome", required=True)
    rp.add_argument("--request-ref", required=True)
    rp.add_argument("--risk-tier", choices=["low", "medium", "high"])

    args = p.parse_args()

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = conn(db)
    init_all_tables(c)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "db": str(db)}))
        return

    if args.cmd == "run-full-path":
        result = run_full_path(
            c,
            Path(args.memory_file),
            Path(args.persona_file),
            args.episode_summary,
            args.outcome,
            request_ref=args.request_ref,
            risk_tier=args.risk_tier,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
