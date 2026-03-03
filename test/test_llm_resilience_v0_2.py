from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.llm_resilience_v0_2 import LLMResilienceConfig, LLMResilienceController


class LLMResilienceV02Test(unittest.TestCase):
    def test_breaker_open_and_recover(self):
        with tempfile.TemporaryDirectory(prefix="mk-llm-breaker-") as td:
            state_file = Path(td) / "state.json"
            ctrl = LLMResilienceController(
                LLMResilienceConfig(
                    state_file=str(state_file),
                    error_threshold=1,
                    cooldown_sec=60,
                )
            )

            s0 = ctrl.load_state()
            self.assertFalse(ctrl.is_open(s0))

            s1 = ctrl.record_failure("boom")
            self.assertTrue(ctrl.is_open(s1))

            s2 = ctrl.record_success()
            self.assertFalse(ctrl.is_open(s2))
            self.assertEqual(int(s2.get("consecutive_failures", 0)), 0)


if __name__ == "__main__":
    unittest.main()
