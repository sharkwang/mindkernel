#!/usr/bin/env python3
"""Validate scheduler multi-worker lease/lock behavior (v0.1)."""

from __future__ import annotations

import json
import tempfile
import threading
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
    return (datetime.now(timezone.utc) + timedelta(seconds=offset_sec)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def worker_pull_ack(
    db_path: Path,
    worker_id: str,
    barrier: threading.Barrier,
    limit: int,
    result_holder: dict,
):
    c = sch.conn(db_path)
    sch.init_db(c)
    barrier.wait(timeout=8)

    jobs = sch.pull_due(
        c,
        worker_id=worker_id,
        now=now_iso(),
        limit=limit,
        lease_sec=60,
        actions={"revalidate"},
    )

    claimed = []
    for j in jobs:
        jid = str(j["job_id"])
        claimed.append(jid)
        sch.ack(
            c,
            jid,
            worker_id=worker_id,
            lease_token=str(j.get("lease_token") or ""),
        )

    result_holder[worker_id] = claimed


def main():
    with tempfile.TemporaryDirectory(prefix="mk-sched-lock-v01-") as td:
        tmp = Path(td)
        db = tmp / "scheduler.sqlite"
        c = sch.conn(db)
        sch.init_db(c)

        total_jobs = 24
        run_at = now_iso(offset_sec=1)
        for i in range(total_jobs):
            sch.enqueue(
                c,
                object_type="cognition",
                object_id=f"cg_lock_{i:03d}",
                action="revalidate",
                run_at=run_at,
                priority="medium",
                max_attempts=2,
                idempotency_key=f"lock:v01:{i:03d}",
                correlation_id="lock-validation",
            )

        time.sleep(1.2)

        worker_count = 4
        barrier = threading.Barrier(worker_count)
        results: dict[str, list[str]] = {}
        threads = []

        for i in range(worker_count):
            wid = f"lock-worker-{i+1}"
            t = threading.Thread(
                target=worker_pull_ack,
                args=(db, wid, barrier, total_jobs, results),
                daemon=True,
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=20)

        all_claimed = [jid for jobs in results.values() for jid in jobs]
        unique_claimed = sorted(set(all_claimed))

        assert len(all_claimed) == len(unique_claimed), "duplicate job claimed across workers"
        assert len(unique_claimed) == total_jobs, (
            f"expected all jobs claimed once, got unique={len(unique_claimed)} total={total_jobs}"
        )

        stats = sch.stats(c)
        assert int(stats.get("succeeded", 0)) == total_jobs, "all jobs should be succeeded"
        assert int(stats.get("queued", 0)) == 0, "queue should be empty"

        out = {
            "ok": True,
            "tmp": str(tmp),
            "workers": {k: len(v) for k, v in sorted(results.items())},
            "claimed_total": len(all_claimed),
            "claimed_unique": len(unique_claimed),
            "scheduler": {
                "queued": stats.get("queued"),
                "running": stats.get("running"),
                "succeeded": stats.get("succeeded"),
                "dead_letter": stats.get("dead_letter"),
                "leased_running_count": stats.get("leased_running_count"),
                "expired_running_count": stats.get("expired_running_count"),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
