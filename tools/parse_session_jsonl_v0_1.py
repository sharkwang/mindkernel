#!/usr/bin/env python3
"""Parse OpenClaw session JSONL into memory-event candidates (v0.1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_SESSIONS_DIR = Path("~/.openclaw/agents/main/sessions").expanduser()

RE_P_TASK = re.compile(r"\b(P\d+-\d+)\b", re.IGNORECASE)
RE_COMPLETED = re.compile(r"(已完成|完成了|做完了|做完|走完|落地|跑通|完成|done|completed)", re.IGNORECASE)
RE_MILESTONE_CLAIM = re.compile(
    r"(P\d+-\d+.{0,24}(已完成|完成了|做完了|做完|走完|落地|跑通|完成)|(?:已完成|完成了|做完了|做完|走完|落地|跑通|完成).{0,24}P\d+-\d+)",
    re.IGNORECASE,
)
RE_DIRECTIVE = re.compile(r"(一步一步|继续|开始做|按步骤|推进|执行)", re.IGNORECASE)
RE_REQUEST = re.compile(r"(我想|请|麻烦|可以|能否|看看|看下|show|please)", re.IGNORECASE)
RE_FORMAT_DISCOVERY = re.compile(r"(格式概览|文件格式|sessions?\s*结构|目录.*格式)", re.IGNORECASE)
RE_REPLY_TAG = re.compile(r"^\s*\[\[\s*reply_to[^\]]*\]\]\s*")
RE_CHAT_PREFIX = re.compile(r"^\[[A-Za-z]{3}\s+\d{4}-\d{2}-\d{2}[^\]]*\]\s*")
RE_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_dt(value: str | None) -> datetime:
    if value:
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def add_days_iso(value: str | None, days: int) -> str:
    base = parse_iso_dt(value)
    return to_iso_z(base + timedelta(days=days))


def compact_text(text: str, max_len: int = 140) -> str:
    one = " ".join(text.split())
    return one if len(one) <= max_len else one[: max_len - 1] + "…"


def make_event_id(event_type: str, source_ref: str) -> str:
    h = hashlib.sha1(f"{event_type}|{source_ref}".encode("utf-8")).hexdigest()[:12]
    return f"mem_{event_type}_{h}"


def is_system_envelope(text: str) -> bool:
    if "A scheduled reminder has been triggered." in text:
        return True
    if text.strip().startswith("System: ["):
        return True
    return False


def normalize_user_text(text: str) -> str:
    """Remove metadata wrappers and keep core human utterance when possible."""
    if not text:
        return text

    # Prefer explicit chat payload line: [Sat ...] content
    for line in text.splitlines():
        m = RE_CHAT_PREFIX.match(line)
        if m:
            payload = line[m.end() :].strip()
            if payload:
                return payload

    # If metadata wrapper exists, keep last non-empty line
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if lines and lines[0].lower().startswith("conversation info"):
        return lines[-1]

    return text.strip()


def classify_user_event(text: str) -> tuple[str, str, float, str] | None:
    if not text:
        return None
    if is_system_envelope(text):
        return None

    t = normalize_user_text(text)
    if not t:
        return None

    if RE_DIRECTIVE.search(t):
        return (
            "workflow_directive",
            f"用户发出执行指令：{compact_text(t)}",
            0.98,
            "high",
        )

    if RE_REQUEST.search(t) or "?" in t or "？" in t:
        return (
            "user_request",
            f"用户请求：{compact_text(t)}",
            0.97,
            "medium",
        )

    return None


def normalize_assistant_text(text: str) -> str:
    if not text:
        return text
    return RE_REPLY_TAG.sub("", text.strip())


def classify_assistant_event(text: str) -> tuple[str, str, float, str] | None:
    if not text:
        return None

    t = normalize_assistant_text(text)

    # Skip obvious quoted examples (avoid turning examples into fake milestones)
    if "```json" in t and ("event_type" in t or "mem_" in t):
        return None

    t_nocode = RE_CODE_FENCE.sub("", t)

    if RE_MILESTONE_CLAIM.search(t_nocode):
        p = RE_P_TASK.search(t_nocode)
        label = p.group(1).upper() if p else "里程碑"
        return (
            "milestone_completed",
            f"{label} 完成：{compact_text(t_nocode)}",
            0.94,
            "high",
        )

    if RE_FORMAT_DISCOVERY.search(t_nocode):
        return (
            "format_discovery",
            f"结构发现：{compact_text(t_nocode)}",
            0.90,
            "medium",
        )

    return None


def resolve_session_file(session_file: str | None, sessions_dir: Path, session_id: str | None, session_key: str | None) -> Path:
    if session_file:
        return Path(session_file).expanduser().resolve()

    sid = session_id
    if not sid and session_key:
        idx_path = sessions_dir / "sessions.json"
        if not idx_path.exists():
            raise SystemExit(f"sessions index not found: {idx_path}")
        data = json.loads(idx_path.read_text())
        row = data.get(session_key)
        if not row:
            raise SystemExit(f"session_key not found in index: {session_key}")
        sid = row.get("sessionId")

    if not sid:
        raise SystemExit("please provide --session-file OR --session-id OR --session-key")

    return (sessions_dir / f"{sid}.jsonl").resolve()


def parse_session_id(session_file: Path) -> str:
    try:
        first = json.loads(session_file.read_text(errors="ignore").splitlines()[0])
        if first.get("type") == "session" and first.get("id"):
            return str(first["id"])
    except Exception:
        pass
    return session_file.stem.split(".")[0]


def build_event(
    *,
    session_id: str,
    msg_id: str,
    ts: str | None,
    line_no: int,
    event_type: str,
    content: str,
    confidence: float,
    impact_tier: str,
    kind: str,
    role: str,
) -> dict:
    source_ref = f"session://{session_id}#msg:{msg_id}"
    return {
        "id": make_event_id(event_type, source_ref),
        "kind": kind,
        "event_type": event_type,
        "content": content,
        "source": {
            "source_type": "session",
            "source_ref": source_ref,
        },
        "evidence_refs": [source_ref],
        "confidence": confidence,
        "risk_tier": "low",
        "impact_tier": impact_tier,
        "status": "candidate",
        "observed_at": ts,
        "migration_meta": {
            "session_line": line_no,
            "role": role,
            "msg_id": msg_id,
        },
    }


def event_to_memory_object(
    event: dict,
    review_due_days: int,
    next_action_days: int,
    status: str,
) -> dict:
    observed_at = event.get("observed_at") or now_iso()
    created_at = to_iso_z(parse_iso_dt(observed_at))

    obj = {
        "id": event["id"],
        "kind": event.get("kind", "event"),
        "content": event.get("content", ""),
        "source": event.get("source", {}),
        "evidence_refs": event.get("evidence_refs", []),
        "confidence": float(event.get("confidence", 0.7)),
        "risk_tier": event.get("risk_tier", "low"),
        "impact_tier": event.get("impact_tier", "medium"),
        "status": status,
        "created_at": created_at,
        "review_due_at": add_days_iso(created_at, review_due_days),
        "next_action_at": add_days_iso(created_at, next_action_days),
        "event_type": event.get("event_type"),
        "migration_meta": event.get("migration_meta", {}),
    }

    # keep traceability-friendly fields if present
    if event.get("observed_at"):
        obj["observed_at"] = event["observed_at"]

    return obj


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def extract_tool_call_events(session_id: str, msg_id: str, ts: str | None, line_no: int, content_items: list[dict]) -> list[dict]:
    events = []
    for item in content_items:
        if item.get("type") != "toolCall":
            continue
        name = item.get("name") or "unknown"
        args = item.get("arguments")
        args_txt = compact_text(json.dumps(args, ensure_ascii=False), max_len=120) if args is not None else "{}"
        content = f"调用工具 {name}，参数={args_txt}"
        events.append(
            build_event(
                session_id=session_id,
                msg_id=msg_id,
                ts=ts,
                line_no=line_no,
                event_type="tool_call",
                content=content,
                confidence=0.88,
                impact_tier="medium",
                kind="event",
                role="assistant",
            )
        )
    return events


def parse_session(
    session_file: Path,
    include_tool_calls: bool,
    max_events: int,
) -> dict:
    if not session_file.exists():
        raise SystemExit(f"session file not found: {session_file}")

    session_id = parse_session_id(session_file)
    events: list[dict] = []
    seen_keys = set()

    with session_file.open() as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("type") != "message":
                continue

            message = obj.get("message", {})
            role = message.get("role")
            msg_id = obj.get("id") or f"line{line_no}"
            ts = obj.get("timestamp")
            content_items = message.get("content") or []

            text = "\n".join(
                c.get("text", "")
                for c in content_items
                if c.get("type") == "text" and c.get("text")
            ).strip()

            classified = None
            if role == "user":
                classified = classify_user_event(text)
            elif role == "assistant":
                classified = classify_assistant_event(text)

            if classified:
                event_type, content, confidence, impact_tier = classified
                kind = "fact" if event_type == "format_discovery" else "event"
                e = build_event(
                    session_id=session_id,
                    msg_id=msg_id,
                    ts=ts,
                    line_no=line_no,
                    event_type=event_type,
                    content=content,
                    confidence=confidence,
                    impact_tier=impact_tier,
                    kind=kind,
                    role=role or "unknown",
                )
                dedupe_key = (e["event_type"], e["source"]["source_ref"])
                if dedupe_key not in seen_keys:
                    seen_keys.add(dedupe_key)
                    events.append(e)

            if include_tool_calls and role == "assistant":
                for e in extract_tool_call_events(session_id, msg_id, ts, line_no, content_items):
                    dedupe_key = (e["event_type"], e["source"]["source_ref"], e["content"])
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    events.append(e)

            if max_events > 0 and len(events) >= max_events:
                break

    by_type = Counter(e["event_type"] for e in events)

    return {
        "ok": True,
        "generated_at": now_iso(),
        "session_id": session_id,
        "session_file": str(session_file),
        "summary": {
            "count": len(events),
            "by_type": dict(by_type),
        },
        "memory_events": events,
    }


def main():
    p = argparse.ArgumentParser(description="Parse OpenClaw session JSONL into memory-event candidates")
    p.add_argument("--session-file", help="session .jsonl path")
    p.add_argument("--sessions-dir", default=str(DEFAULT_SESSIONS_DIR), help="sessions directory (contains sessions.json + *.jsonl)")
    p.add_argument("--session-id", help="session id (without .jsonl)")
    p.add_argument("--session-key", help="session key in sessions.json, e.g. agent:main:main")
    p.add_argument("--include-tool-calls", action="store_true", help="also emit tool_call memory events from assistant toolCall content")
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
