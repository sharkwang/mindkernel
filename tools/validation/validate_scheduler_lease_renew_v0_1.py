#!/usr/bin/env python3
"""Validate scheduler lease renew/heartbeat behavior (R2)."""

from __future__ import annotations

import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS_SCHED = ROOT / "tools" / "scheduler"

import sys

if str(TOOLS_SCHED) not in sys.path:
    sys.path.insert(0, str(TOOLS_SCHED))

import scheduler_v0_1 as sch  # noqa: E402


def now_iso(offset_sec: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_sec)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main():
    with tempfile.TemporaryDirectory(prefix="mk-lease-renew-v01-") as td:
        tmp = Path(td)
        db = tmp / "scheduler.sqlite"

        c = sch.conn(db)
        sch.init_db(c)

        enq = sch.enqueue(
            c,
            object_type="reflect_job",
            object_id="renew_demo",
            action="reflect",
            run_at=now_iso(offset_sec=1),
            priority="high",
            max_attempts=3,
            idempotency_key="lease-renew:v01:1",
            correlation_id="lease-renew-validation",
        )
        job_id = str(enq["job_id"])

        time.sleep(1.2)
        pulled = sch.pull_due(c, worker_id="lease-worker", now=now_iso(), limit=1, lease_sec=2, actions={"reflect"})
        assert len(pulled) == 1, "should pull exactly one job"
        job = pulled[0]
        lease_token = str(job.get("lease_token") or "")
        lease_before = str(job.get("lease_expires_at") or "")

        time.sleep(1.1)
        renewed = sch.renew_lease(
            c,
            job_id=job_id,
            worker_id="lease-worker",
            lease_token=lease_token,
            extend_sec=5,
        )
        lease_after = str(renewed.get("lease_expires_at") or "")
        assert lease_after > lease_before, "renewed lease should be later than previous lease"

        # exceed original lease window but still before renewed expiry
        time.sleep(2.3)
        sch.ack(c, job_id, worker_id="lease-worker", lease_token=lease_token)

        row = c.execute("SELECT status, lease_expires_at FROM scheduler_jobs WHERE job_id=?", (job_id,)).fetchone()
        assert row and row[0] == "succeeded", "job should succeed after renewal"
        assert row[1] is None, "lease should clear after ack"

        stats = sch.stats(c)
        audits = sch.list_audits(c, limit=20)
        renew_audits = [a for a in audits if a.get("reason") == "Lease renewed by worker heartbeat."]
        assert renew_audits, "renew audit event should be written"

        out = {
            "ok": True,
            "tmp": str(tmp),
            "job_id": job_id,
            "lease_before": lease_before,
            "lease_after": lease_after,
            "scheduler": {
                "queued": stats.get("queued"),
                "running": stats.get("running"),
                "succeeded": stats.get("succeeded"),
                "dead_letter": stats.get("dead_letter"),
            },
            "renew_audit_count": len(renew_audits),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
