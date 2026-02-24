from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.memory_experience_core_v0_1 import (
    conn,
    ingest_memory,
    init_db,
    list_audits,
    memory_to_experience,
)


class MemoryExperienceCoreV01Test(unittest.TestCase):
    def test_ingest_and_promote_happy_path(self):
        root = Path(__file__).resolve().parents[1]
        fixture_path = root / "data" / "fixtures" / "critical-paths" / "08-memory-experience-path.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))["memory"]

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mk.sqlite"
            c = conn(db_path)
            init_db(c)

            ing = ingest_memory(c, payload, actor_id="test")
            self.assertEqual(ing["memory_id"], payload["id"])

            pro = memory_to_experience(
                c,
                memory_id=payload["id"],
                episode_summary="test summary",
                outcome="candidate generated",
                actor_id="test",
            )

            self.assertEqual(pro["memory_status"], "active")
            self.assertEqual(pro["experience_status"], "candidate")

            audits = list_audits(c, limit=10)
            self.assertGreaterEqual(len(audits), 2)

    def test_duplicate_memory_id_rejected(self):
        root = Path(__file__).resolve().parents[1]
        fixture_path = root / "data" / "fixtures" / "critical-paths" / "08-memory-experience-path.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))["memory"]

        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "mk.sqlite"
            c = conn(db_path)
            init_db(c)

            ingest_memory(c, payload, actor_id="test")
            with self.assertRaises(ValueError):
                ingest_memory(c, payload, actor_id="test")


if __name__ == "__main__":
    unittest.main()
