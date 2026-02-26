#!/usr/bin/env python3
"""Evaluate vector-retrieval readiness for MindKernel v0.1 (R6)."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_recall_baseline(path: Path) -> dict:
    if not path.exists():
        return {"found": False, "accuracy": None, "macro_recall": None, "macro_noise": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"found": False, "accuracy": None, "macro_recall": None, "macro_noise": None}
    return {
        "found": True,
        "accuracy": data.get("accuracy"),
        "macro_recall": data.get("macro_recall"),
        "macro_noise": data.get("macro_noise"),
    }


def load_latest_benchmark(path: Path) -> dict:
    if not path.exists():
        return {"found": False, "throughput_jobs_per_min": None, "lag_p95_sec": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"found": False, "throughput_jobs_per_min": None, "lag_p95_sec": None}
    b = data.get("benchmark", {}) if isinstance(data, dict) else {}
    return {
        "found": True,
        "throughput_jobs_per_min": b.get("throughput_jobs_per_min"),
        "lag_p95_sec": (b.get("lag_seconds") or {}).get("p95") if isinstance(b.get("lag_seconds"), dict) else None,
    }


def count_sqlite_rows(db: Path, table: str) -> int:
    if not db.exists():
        return 0
    try:
        c = sqlite3.connect(str(db))
        row = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        c.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def render_md(report: dict) -> str:
    i = report["inputs"]
    t = report["thresholds"]
    d = report["decision"]

    lines = [
        "# Vector Retrieval Readiness Evaluation (v0.1)",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- decision: **{d['label']}**",
        f"- summary: {d['summary']}",
        "",
        "## Inputs",
        "",
        f"- memory_items_count: {i['memory_items_count']}",
        f"- external_query_volume_per_day: {i['query_volume_per_day']}",
        f"- recall_accuracy: {i['recall_quality'].get('accuracy')}",
        f"- recall_macro_recall: {i['recall_quality'].get('macro_recall')}",
        f"- recall_macro_noise: {i['recall_quality'].get('macro_noise')}",
        "",
        "## Thresholds",
        "",
        f"- min_corpus_for_vector: {t['min_corpus_for_vector']}",
        f"- min_qpd_for_vector: {t['min_qpd_for_vector']}",
        f"- quality_floor_accuracy: {t['quality_floor_accuracy']}",
        f"- quality_floor_recall: {t['quality_floor_recall']}",
        "",
        "## Reasons",
        "",
    ]
    for r in d.get("reasons", []):
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Trigger to revisit")
    lines.append("")
    for x in d.get("revisit_triggers", []):
        lines.append(f"- {x}")
    lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Evaluate vector retrieval readiness")
    p.add_argument("--db", default=str(ROOT / "data" / "mindkernel_v0_1.sqlite"))
    p.add_argument(
        "--recall-baseline",
        default=str(ROOT / "data" / "fixtures" / "recall-quality-v0_1" / "baseline.json"),
    )
    p.add_argument("--benchmark-json", default=str(ROOT / "reports" / "benchmark" / f"scheduler_baseline_{datetime.now(timezone.utc).date().isoformat()}.json"))
    p.add_argument("--query-volume-per-day", type=int, default=50)
    p.add_argument("--min-corpus-for-vector", type=int, default=5000)
    p.add_argument("--min-qpd-for-vector", type=int, default=200)
    p.add_argument("--quality-floor-accuracy", type=float, default=0.90)
    p.add_argument("--quality-floor-recall", type=float, default=0.90)
    p.add_argument("--out-json")
    p.add_argument("--out-md")
    args = p.parse_args()

    db = Path(args.db).expanduser().resolve()
    baseline = load_recall_baseline(Path(args.recall_baseline).expanduser().resolve())
    benchmark = load_latest_benchmark(Path(args.benchmark_json).expanduser().resolve())

    memory_items_count = count_sqlite_rows(db, "memory_items")
    qpd = max(0, int(args.query_volume_per_day))

    acc = baseline.get("accuracy")
    rec = baseline.get("macro_recall")

    quality_gap = False
    if isinstance(acc, (int, float)) and float(acc) < float(args.quality_floor_accuracy):
        quality_gap = True
    if isinstance(rec, (int, float)) and float(rec) < float(args.quality_floor_recall):
        quality_gap = True

    corpus_ready = memory_items_count >= int(args.min_corpus_for_vector)
    traffic_ready = qpd >= int(args.min_qpd_for_vector)

    go_pilot = corpus_ready and (quality_gap or traffic_ready)

    reasons = []
    if not corpus_ready:
        reasons.append(
            f"current corpus {memory_items_count} < threshold {int(args.min_corpus_for_vector)}"
        )
    if not traffic_ready:
        reasons.append(f"query volume {qpd}/day < threshold {int(args.min_qpd_for_vector)}/day")
    if not quality_gap:
        reasons.append("recall baseline currently healthy; no quality-pressure signal")

    if go_pilot:
        label = "GO_PILOT"
        summary = "start vector pilot behind feature flag"
    else:
        label = "NO_GO_KEEP_FTS"
        summary = "keep FTS-only and revisit at scale/quality trigger"

    report = {
        "ok": True,
        "generated_at": now_iso(),
        "inputs": {
            "db_path": str(db),
            "memory_items_count": memory_items_count,
            "query_volume_per_day": qpd,
            "recall_quality": baseline,
            "scheduler_benchmark": benchmark,
        },
        "thresholds": {
            "min_corpus_for_vector": int(args.min_corpus_for_vector),
            "min_qpd_for_vector": int(args.min_qpd_for_vector),
            "quality_floor_accuracy": float(args.quality_floor_accuracy),
            "quality_floor_recall": float(args.quality_floor_recall),
        },
        "decision": {
            "label": label,
            "summary": summary,
            "reasons": reasons,
            "revisit_triggers": [
                f"memory_items >= {int(args.min_corpus_for_vector)}",
                f"query_volume_per_day >= {int(args.min_qpd_for_vector)}",
                "recall accuracy/macro_recall falls below floor for 2 consecutive weekly runs",
            ],
        },
    }

    reports_dir = ROOT / "reports" / "vector"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"vector_readiness_{datetime.now(timezone.utc).date().isoformat()}"
    out_json = Path(args.out_json).expanduser().resolve() if args.out_json else reports_dir / f"{stem}.json"
    out_md = Path(args.out_md).expanduser().resolve() if args.out_md else reports_dir / f"{stem}.md"

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_md(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "generated_at": report["generated_at"],
                "decision": report["decision"]["label"],
                "out_json": str(out_json),
                "out_md": str(out_md),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
