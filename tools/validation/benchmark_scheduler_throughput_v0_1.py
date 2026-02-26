#!/usr/bin/env python3
"""Benchmark scheduler throughput/lag baseline for v0.1 (R5)."""

from __future__ import annotations

import argparse
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
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_sec)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    arr = sorted(vals)
    if len(arr) == 1:
        return arr[0]
    rank = (len(arr) - 1) * (p / 100.0)
    lo = int(rank)
    hi = min(lo + 1, len(arr) - 1)
    frac = rank - lo
    return arr[lo] * (1 - frac) + arr[hi] * frac


def worker_run(db: Path, worker_id: str, batch: int, done_flag: dict, out: dict, lock: threading.Lock):
    c = sch.conn(db)
    sch.init_db(c)

    processed = 0
    lag_samples: list[float] = []
    failures = 0
    idle_rounds = 0

    while True:
        jobs = sch.pull_due(
            c,
            worker_id=worker_id,
            now=now_iso(),
            limit=max(1, int(batch)),
            lease_sec=30,
            actions={"revalidate"},
        )

        if not jobs:
            idle_rounds += 1
            if done_flag.get("stop"):
                break
            if idle_rounds >= 5:
                # little backoff to reduce lock churn
                time.sleep(0.03)
            continue

        idle_rounds = 0
        for j in jobs:
            jid = str(j.get("job_id"))
            lease_token = str(j.get("lease_token") or "")
            try:
                run_at = sch.parse_dt(str(j.get("run_at")))
                lag = (datetime.now(timezone.utc) - run_at).total_seconds()
                if lag > 0:
                    lag_samples.append(lag)
                sch.ack(c, jid, worker_id=worker_id, lease_token=lease_token)
                processed += 1
            except Exception:
                failures += 1
                try:
                    sch.fail(
                        c,
                        jid,
                        error="benchmark-worker-failure",
                        retry_delay_sec=1,
                        worker_id=worker_id,
                        lease_token=lease_token,
                    )
                except Exception:
                    pass

    with lock:
        out[worker_id] = {
            "processed": processed,
            "failures": failures,
            "lag_samples": lag_samples,
        }


def render_md(report: dict) -> str:
    b = report["benchmark"]
    s = report["scheduler"]
    lines = [
        "# Scheduler Throughput Baseline (v0.1)",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- profile: {report['profile']}",
        f"- jobs: {b['jobs']}",
        f"- workers: {b['workers']}",
        f"- duration_sec: {b['duration_sec']}",
        f"- throughput_jobs_per_min: **{b['throughput_jobs_per_min']}**",
        f"- lag_p95_sec: **{b['lag_seconds']['p95']}**",
        f"- retry_rate: **{b['retry_rate_percent']}%**",
        "",
        "## Scheduler status",
        "",
        f"- queued: {s.get('queued')}",
        f"- running: {s.get('running')}",
        f"- succeeded: {s.get('succeeded')}",
        f"- dead_letter: {s.get('dead_letter')}",
        "",
    ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Benchmark scheduler throughput baseline")
    p.add_argument("--jobs", type=int, default=600)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--batch", type=int, default=50)
    p.add_argument("--profile", default="synthetic-revalidate")
    p.add_argument("--out-json")
    p.add_argument("--out-md")
    args = p.parse_args()

    jobs_n = max(10, int(args.jobs))
    workers_n = max(1, int(args.workers))
    batch_n = max(1, int(args.batch))

    reports_dir = ROOT / "reports" / "benchmark"
    reports_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="mk-bench-v01-") as td:
        tmp = Path(td)
        db = tmp / "bench.sqlite"

        c = sch.conn(db)
        sch.init_db(c)

        due = now_iso(offset_sec=1)
        for i in range(jobs_n):
            sch.enqueue(
                c,
                object_type="cognition",
                object_id=f"bench_cg_{i:05d}",
                action="revalidate",
                run_at=due,
                priority="medium",
                max_attempts=2,
                idempotency_key=f"bench:v01:{i:05d}",
                correlation_id="bench-throughput-v01",
            )

        time.sleep(1.15)

        done = {"stop": False}
        lock = threading.Lock()
        out: dict[str, dict] = {}
        threads = []

        t0 = time.time()
        for i in range(workers_n):
            wid = f"bench-worker-{i+1}"
            t = threading.Thread(target=worker_run, args=(db, wid, batch_n, done, out, lock), daemon=True)
            threads.append(t)
            t.start()

        # wait until all queued done
        while True:
            stats = sch.stats(c)
            if int(stats.get("queued", 0)) == 0 and int(stats.get("running", 0)) == 0:
                break
            time.sleep(0.05)

        done["stop"] = True
        for t in threads:
            t.join(timeout=3)

        duration = max(0.001, time.time() - t0)
        stats = sch.stats(c)

        all_lags = []
        total_processed = 0
        total_failures = 0
        by_worker = {}
        for wid, data in sorted(out.items()):
            processed = int(data.get("processed", 0))
            failures = int(data.get("failures", 0))
            lags = [float(x) for x in data.get("lag_samples", [])]
            by_worker[wid] = {"processed": processed, "failures": failures}
            total_processed += processed
            total_failures += failures
            all_lags.extend(lags)

        throughput = round((total_processed / duration) * 60.0, 3)
        retry_rate = round((total_failures / jobs_n) * 100.0, 3) if jobs_n > 0 else 0.0

        generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        stem = f"scheduler_baseline_{datetime.now(timezone.utc).date().isoformat()}"
        out_json = Path(args.out_json).expanduser().resolve() if args.out_json else reports_dir / f"{stem}.json"
        out_md = Path(args.out_md).expanduser().resolve() if args.out_md else reports_dir / f"{stem}.md"

        report = {
            "ok": True,
            "generated_at": generated,
            "profile": args.profile,
            "benchmark": {
                "jobs": jobs_n,
                "workers": workers_n,
                "batch": batch_n,
                "duration_sec": round(duration, 3),
                "processed": total_processed,
                "failures": total_failures,
                "throughput_jobs_per_min": throughput,
                "retry_rate_percent": retry_rate,
                "lag_seconds": {
                    "count": len(all_lags),
                    "p50": round(percentile(all_lags, 50), 3),
                    "p95": round(percentile(all_lags, 95), 3),
                    "max": round(max(all_lags), 3) if all_lags else 0.0,
                },
                "workers": by_worker,
            },
            "scheduler": {
                "queued": stats.get("queued"),
                "running": stats.get("running"),
                "succeeded": stats.get("succeeded"),
                "dead_letter": stats.get("dead_letter"),
            },
        }

        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        out_md.write_text(render_md(report), encoding="utf-8")

        print(
            json.dumps(
                {
                    "ok": True,
                    "generated_at": generated,
                    "out_json": str(out_json),
                    "out_md": str(out_md),
                    "throughput_jobs_per_min": throughput,
                    "lag_p95_sec": report["benchmark"]["lag_seconds"]["p95"],
                    "retry_rate_percent": retry_rate,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
