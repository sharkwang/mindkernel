from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class ValidateTemporalVerifyRevalidateV01Test(unittest.TestCase):
    def test_validate_temporal_verify_revalidate_script(self):
        root = Path(__file__).resolve().parents[1]
        cmd = ["python3", "tools/validation/validate_temporal_verify_revalidate_v0_1.py"]
        p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr}\nstdout: {p.stdout}")

        out = json.loads(p.stdout)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("memory_status", {}).get("mem_verify"), "verified")


if __name__ == "__main__":
    unittest.main()
