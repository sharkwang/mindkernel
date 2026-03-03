#!/usr/bin/env python3
"""Validate external LLM resilience fallback (v0.2)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLM_TOOL = ROOT / "tools" / "memory" / "llm_memory_processor_v0_1.py"
FIXTURE = ROOT / "data" / "fixtures" / "llm-memory" / "sample-memory-input.txt"


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(
            "command failed:\n"
            + " ".join(cmd)
            + f"\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        )
    return json.loads(p.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix="mk-llm-resilience-v02-") as td:
        tmp = Path(td)
        state_file = tmp / "resilience_state.json"

        common = [
            "python3",
            str(LLM_TOOL),
            "--backend",
            "openai_compatible",
            "--endpoint",
            "http://127.0.0.1:9/v1/chat/completions",  # guaranteed fail-fast endpoint
            "--model",
            "failover-test",
            "--api-key-env",
            "OPENAI_API_KEY",
            "--timeout-sec",
            "1",
            "--max-retries",
            "0",
            "--retry-backoff-sec",
            "0",
            "--fallback-backend",
            "mock",
            "--breaker-error-threshold",
            "1",
            "--breaker-cooldown-sec",
            "120",
            "--resilience-state-file",
            str(state_file),
            "--source-ref",
            "session://resilience-test#msg:u1",
            "--text-file",
            str(FIXTURE),
            "--max-items",
            "4",
        ]

        # call 1: request fails, fallback to mock, breaker opens
        first = _run(common)
        assert first.get("ok") is True
        assert first.get("fallback_used") is True
        assert first.get("runtime_backend") == "mock"
        assert int(first.get("count", 0)) >= 1

        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert int(state.get("consecutive_failures", 0)) >= 1
        assert state.get("circuit_open_until")

        # call 2: breaker open, short-circuit to mock without retry
        second = _run(common)
        assert second.get("ok") is True
        assert second.get("fallback_used") is True
        assert second.get("fallback_reason") in {"circuit_open", "request_failed"}
        assert second.get("runtime_backend") == "mock"

        print(
            json.dumps(
                {
                    "ok": True,
                    "tmp": str(tmp),
                    "first": {
                        "runtime_backend": first.get("runtime_backend"),
                        "fallback_used": first.get("fallback_used"),
                        "attempts": first.get("attempts"),
                    },
                    "second": {
                        "runtime_backend": second.get("runtime_backend"),
                        "fallback_used": second.get("fallback_used"),
                        "fallback_reason": second.get("fallback_reason"),
                        "attempts": second.get("attempts"),
                    },
                    "state_file": str(state_file),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
