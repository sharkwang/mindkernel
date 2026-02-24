#!/usr/bin/env python3
"""CLI wrapper: MindKernel v0.1 Memory -> Experience prototype."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import (  # noqa: E402
    DEFAULT_DB,
    conn,
    extract_memory_payload,
    ingest_memory,
    init_db,
    list_audits,
    list_items,
    memory_to_experience,
)

# backward-compatible alias for existing imports in tools/*
_extract_memory_payload = extract_memory_payload


def main():
    p = argparse.ArgumentParser(description="MindKernel v0.1 Memory->Experience prototype")
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    ing = sub.add_parser("ingest-memory")
    ing.add_argument(
        "--file",
        required=True,
        help="Memory JSON/scenario file, or Markdown note (.md/.markdown with optional front matter)",
    )

    m2e = sub.add_parser("memory-to-experience")
    m2e.add_argument("--memory-id", required=True)
    m2e.add_argument("--episode-summary", required=True)
    m2e.add_argument("--outcome", required=True)

    rp = sub.add_parser("run-path")
    rp.add_argument(
        "--file",
        required=True,
        help="Memory JSON/scenario file, or Markdown note (.md/.markdown with optional front matter)",
    )
    rp.add_argument("--episode-summary", required=True)
    rp.add_argument("--outcome", required=True)

    lm = sub.add_parser("list-memory")
    lm.add_argument("--limit", type=int, default=20)

    le = sub.add_parser("list-experience")
    le.add_argument("--limit", type=int, default=20)

    la = sub.add_parser("list-audits")
    la.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    c = conn(db)
    init_db(c)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "db": str(db)}))
        return

    if args.cmd == "ingest-memory":
        payload = extract_memory_payload(Path(args.file))
        print(json.dumps(ingest_memory(c, payload), ensure_ascii=False))
        return

    if args.cmd == "memory-to-experience":
        print(
            json.dumps(
                memory_to_experience(c, args.memory_id, args.episode_summary, args.outcome),
                ensure_ascii=False,
            )
        )
        return

    if args.cmd == "run-path":
        payload = extract_memory_payload(Path(args.file))
        ing = ingest_memory(c, payload)
        res = memory_to_experience(c, ing["memory_id"], args.episode_summary, args.outcome)
        print(json.dumps({"ingest": ing, "promote": res}, ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-memory":
        print(json.dumps(list_items(c, "memory_items", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-experience":
        print(json.dumps(list_items(c, "experience_records", args.limit), ensure_ascii=False, indent=2))
        return

    if args.cmd == "list-audits":
        print(json.dumps(list_audits(c, args.limit), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
