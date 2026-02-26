from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


class ValidateSchedulerBenchmarkV01Test(unittest.TestCase):
    def test_validate_scheduler_benchmark_script(self):
        root = Path(__file__).resolve().parents[1]
        cmd = ["python3", "tools/validation/validate_scheduler_benchmark_v0_1.py"]
        p = subprocess.run(cmd, cwd=str(root), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr}\nstdout: {p.stdout}")

        out = json.loads(p.stdout)
        self.assertTrue(out.get("ok"))
        self.assertGreater(float(out.get("throughput_jobs_per_min", 0.0)), 0.0)


if __name__ == "__main__":
    unittest.main()
