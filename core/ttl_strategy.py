"""
TTL 遗忘策略 — 定时清理低价值记忆，防止存储无限膨胀。
V1 简单版：按访问频率 + 时间衰减计算 score，低于阈值则淘汰。

Score 算法：
  - grace_period_days（默认7天）内的新记忆不受淘汰
  - score = recency_score * frequency_score
  - recency_score = max(0, 1 - age_days/max_age_days)
  - frequency_score = min(access_count/10, 1.0)
  - 低于 prune_threshold（默认0.15）进入淘汰
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn

CONFIG_PATH = ROOT / ".mindkernel" / "config" / "ttl_policy.json"
DEFAULT_CONFIG = {
    "enabled": True,
    "max_age_days": 90,
    "min_access_count": 2,
    "decay_factor": 0.95,
    "prune_threshold": 0.15,
    "prune_interval_hours": 24,
    "grace_period_days": 7,  # 新记忆 7 天内不淘汰
    "dry_run": True,  # 默认干跑，不实际删除
}


def load_config() -> dict:
    path = CONFIG_PATH.expanduser()
    if path.exists():
        cfg = json.loads(path.read_text())
        return {**DEFAULT_CONFIG, **cfg}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG


def _parse_ts(val: str) -> datetime:
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


def compute_score(
    created_at: str,
    access_count: int,
    config: dict,
) -> float:
    """计算一条记忆的 TTL score，0.0~1.0，越高越值得保留。"""
    now = datetime.now(timezone.utc)
    created = _parse_ts(created_at)
    age_days = (now - created).days

    # grace period 内不受淘汰
    if age_days < config["grace_period_days"]:
        return 1.0

    # 超过 max_age_days 直接淘汰
    if age_days > config["max_age_days"]:
        return 0.0

    # 频率分数：访问越多越值得保留，最多 10 次封顶
    frequency_score = min(access_count / 10.0, 1.0)

    # 时间衰减：越老分数越低
    recency_score = max(0.0, 1.0 - (age_days / config["max_age_days"]))

    return recency_score * frequency_score


def should_prune(score: float, threshold: float) -> bool:
    return score < threshold


def get_memory_records(c) -> list[dict]:
    """拉取所有 candidate 状态的记忆记录。"""
    rows = c.execute(
        "SELECT id, status, payload_json, created_at FROM memory_items WHERE status = 'candidate'"
    ).fetchall()
    result = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            result.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "access_count": payload.get("metadata", {}).get("access_count", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return result


def get_experience_records(c) -> list[dict]:
    """拉取所有 active 状态的 experience 记录。"""
    rows = c.execute(
        "SELECT id, status, payload_json, created_at FROM experience_records WHERE status = 'active'"
    ).fetchall()
    result = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
            result.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "access_count": payload.get("metadata", {}).get("access_count", 0),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return result


def run_prune(dry_run: bool | None = None) -> dict:
    """
    执行 TTL 淘汰检查。
    返回 {candidates_pruned, experiences_pruned, details}
    """
    config = load_config()
    if dry_run is None:
        dry_run = config["dry_run"]

    db_path = ROOT / "data" / "mindkernel_v0_1.sqlite"
    c = conn(db_path)

    candidates_pruned = []
    experiences_pruned = []
    candidates_kept = 0
    experiences_kept = 0

    for rec in get_memory_records(c):
        score = compute_score(rec["created_at"], rec.get("access_count", 0), config)
        if should_prune(score, config["prune_threshold"]):
            candidates_pruned.append({
                "id": rec["id"],
                "score": round(score, 3),
                "created_at": rec["created_at"],
                "dry_run": dry_run,
            })
        else:
            candidates_kept += 1

    for rec in get_experience_records(c):
        score = compute_score(rec["created_at"], rec.get("access_count", 0), config)
        if should_prune(score, config["prune_threshold"]):
            if dry_run:
                experiences_pruned.append({
                    "id": rec["id"],
                    "score": round(score, 3),
                    "dry_run": True,
                })
            else:
                c.execute(
                    "UPDATE experience_records SET status = 'archived' WHERE id = ?",
                    (rec["id"],)
                )
                experiences_pruned.append({
                    "id": rec["id"],
                    "score": round(score, 3),
                    "dry_run": False,
                })
        else:
            experiences_kept += 1

    if not dry_run:
        c.commit()
    c.close()

    return {
        "candidates_pruned": candidates_pruned,
        "candidates_kept": candidates_kept,
        "experiences_pruned": experiences_pruned,
        "experiences_kept": experiences_kept,
        "dry_run": dry_run,
        "config": {k: v for k, v in config.items() if k != "dry_run"},
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MindKernel TTL Prune")
    parser.add_argument("--apply", action="store_true", help="实际执行删除（默认 dry_run）")
    args = parser.parse_args()

    result = run_prune(dry_run=not args.apply)
    print(json.dumps(result, indent=2, ensure_ascii=False))
