"""MindKernel v0.2 realtime memory candidate extractor (D3)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

HIGH_RISK_PATTERNS = [
    r"\b(delete|wipe|erase|reset all|overwrite)\b",
    r"删除|清空|覆盖|重置全部|抹掉",
]
MEDIUM_RISK_PATTERNS = [
    r"\b(todo|deadline|remind|follow[- ]?up|plan)\b",
    r"待办|截止|提醒|计划|下周|记住|记一下|跟进",
]

MEMORY_SIGNAL_PATTERNS = [
    r"\b(remember|preference|always|never)\b",
    r"记住|偏好|习惯|长期",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def in_seconds_iso(sec: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0, int(sec)))).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _has_any(patterns: list[str], text: str) -> bool:
    if not text:
        return False
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def infer_risk(text: str) -> tuple[int, str, list[str]]:
    reasons: list[str] = []
    if _has_any(HIGH_RISK_PATTERNS, text):
        reasons.append("HIGH_RISK_PATTERN")
        return 82, "high", reasons
    if _has_any(MEDIUM_RISK_PATTERNS, text):
        reasons.append("MEDIUM_RISK_PATTERN")
        return 56, "medium", reasons
    reasons.append("DEFAULT_LOW")
    return 25, "low", reasons


def infer_value_score(text: str, role: str) -> int:
    base = 20 if role == "user" else 8
    if _has_any(MEMORY_SIGNAL_PATTERNS, text):
        base += 25
    if _has_any(MEDIUM_RISK_PATTERNS, text):
        base += 20
    return min(100, base)


def _priority_from_risk_level(level: str) -> str:
    if level == "high":
        return "high"
    if level == "medium":
        return "medium"
    return "low"


def _stable_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def extract_candidates(
    ev: dict,
    *,
    min_content_len: int = 6,
    max_candidates: int = 1,
) -> list[dict]:
    """Extract realtime candidates from normalized event.

    D3 policy (minimal):
    - focus on user events
    - require non-empty content and min length
    - one candidate per event by default
    """

    role = str(ev.get("role") or "")
    text = str(ev.get("content") or "").strip()
    if role != "user":
        return []
    if len(text) < max(1, int(min_content_len)):
        return []

    risk_score, risk_level, reasons = infer_risk(text)
    value_score = infer_value_score(text, role)

    seed = f"{ev.get('session_id')}|{ev.get('turn_id')}|{ev.get('event_id')}|{text}"
    h = _stable_hash(seed)
    candidate_id = f"cand_{h[:12]}"
    object_id = f"rt_reflect_{ev.get('session_id','s')}_{ev.get('turn_id','t')}_{h[:8]}"
    idem = f"rtmem:{ev.get('session_id','s')}:{ev.get('turn_id','t')}:{h[:16]}"

    candidate = {
        "candidate_id": candidate_id,
        "event_id": ev.get("event_id"),
        "session_id": ev.get("session_id"),
        "turn_id": ev.get("turn_id"),
        "role": role,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "value_score": value_score,
        "reason_codes": reasons,
        "summary": text[:200],
        "created_at": now_iso(),
        "idempotency_key": idem,
        "scheduler_job": {
            "object_type": "reflect_job",
            "object_id": object_id,
            "action": "reflect",
            "run_at": in_seconds_iso(1),
            "priority": _priority_from_risk_level(risk_level),
            "max_attempts": 3,
            "idempotency_key": idem,
            "correlation_id": f"daemon_v0_2:{ev.get('session_id')}:{ev.get('turn_id')}",
        },
    }

    return [candidate][: max(1, int(max_candidates))]

