from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class ValidateVectorReadinessV01Test(unittest.TestCase):
    def test_validate_vector_readiness_script(self):
        root = Path(__file__).resolve().parents[1]
        cmd = ["python3", "tools/validation/validate_vector_readiness_v0_1.py"]
        p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr}\nstdout: {p.stdout}")

        out = json.loads(p.stdout)
        self.assertTrue(out.get("ok"))
        self.assertIn(out.get("decision"), {"GO_PILOT", "NO_GO_KEEP_FTS"})


if __name__ == "__main__":
    unittest.main()
