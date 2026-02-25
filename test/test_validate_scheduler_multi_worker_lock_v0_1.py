from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class ValidateSchedulerMultiWorkerLockV01Test(unittest.TestCase):
    def test_validate_scheduler_multi_worker_lock_script(self):
        root = Path(__file__).resolve().parents[1]
        cmd = ["python3", "tools/validation/validate_scheduler_multi_worker_lock_v0_1.py"]
        p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr}\nstdout: {p.stdout}")

        out = json.loads(p.stdout)
        self.assertTrue(out.get("ok"))
        self.assertGreaterEqual(int(out.get("claimed_unique", 0)), 1)
        self.assertEqual(int(out.get("claimed_total", 0)), int(out.get("claimed_unique", 0)))


if __name__ == "__main__":
    unittest.main()
