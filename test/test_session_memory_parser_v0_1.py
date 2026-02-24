from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.session_memory_parser_v0_1 import parse_session


class SessionMemoryParserV01Test(unittest.TestCase):
    def test_tool_call_ids_are_unique_per_item(self):
        session_lines = [
            {"type": "session", "id": "sess_test_001"},
            {
                "type": "message",
                "id": "m1",
                "timestamp": "2026-02-24T02:00:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "toolCall", "name": "read", "arguments": {"path": "A.md"}},
                        {"type": "toolCall", "name": "read", "arguments": {"path": "B.md"}},
                    ],
                },
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            session_path = Path(td) / "sess.jsonl"
            with session_path.open("w", encoding="utf-8") as f:
                for row in session_lines:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

            out = parse_session(session_path, include_tool_calls=True, max_events=0)

        self.assertTrue(out["ok"])
        tool_events = [e for e in out["memory_events"] if e["event_type"] == "tool_call"]
        self.assertEqual(len(tool_events), 2)
        ids = [e["id"] for e in tool_events]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
