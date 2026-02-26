#!/usr/bin/env python3
"""Generate weekly governance report for MindKernel v0.1."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except Exception:
        return None


def pct(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return round((n / d) * 100, 2)


def safe_div(n: float, d: float) -> float:
    if d <= 0:
        return 0.0
    return n / d


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    arr = sorted(float(v) for v in vals)
    if len(arr) == 1:
        return arr[0]
    rank = (len(arr) - 1) * (p / 100.0)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return arr[lo]
    f = rank - lo
    return arr[lo] * (1 - f) + arr[hi] * f


def table_exists(c: sqlite3.Connection, name: str) -> bool:
    row = c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


@dataclass
class Window:
    start: datetime
    end: datetime

    @property
    def start_iso(self) -> str:
        return iso(self.start)

    @property
    def end_iso(self) -> str:
        return iso(self.end)


def collect_scheduler(c: sqlite3.Connection, w: Window) -> dict:
    if not table_exists(c, "scheduler_jobs"):
        return {
            "window_jobs": 0,
            "status_counts": {},
            "action_counts": {},
            "success_rate": 0.0,
            "retry_rate": 0.0,
            "dead_letter_rate": 0.0,
            "avg_attempt": 0.0,
            "max_attempt": 0,
            "current_backlog": {"queued": 0, "running": 0, "dead_letter": 0},
            "due_lag_seconds": {"count": 0, "p50": 0.0, "p95": 0.0, "max": 0.0},
            "reflect_success_count": 0,
        }

    rows = c.execute(
        """
        SELECT status, action, attempt, run_at, created_at
        FROM scheduler_jobs
        WHERE created_at >= ? AND created_at <= ?
        """,
        (w.start_iso, w.end_iso),
    ).fetchall()

    status_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    attempts: list[int] = []
    retry_jobs = 0
    dead_letter = 0
    succeeded = 0
    completed = 0
    reflect_success = 0

    for r in rows:
        status = str(r["status"])
        action = str(r["action"])
        attempt = int(r["attempt"] or 0)

        status_counts[status] = status_counts.get(status, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
        attempts.append(attempt)

        if attempt > 0:
            retry_jobs += 1
        if status == "dead_letter":
            dead_letter += 1
        if status == "succeeded":
            succeeded += 1
        if status in {"succeeded", "failed", "dead_letter", "partial_success"}:
            completed += 1
        if status == "succeeded" and action == "reflect":
            reflect_success += 1

    now = now_utc()
    queued_rows = c.execute("SELECT run_at FROM scheduler_jobs WHERE status='queued'").fetchall()
    lags = []
    for q in queued_rows:
        dt = parse_iso(q["run_at"])
        if not dt:
            continue
        lag = (now - dt).total_seconds()
        if lag > 0:
            lags.append(lag)

    backlog = {
        "queued": int(c.execute("SELECT COUNT(*) FROM scheduler_jobs WHERE status='queued'").fetchone()[0]),
        "running": int(c.execute("SELECT COUNT(*) FROM scheduler_jobs WHERE status='running'").fetchone()[0]),
        "dead_letter": int(
            c.execute("SELECT COUNT(*) FROM scheduler_jobs WHERE status='dead_letter'").fetchone()[0]
        ),
    }

    return {
        "window_jobs": len(rows),
        "status_counts": status_counts,
        "action_counts": action_counts,
        "success_rate": round(pct(succeeded, completed), 2),
        "retry_rate": round(pct(retry_jobs, len(rows)), 2),
        "dead_letter_rate": round(pct(dead_letter, len(rows)), 2),
        "avg_attempt": round(safe_div(sum(attempts), len(attempts)), 3) if attempts else 0.0,
        "max_attempt": max(attempts) if attempts else 0,
        "current_backlog": backlog,
        "due_lag_seconds": {
            "count": len(lags),
            "p50": round(percentile(lags, 50), 3),
            "p95": round(percentile(lags, 95), 3),
            "max": round(max(lags), 3) if lags else 0.0,
        },
        "reflect_success_count": reflect_success,
    }


def collect_audit(c: sqlite3.Connection, w: Window) -> dict:
    if not table_exists(c, "audit_events"):
        return {
            "window_events": 0,
            "event_type_counts": {},
            "rollback_count": 0,
            "decision_gate_count": 0,
            "blocked_count": 0,
            "escalated_count": 0,
            "state_transition_count": 0,
            "activation_count": 0,
            "archive_count": 0,
            "learning_yield_proxy": 0,
            "escalation_rate": 0.0,
            "blocked_rate": 0.0,
        }

    rows = c.execute(
        "SELECT payload_json FROM audit_events WHERE timestamp >= ? AND timestamp <= ?",
        (w.start_iso, w.end_iso),
    ).fetchall()

    event_type_counts: dict[str, int] = {}
    rollback_count = 0
    decision_gate_count = 0
    blocked_count = 0
    escalated_count = 0
    state_transition_count = 0
    activation_count = 0
    archive_count = 0

    for r in rows:
        try:
            payload = json.loads(r["payload_json"])
        except Exception:
            continue

        et = str(payload.get("event_type") or "unknown")
        event_type_counts[et] = event_type_counts.get(et, 0) + 1

        if et == "rollback":
            rollback_count += 1
        if et == "decision_gate":
            decision_gate_count += 1

        after = payload.get("after") if isinstance(payload.get("after"), dict) else {}
        outcome = str(after.get("final_outcome") or "").lower()
        gate = str(after.get("persona_conflict_gate") or "").lower()

        if outcome == "blocked" or gate == "block":
            blocked_count += 1
        if outcome == "escalated":
            escalated_count += 1

        if et == "state_transition":
            state_transition_count += 1
            before = payload.get("before") if isinstance(payload.get("before"), dict) else {}
            b_status = str(before.get("status") or "")
            a_status = str(after.get("status") or "")
            if a_status == "active" and b_status != "active":
                activation_count += 1
            if a_status == "archived":
                archive_count += 1

    learning_yield_proxy = activation_count

    return {
        "window_events": len(rows),
        "event_type_counts": event_type_counts,
        "rollback_count": rollback_count,
        "decision_gate_count": decision_gate_count,
        "blocked_count": blocked_count,
        "escalated_count": escalated_count,
        "state_transition_count": state_transition_count,
        "activation_count": activation_count,
        "archive_count": archive_count,
        "learning_yield_proxy": learning_yield_proxy,
        "escalation_rate": round(pct(escalated_count, decision_gate_count), 2),
        "blocked_rate": round(pct(blocked_count, max(1, decision_gate_count)), 2) if decision_gate_count else 0.0,
    }


def load_release_gate(path: Path) -> dict:
    if not path.exists():
        return {
            "found": False,
            "ok": None,
            "passed": 0,
            "total": 0,
            "generated_at": None,
            "release_target": None,
        }

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "found": False,
            "ok": None,
            "passed": 0,
            "total": 0,
            "generated_at": None,
            "release_target": None,
        }

    return {
        "found": True,
        "ok": bool(obj.get("ok")),
        "passed": int(obj.get("passed") or 0),
        "total": int(obj.get("total") or 0),
        "generated_at": obj.get("generated_at"),
        "release_target": obj.get("release_target"),
    }


def load_previous_report(reports_dir: Path, current_name: str) -> dict | None:
    files = sorted(p for p in reports_dir.glob("weekly_governance_*.json") if p.name != current_name)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_trend(cur: dict, prev: dict | None) -> dict:
    if not prev:
        return {"has_previous": False, "deltas": {}}

    def g(obj: dict, path: list[str], default=0.0):
        x = obj
        for k in path:
            if not isinstance(x, dict) or k not in x:
                return default
            x = x[k]
        return x

    deltas = {
        "scheduler_window_jobs": int(g(cur, ["scheduler", "window_jobs"], 0))
        - int(g(prev, ["scheduler", "window_jobs"], 0)),
        "success_rate": round(
            float(g(cur, ["scheduler", "success_rate"], 0.0))
            - float(g(prev, ["scheduler", "success_rate"], 0.0)),
            2,
        ),
        "retry_rate": round(
            float(g(cur, ["scheduler", "retry_rate"], 0.0))
            - float(g(prev, ["scheduler", "retry_rate"], 0.0)),
            2,
        ),
        "dead_letter_rate": round(
            float(g(cur, ["scheduler", "dead_letter_rate"], 0.0))
            - float(g(prev, ["scheduler", "dead_letter_rate"], 0.0)),
            2,
        ),
        "learning_yield_proxy": int(g(cur, ["audit", "learning_yield_proxy"], 0))
        - int(g(prev, ["audit", "learning_yield_proxy"], 0)),
    }

    return {
        "has_previous": True,
        "previous_generated_at": prev.get("generated_at"),
        "deltas": deltas,
    }


def build_risk_signals(report: dict) -> list[dict]:
    scheduler = report["scheduler"]
    release_gate = report["release_gate"]
    signals: list[dict] = []

    if release_gate.get("found") and not release_gate.get("ok"):
        signals.append(
            {
                "level": "high",
                "key": "release_gate",
                "message": f"release check not fully green ({release_gate.get('passed')}/{release_gate.get('total')})",
            }
        )

    if float(scheduler.get("dead_letter_rate", 0.0)) > 0.0:
        signals.append(
            {
                "level": "medium",
                "key": "dead_letter_rate",
                "message": f"dead letter rate is {scheduler.get('dead_letter_rate')}%",
            }
        )

    if float(scheduler.get("retry_rate", 0.0)) > 20.0:
        signals.append(
            {
                "level": "medium",
                "key": "retry_rate",
                "message": f"retry rate is elevated at {scheduler.get('retry_rate')}%",
            }
        )

    lag_p95 = float(scheduler.get("due_lag_seconds", {}).get("p95", 0.0))
    if lag_p95 > 300:
        signals.append(
            {
                "level": "medium",
                "key": "queue_lag",
                "message": f"queued due lag p95 is {round(lag_p95, 2)}s",
            }
        )

    if not signals:
        signals.append(
            {
                "level": "low",
                "key": "status",
                "message": "no critical governance risk found in current window",
            }
        )

    return signals


def build_recommendations(report: dict) -> list[str]:
    recs: list[str] = []
    scheduler = report["scheduler"]
    release_gate = report["release_gate"]

    if not release_gate.get("found"):
        recs.append("补充 release_check 报告路径，确保周报可绑定最新发布门禁结果。")

    if int(scheduler.get("current_backlog", {}).get("running", 0)) > 0:
        recs.append("检查 running 作业是否存在长任务，优先接入 lease renew/heartbeat。")

    if float(scheduler.get("retry_rate", 0.0)) > 10:
        recs.append("重试率偏高，建议审查失败分类并补充幂等/超时策略。")

    if int(report.get("audit", {}).get("learning_yield_proxy", 0)) == 0:
        recs.append("本周 learning_yield_proxy 为 0，可增加 reflect/temporal 有效迁移样本。")

    if not recs:
        recs.append("治理指标整体平稳，建议保持当前门禁并继续累计趋势数据。")

    return recs


def render_markdown(report: dict) -> str:
    w = report["window"]
    s = report["scheduler"]
    a = report["audit"]
    r = report["release_gate"]
    t = report["trend"]

    lines = []
    lines.append("# Weekly Governance Report (v0.1)")
    lines.append("")
    lines.append(f"- generated_at: {report['generated_at']}")
    lines.append(f"- window: {w['start']} ~ {w['end']}")
    lines.append(f"- db: `{report['db_path']}`")
    lines.append("")

    lines.append("## Scheduler")
    lines.append("")
    lines.append(f"- window_jobs: **{s['window_jobs']}**")
    lines.append(f"- success_rate: **{s['success_rate']}%**")
    lines.append(f"- retry_rate: **{s['retry_rate']}%**")
    lines.append(f"- dead_letter_rate: **{s['dead_letter_rate']}%**")
    lines.append(
        f"- backlog: queued={s['current_backlog']['queued']}, running={s['current_backlog']['running']}, dead_letter={s['current_backlog']['dead_letter']}"
    )
    lines.append(
        f"- due_lag_seconds(p95/max): {s['due_lag_seconds']['p95']} / {s['due_lag_seconds']['max']}"
    )
    lines.append("")

    lines.append("## Audit")
    lines.append("")
    lines.append(f"- window_events: **{a['window_events']}**")
    lines.append(f"- state_transition_count: {a['state_transition_count']}")
    lines.append(f"- rollback_count: {a['rollback_count']}")
    lines.append(f"- blocked_count: {a['blocked_count']}")
    lines.append(f"- escalated_count: {a['escalated_count']}")
    lines.append(f"- learning_yield_proxy: **{a['learning_yield_proxy']}**")
    lines.append("")

    lines.append("## Release Gate")
    lines.append("")
    if r.get("found"):
        lines.append(
            f"- release_target: `{r.get('release_target')}` / checks: **{r.get('passed')}/{r.get('total')}** / ok={r.get('ok')}"
        )
        lines.append(f"- report_generated_at: {r.get('generated_at')}")
    else:
        lines.append("- release check report not found")
    lines.append("")

    lines.append("## Trend")
    lines.append("")
    if t.get("has_previous"):
        lines.append(f"- previous_generated_at: {t.get('previous_generated_at')}")
        for k, v in t.get("deltas", {}).items():
            lines.append(f"- delta.{k}: {v}")
    else:
        lines.append("- no previous report for delta comparison")
    lines.append("")

    lines.append("## Risk Signals")
    lines.append("")
    for sig in report.get("risk_signals", []):
        lines.append(f"- [{sig['level']}] {sig['key']}: {sig['message']}")
    lines.append("")

    lines.append("## Recommended Next Actions")
    lines.append("")
    for i, item in enumerate(report.get("recommendations", []), start=1):
        lines.append(f"{i}. {item}")

    lines.append("")
    return "\n".join(lines)


def default_output_paths(now: datetime, reports_dir: Path) -> tuple[Path, Path]:
    name = f"weekly_governance_{now.date().isoformat()}"
    return reports_dir / f"{name}.json", reports_dir / f"{name}.md"


def main():
    p = argparse.ArgumentParser(description="Generate weekly governance report for MindKernel v0.1")
    p.add_argument("--db", default=str(ROOT / "data" / "mindkernel_v0_1.sqlite"))
    p.add_argument("--since-days", type=int, default=7)
    p.add_argument("--release-check-json", default=str(ROOT / "reports" / "release_check_v0_1.json"))
    p.add_argument("--reports-dir", default=str(ROOT / "reports" / "governance"))
    p.add_argument("--out-json", help="optional explicit output json path")
    p.add_argument("--out-md", help="optional explicit output markdown path")
    args = p.parse_args()

    end = now_utc()
    start = end - timedelta(days=max(1, int(args.since_days)))
    w = Window(start=start, end=end)

    db_path = Path(args.db).expanduser().resolve()
    reports_dir = Path(args.reports_dir).expanduser().resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    out_json = Path(args.out_json).expanduser().resolve() if args.out_json else None
    out_md = Path(args.out_md).expanduser().resolve() if args.out_md else None
    if not out_json or not out_md:
        d_json, d_md = default_output_paths(end, reports_dir)
        out_json = out_json or d_json
        out_md = out_md or d_md

    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row

    report = {
        "generated_at": iso(end),
        "window": {"start": w.start_iso, "end": w.end_iso, "since_days": int(args.since_days)},
        "db_path": str(db_path),
        "scheduler": collect_scheduler(c, w),
        "audit": collect_audit(c, w),
        "release_gate": load_release_gate(Path(args.release_check_json).expanduser().resolve()),
    }
    c.close()

    prev = load_previous_report(reports_dir, current_name=out_json.name)
    report["trend"] = compute_trend(report, prev)

    # learning_yield_proxy includes reflect success as additive signal
    report["audit"]["learning_yield_proxy"] = int(report["audit"].get("learning_yield_proxy", 0)) + int(
        report["scheduler"].get("reflect_success_count", 0)
    )

    report["risk_signals"] = build_risk_signals(report)
    report["recommendations"] = build_recommendations(report)

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "generated_at": report["generated_at"],
                "window": report["window"],
                "out_json": str(out_json),
                "out_md": str(out_md),
                "scheduler_window_jobs": report["scheduler"]["window_jobs"],
                "release_gate": {
                    "found": report["release_gate"]["found"],
                    "ok": report["release_gate"]["ok"],
                    "passed": report["release_gate"]["passed"],
                    "total": report["release_gate"]["total"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
