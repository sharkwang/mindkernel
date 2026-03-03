from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.realtime_memory_candidate_v0_2 import extract_candidates


class RealtimeMemoryCandidateV02Test(unittest.TestCase):
    def test_extract_user_candidate(self):
        ev = {
            "event_id": "evt_1",
            "session_id": "sess_a",
            "turn_id": "12",
            "role": "user",
            "content": "记住这个偏好：每周一上午提醒我复盘项目。",
        }
        cands = extract_candidates(ev)
        self.assertEqual(len(cands), 1)
        c = cands[0]
        self.assertIn(c["risk_level"], {"low", "medium", "high"})
        self.assertTrue(c["idempotency_key"].startswith("rtmem:"))
        self.assertEqual(c["scheduler_job"]["object_type"], "reflect_job")
        self.assertEqual(c["scheduler_job"]["action"], "reflect")

    def test_non_user_no_candidate(self):
        ev = {
            "event_id": "evt_2",
            "session_id": "sess_a",
            "turn_id": "13",
            "role": "assistant",
            "content": "收到。",
        }
        self.assertEqual(extract_candidates(ev), [])


if __name__ == "__main__":
    unittest.main()
