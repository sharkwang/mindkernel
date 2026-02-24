from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.reflect_gate_v0_1 import route_proposals


class ReflectGateV01Test(unittest.TestCase):
    def test_route_proposals_with_hard_rules_and_sampling(self):
        proposals = [
            {
                "proposal_id": "p_low",
                "job_id": "j1",
                "operation": "upsert",
                "target_type": "opinion",
                "risk_score": 18,
                "evidence_refs": ["ev://1", "ev://2"],
            },
            {
                "proposal_id": "p_medium",
                "job_id": "j1",
                "operation": "upsert",
                "target_type": "entity",
                "risk_score": 50,
                "evidence_refs": ["ev://3", "ev://4"],
            },
            {
                "proposal_id": "p_high_hard",
                "job_id": "j1",
                "operation": "delete",
                "target_type": "core_memory",
                "risk_score": 10,
                "evidence_refs": ["ev://5", "ev://6"],
            },
        ]

        cfg = {
            "thresholds": {"low_max": 39, "medium_max": 69, "high_min": 70},
            "sampling": {"medium_ratio": 0.0},
            "hard_rules": {
                "always_high_operations": ["delete", "overwrite", "merge_conflict"],
                "always_high_targets": ["core_memory", "persona_trait"],
            },
        }

        with tempfile.TemporaryDirectory() as td:
            in_path = Path(td) / "proposals.json"
            cfg_path = Path(td) / "cfg.json"
            in_path.write_text(json.dumps(proposals, ensure_ascii=False), encoding="utf-8")
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")

            out = route_proposals(str(in_path), config_path=str(cfg_path))

        self.assertTrue(out["ok"])
        self.assertEqual(out["counts"]["total"], 3)
        self.assertEqual(out["by_risk_level"]["high"], 1)
        self.assertEqual(out["by_risk_level"]["low"], 1)
        self.assertEqual(out["by_risk_level"]["medium"], 1)

        routed = {x["proposal_id"]: x for x in out["proposals"]}
        self.assertEqual(routed["p_low"]["decision"], "auto_applied")
        self.assertEqual(routed["p_medium"]["decision"], "auto_applied")
        self.assertEqual(routed["p_high_hard"]["decision"], "pending_review")
        self.assertIn("HARD_RULE_OPERATION", routed["p_high_hard"]["reason_codes"])


if __name__ == "__main__":
    unittest.main()
