#!/usr/bin/env python3
"""Temporal governance worker for decay/archive/reinstate-check actions (v0.1)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scheduler_v0_1 as sch  # noqa: E402
from core.memory_experience_core_v0_1 import init_db as init_me_db  # noqa: E402

OBJECT_TABLES = {
    "memory": "memory_items",
    "experience": "experience_records",
}

WORKER_ACTIONS = {"decay", "archive", "reinstate-check"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def in_days_iso(days: int, base: str | None = None) -> str:
    if base:
        b = sch.parse_dt(base)
    else:
        b = datetime.now(timezone.utc)
    return (b + timedelta(days=max(0, int(days)))).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_payload(raw: str) -> dict:
    payload = json.loads(raw or "{}")
    if not isinstance(payload, dict):
        raise ValueError("payload_json must be object")
    return payload


def _evidence_refs(object_type: str, payload: dict, object_id: str, job_id: str) -> list[str]:
    refs = payload.get("evidence_refs")
    if isinstance(refs, list):
        out = [str(x) for x in refs if str(x)]
        if out:
            return out

    if object_type == "experience":
        mrefs = payload.get("memory_refs")
        if isinstance(mrefs, list):
            out = [f"memory:{x}" for x in mrefs if str(x)]
            if out:
                return out

    return [f"{object_type}:{object_id}", f"scheduler_job:{job_id}"]


def _has_reinstate_signal(payload: dict) -> bool:
    if bool(payload.get("reinstate_signal")):
        return True

    try:
        if int(payload.get("reinforcement_count", 0)) > 0:
            return True
    except Exception:
        pass

    try:
        if int(payload.get("new_evidence_count", 0)) > 0:
            return True
    except Exception:
        pass

    last_reinforced = payload.get("last_reinforced_at")
    stale_since = payload.get("stale_since")
    if isinstance(last_reinforced, str) and isinstance(stale_since, str):
        try:
            return sch.parse_dt(last_reinforced) >= sch.parse_dt(stale_since)
        except Exception:
            return False

    return False


def _decide_target_status(object_type: str, action: str, current_status: str, payload: dict) -> tuple[str | None, str]:
    if action == "decay":
        if object_type == "memory":
            if current_status in {"active", "verified"}:
                return "stale", "memory decay: activity timeout"
            return None, f"memory decay noop from status={current_status}"

        if object_type == "experience":
            if current_status == "active":
                return "needs_review", "experience decay: review due"
            return None, f"experience decay noop from status={current_status}"

    if action == "archive":
        if object_type == "memory":
            if current_status in {"stale", "stale_uncertain", "rejected_poisoned"}:
                return "archived", "memory archive: stale/poisoned retention window reached"
            return None, f"memory archive noop from status={current_status}"

        if object_type == "experience":
            if current_status in {"needs_review", "active", "invalidated"}:
                return "archived", "experience archive: no value continuation"
            return None, f"experience archive noop from status={current_status}"

    if action == "reinstate-check":
        has_signal = _has_reinstate_signal(payload)
        if not has_signal:
            return None, f"reinstate-check noop: no new evidence signal (status={current_status})"

        if object_type == "memory":
            if current_status in {"stale", "stale_uncertain"}:
                return "active", "memory reinstate: new evidence signal detected"
            return None, f"memory reinstate-check noop from status={current_status}"

        if object_type == "experience":
            if current_status == "needs_review":
                return "active", "experience reinstate: review signal satisfied"
            return None, f"experience reinstate-check noop from status={current_status}"

    return None, f"unsupported transition for {object_type}:{action}:{current_status}"


def _next_action(action: str, target_status: str | None, now: str, existing_next: str | None) -> str:
    if action == "archive":
        return in_days_iso(30, base=now)
    if action == "reinstate-check" and target_status == "active":
        return in_days_iso(7, base=now)
    if action == "decay":
        return in_days_iso(3, base=now)
    return existing_next or in_days_iso(7, base=now)


def process_temporal_job(c, job: dict, worker_id: str, dry_run: bool = False) -> dict:
    object_type = str(job.get("object_type") or "")
    object_id = str(job.get("object_id") or "")
    action = str(job.get("action") or "")
    job_id = str(job.get("job_id") or "")

    if action not in WORKER_ACTIONS:
        raise ValueError(f"unsupported action for temporal worker: {action}")
    table = OBJECT_TABLES.get(object_type)
    if not table:
        raise ValueError(f"unsupported object_type for temporal worker: {object_type}")

    row = c.execute(f"SELECT status, payload_json FROM {table} WHERE id=?", (object_id,)).fetchone()
    if not row:
        raise ValueError(f"{object_type} object not found: {object_id}")

    current_status = str(row["status"])
    payload = _parse_payload(row["payload_json"])
    now = now_iso()

    target_status, reason = _decide_target_status(object_type, action, current_status, payload)
    transitioned = bool(target_status and target_status != current_status)

    before = {
        "status": current_status,
        "next_action_at": payload.get("next_action_at"),
        "stale_since": payload.get("stale_since"),
    }

    after_payload = dict(payload)
    if transitioned and target_status:
        after_payload["status"] = target_status
        if action == "decay" and object_type == "memory":
            after_payload.setdefault("stale_since", now)
        if action == "reinstate-check" and target_status == "active":
            after_payload["last_reinforced_at"] = now

    next_action_at = _next_action(action, target_status if transitioned else None, now, str(payload.get("next_action_at") or ""))
    if next_action_at:
        after_payload["next_action_at"] = next_action_at

    after_status = target_status if transitioned and target_status else current_status
    after = {
        "status": after_status,
        "next_action_at": after_payload.get("next_action_at"),
        "transitioned": transitioned,
        "action": action,
    }

    if transitioned and not dry_run:
        c.execute(
            f"UPDATE {table} SET status=?, payload_json=?, updated_at=? WHERE id=?",
            (after_status, json.dumps(after_payload, ensure_ascii=False), now_iso(), object_id),
        )

    evidence = _evidence_refs(object_type, payload, object_id=object_id, job_id=job_id)
    sch.write_audit_event(
        c,
        event_type="state_transition",
        actor_type="worker",
        actor_id=worker_id,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        reason=reason,
        evidence_refs=evidence,
        risk_tier=str(payload.get("risk_tier")) if payload.get("risk_tier") in {"low", "medium", "high"} else None,
        job_id=job_id,
        correlation_id=job.get("correlation_id"),
        metadata={
            "action": action,
            "dry_run": dry_run,
            "table": table,
            "worker": "temporal_governance_worker_v0_1",
        },
    )

    return {
        "job_id": job_id,
        "object_type": object_type,
        "object_id": object_id,
        "action": action,
        "from": current_status,
        "to": after_status,
        "transitioned": transitioned,
        "dry_run": dry_run,
        "reason": reason,
    }


def run_loop(args):
    db = Path(args.db).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)

    c = sch.conn(db)
    sch.init_db(c)
    init_me_db(c)

    loops = 0
    processed = 0
    succeeded = 0
    failed = 0
    transitions = 0
    noops = 0

    details: list[dict] = []

    while True:
        loops += 1
        jobs = sch.pull_due(
            c,
            worker_id=args.worker_id,
            now=now_iso(),
            limit=max(1, int(args.pull_limit)),
            lease_sec=max(1, int(args.lease_sec)),
            actions=WORKER_ACTIONS,
        )

        if not jobs and args.run_once:
            break

        if not jobs:
            if args.max_loops and loops >= args.max_loops:
                break
            time.sleep(max(1, int(args.interval_sec)))
            continue

        for job in jobs:
            processed += 1
            job_id = str(job["job_id"])
            lease_token = str(job.get("lease_token") or "")
            try:
                res = process_temporal_job(c, job=job, worker_id=args.worker_id, dry_run=args.dry_run)
                if res.get("transitioned"):
                    transitions += 1
                else:
                    noops += 1
                details.append(res)
                sch.ack(c, job_id, worker_id=args.worker_id, lease_token=lease_token)
                succeeded += 1
            except Exception as e:
                sch.fail(
                    c,
                    job_id,
                    error=str(e),
                    retry_delay_sec=max(1, int(args.retry_delay_sec)),
                    worker_id=args.worker_id,
                    lease_token=lease_token,
                )
                details.append(
                    {
                        "job_id": job_id,
                        "action": str(job.get("action") or ""),
                        "error": str(e),
                        "failed": True,
                    }
                )
                failed += 1

        if args.run_once:
            break
        if args.max_loops and loops >= args.max_loops:
            break
        time.sleep(max(1, int(args.interval_sec)))

    out = {
        "ok": failed == 0,
        "worker_id": args.worker_id,
        "db": str(db),
        "mode": "dry-run" if args.dry_run else "apply",
        "loops": loops,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "transitioned": transitions,
        "noops": noops,
        "details": details,
    }

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(out, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description="Temporal governance worker loop v0.1")
    p.add_argument("--db", default=str(ROOT / "data" / "mindkernel_v0_1.sqlite"), help="scheduler sqlite path")
    p.add_argument("--worker-id", default="temporal-worker-1")
    p.add_argument("--pull-limit", type=int, default=20)
    p.add_argument("--lease-sec", type=int, default=120)
    p.add_argument("--retry-delay-sec", type=int, default=120)
    p.add_argument("--interval-sec", type=int, default=5)
    p.add_argument("--max-loops", type=int, default=0, help="0 means unlimited")
    p.add_argument("--run-once", action="store_true", help="run one pull-process cycle and exit")
    p.add_argument("--dry-run", action="store_true", help="do not persist object state updates")
    p.add_argument("--output", help="optional json output path")
    args = p.parse_args()

    run_loop(args)


if __name__ == "__main__":
    main()
