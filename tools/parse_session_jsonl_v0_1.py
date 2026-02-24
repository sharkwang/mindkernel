#!/usr/bin/env python3
"""CLI wrapper: parse OpenClaw session JSONL into memory-event candidates (v0.1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.session_memory_parser_v0_1 import (  # noqa: E402
    DEFAULT_SESSIONS_DIR,
    event_to_memory_object,
    parse_session,
    resolve_session_file,
    write_jsonl,
)


def main():
    p = argparse.ArgumentParser(description="Parse OpenClaw session JSONL into memory-event candidates")
    p.add_argument("--session-file", help="session .jsonl path")
    p.add_argument(
        "--sessions-dir",
        default=str(DEFAULT_SESSIONS_DIR),
        help="sessions directory (contains sessions.json + *.jsonl)",
    )
    p.add_argument("--session-id", help="session id (without .jsonl)")
    p.add_argument("--session-key", help="session key in sessions.json, e.g. agent:main:main")
    p.add_argument(
        "--include-tool-calls",
        action="store_true",
        help="also emit tool_call memory events from assistant toolCall content",
    )
    p.add_argument("--max-events", type=int, default=0, help="max emitted events (0 = no limit)")
    p.add_argument("--out", help="optional output json path")
    p.add_argument("--memory-jsonl-out", help="optional output path for memory.schema-compatible JSONL")
    p.add_argument("--review-due-days", type=int, default=7, help="review_due_at = created_at + N days for memory JSONL")
    p.add_argument("--next-action-days", type=int, default=7, help="next_action_at = created_at + N days for memory JSONL")
    p.add_argument(
        "--memory-status",
        default="candidate",
        choices=["candidate", "quarantine", "verified", "active", "stale", "stale_uncertain", "rejected_poisoned", "archived"],
        help="status field value when emitting memory JSONL",
    )
    args = p.parse_args()

    sessions_dir = Path(args.sessions_dir).expanduser().resolve()
    session_file = resolve_session_file(args.session_file, sessions_dir, args.session_id, args.session_key)

    out = parse_session(
        session_file=session_file,
        include_tool_calls=args.include_tool_calls,
        max_events=max(0, int(args.max_events)),
    )

    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    if args.memory_jsonl_out:
        mem_rows = [
            event_to_memory_object(
                e,
                review_due_days=max(0, int(args.review_due_days)),
                next_action_days=max(0, int(args.next_action_days)),
                status=args.memory_status,
            )
            for e in out.get("memory_events", [])
        ]
        mem_path = Path(args.memory_jsonl_out).expanduser().resolve()
        write_jsonl(mem_path, mem_rows)
        out["memory_jsonl"] = {
            "path": str(mem_path),
            "count": len(mem_rows),
            "review_due_days": max(0, int(args.review_due_days)),
            "next_action_days": max(0, int(args.next_action_days)),
            "status": args.memory_status,
        }

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
