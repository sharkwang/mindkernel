"""v0.2 external LLM resilience controller.

Provides a lightweight circuit-breaker state persisted on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_dt(v: str | None) -> datetime | None:
    if not v:
        return None
    s = str(v)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


@dataclass
class LLMResilienceConfig:
    state_file: str
    error_threshold: int = 3
    cooldown_sec: int = 300


class LLMResilienceController:
    def __init__(self, cfg: LLMResilienceConfig):
        self.cfg = cfg
        self.path = Path(cfg.state_file).expanduser().resolve()

    def _default(self) -> dict:
        return {
            "consecutive_failures": 0,
            "circuit_open_until": None,
            "last_error": None,
            "updated_at": now_iso(),
        }

    def load_state(self) -> dict:
        if not self.path.exists():
            return self._default()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return self._default()
            out = self._default()
            out.update(raw)
            return out
        except Exception:  # noqa: BLE001
            return self._default()

    def save_state(self, state: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = dict(state)
        state["updated_at"] = now_iso()
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_open(self, state: dict | None = None) -> bool:
        st = state or self.load_state()
        open_until = parse_dt(st.get("circuit_open_until"))
        if not open_until:
            return False
        return datetime.now(timezone.utc) < open_until

    def record_success(self) -> dict:
        st = self.load_state()
        st["consecutive_failures"] = 0
        st["circuit_open_until"] = None
        st["last_error"] = None
        self.save_state(st)
        return st

    def record_failure(self, err: str) -> dict:
        st = self.load_state()
        failures = int(st.get("consecutive_failures") or 0) + 1
        st["consecutive_failures"] = failures
        st["last_error"] = str(err)

        if failures >= max(1, int(self.cfg.error_threshold)):
            st["circuit_open_until"] = (
                datetime.now(timezone.utc) + timedelta(seconds=max(1, int(self.cfg.cooldown_sec)))
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        self.save_state(st)
        return st

