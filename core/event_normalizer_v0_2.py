"""MindKernel v0.2 event normalizer (D2).

Standardizes heterogeneous conversation events into a stable shape
used by realtime candidate extraction.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

_WHITESPACE_RE = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _coerce_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        # common message payload shape
        if isinstance(content.get("text"), str):
            return content.get("text") or ""
        if isinstance(content.get("content"), str):
            return content.get("content") or ""
        return ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                t = item.get("type")
                if t in {"text", "input_text", "output_text"}:
                    tx = item.get("text")
                    if isinstance(tx, str):
                        parts.append(tx)
                        continue
                # fallback fields
                for k in ("text", "content"):
                    v = item.get(k)
                    if isinstance(v, str) and v:
                        parts.append(v)
                        break
        return "\n".join(parts)
    return str(content)


def _normalize_ws(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text or "").strip()


def normalize_event(raw: dict, *, default_session_id: str = "session_unknown") -> dict:
    """Normalize a raw event into stable fields.

    Output shape:
    {
      event_id, session_id, turn_id, role, channel, content, content_len,
      timestamp, raw
    }
    """

    msg = raw.get("message") if isinstance(raw.get("message"), dict) else None

    event_id = str(raw.get("event_id") or raw.get("id") or raw.get("msg_id") or "")
    session_id = str(raw.get("session_id") or raw.get("session") or default_session_id)
    turn_id = str(raw.get("turn_id") or raw.get("turn") or raw.get("id") or "")
    role = str(raw.get("role") or (msg or {}).get("role") or "user").lower()
    channel = str(raw.get("channel") or raw.get("source") or "unknown")

    raw_content = raw.get("content")
    if raw_content is None and msg is not None:
        raw_content = msg.get("content")

    content = _normalize_ws(_coerce_text(raw_content))
    ts = str(raw.get("timestamp") or raw.get("created_at") or now_iso())

    if not event_id:
        seed = f"{session_id}|{turn_id}|{role}|{content[:80]}|{ts}"
        event_id = f"evt_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:12]}"

    return {
        "event_id": event_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "role": role,
        "channel": channel,
        "content": content,
        "content_len": len(content),
        "timestamp": ts,
        "raw": raw,
    }


def event_fingerprint(ev: dict) -> str:
    seed = "|".join(
        [
            str(ev.get("session_id") or ""),
            str(ev.get("turn_id") or ""),
            str(ev.get("role") or ""),
            str(ev.get("content") or ""),
        ]
    )
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()


def minute_bucket(ts: str) -> str:
    """Return YYYY-MM-DDTHH:MM bucket in UTC best-effort parsing."""
    v = ts or now_iso()
    try:
        if v.endswith("Z"):
            dt = datetime.fromisoformat(v[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M")

