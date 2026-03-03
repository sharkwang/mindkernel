from __future__ import annotations

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.event_normalizer_v0_2 import event_fingerprint, minute_bucket, normalize_event


class EventNormalizerV02Test(unittest.TestCase):
    def test_normalize_message_content_list(self):
        raw = {
            "session_id": "sess_1",
            "turn_id": "t_1",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "  记住 这个 偏好  "},
                    {"type": "input_text", "text": "  下周提醒我  "},
                ],
            },
            "timestamp": "2026-03-03T02:20:00Z",
        }
        out = normalize_event(raw)
        self.assertEqual(out["role"], "user")
        self.assertIn("记住", out["content"])
        self.assertIn("下周提醒我", out["content"])
        self.assertTrue(out["event_id"].startswith("evt_"))

    def test_fingerprint_stable(self):
        ev = {
            "session_id": "s",
            "turn_id": "1",
            "role": "user",
            "content": "hello",
        }
        self.assertEqual(event_fingerprint(ev), event_fingerprint(ev))

    def test_minute_bucket(self):
        b = minute_bucket("2026-03-03T10:20:59Z")
        self.assertEqual(b, "2026-03-03T10:20")


if __name__ == "__main__":
    unittest.main()
