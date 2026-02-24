#!/usr/bin/env python3
"""Agent-first reflect proposal gate (risk routing) for MindKernel v0.1."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

DEFAULT_GATE_CONFIG = {
    "thresholds": {"low_max": 39, "medium_max": 69, "high_min": 70},
    "sampling": {"medium_ratio": 0.20},
    "hard_rules": {
        "always_high_operations": {"delete", "overwrite", "merge_conflict"},
        "always_high_targets": {"core_memory", "persona_trait"},
    },
}


def _to_set(v) -> set[str]:
    if isinstance(v, set):
        return v
    if isinstance(v, (list, tuple)):
        return {str(x) for x in v}
    return set()


def load_gate_config(path: str | None) -> dict:
    cfg = {
        "thresholds": dict(DEFAULT_GATE_CONFIG["thresholds"]),
        "sampling": dict(DEFAULT_GATE_CONFIG["sampling"]),
        "hard_rules": {
            "always_high_operations": set(DEFAULT_GATE_CONFIG["hard_rules"]["always_high_operations"]),
            "always_high_targets": set(DEFAULT_GATE_CONFIG["hard_rules"]["always_high_targets"]),
        },
    }
    if not path:
        return cfg

    user_cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(user_cfg.get("thresholds"), dict):
        cfg["thresholds"].update(user_cfg["thresholds"])
    if isinstance(user_cfg.get("sampling"), dict):
        cfg["sampling"].update(user_cfg["sampling"])
    if isinstance(user_cfg.get("hard_rules"), dict):
        hr = user_cfg["hard_rules"]
        if "always_high_operations" in hr:
            cfg["hard_rules"]["always_high_operations"] = _to_set(hr["always_high_operations"])
        if "always_high_targets" in hr:
            cfg["hard_rules"]["always_high_targets"] = _to_set(hr["always_high_targets"])
    return cfg


def load_proposals(path: str) -> list[dict]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".jsonl":
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
        return out

    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("proposals"), list):
        return data["proposals"]
    raise ValueError('proposals input must be JSON array, {"proposals": [...]}, or JSONL')


def stable_bucket(value: str) -> int:
    h = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return int(h, 16) % 100


def compute_risk_score(proposal: dict, cfg: dict) -> tuple[int, list[str], bool]:
    score = int(round(float(proposal.get("risk_score", 0))))
    reasons: list[str] = []
    forced_high = False

    op = str(proposal.get("operation", "")).strip()
    target_type = str(proposal.get("target_type", "")).strip()

    if proposal.get("contradiction_detected") is True:
        score += 20
        reasons.append("CONTRADICTION_DETECTED")

    evidence_refs = proposal.get("evidence_refs") or []
    if isinstance(evidence_refs, list) and len(evidence_refs) < 2:
        score += 10
        reasons.append("LOW_EVIDENCE")

    try:
        cb = float(proposal.get("confidence_before", 0))
        ca = float(proposal.get("confidence_after", cb))
        if abs(ca - cb) > 0.20:
            score += 10
            reasons.append("CONFIDENCE_JUMP")
    except Exception:
        pass

    if str(proposal.get("source_quality", "")).lower() == "low":
        score += 10
        reasons.append("LOW_SOURCE_QUALITY")

    if proposal.get("exact_duplicate") is True:
        score -= 10
        reasons.append("EXACT_DUPLICATE")

    if op in cfg["hard_rules"]["always_high_operations"]:
        forced_high = True
        reasons.append("HARD_RULE_OPERATION")

    if target_type in cfg["hard_rules"]["always_high_targets"]:
        forced_high = True
        reasons.append("HARD_RULE_TARGET")

    return max(0, min(100, score)), reasons, forced_high


def classify_level(score: int, thresholds: dict, forced_high: bool) -> str:
    if forced_high:
        return "high"

    low_max = int(thresholds.get("low_max", 39))
    medium_max = int(thresholds.get("medium_max", 69))
    high_min = int(thresholds.get("high_min", 70))

    if score <= low_max:
        return "low"
    if score >= high_min:
        return "high"
    if score <= medium_max:
        return "medium"
    return "high"


def route_proposal(proposal: dict, cfg: dict) -> dict:
    score, reason_codes, forced_high = compute_risk_score(proposal, cfg)
    level = classify_level(score, cfg["thresholds"], forced_high)

    medium_ratio = float(cfg["sampling"].get("medium_ratio", 0.20))
    medium_ratio = min(1.0, max(0.0, medium_ratio))

    pid = str(proposal.get("proposal_id") or proposal.get("id") or uuid.uuid4().hex)
    jid = str(proposal.get("job_id") or "")
    bucket = stable_bucket(f"{jid}:{pid}")

    if level == "low":
        policy_decision = "auto_apply"
        decision = "auto_applied"
    elif level == "high":
        policy_decision = "mandatory_review"
        decision = "pending_review"
    else:
        sampled = bucket < int(medium_ratio * 100)
        policy_decision = "sample_review" if sampled else "auto_apply"
        decision = "pending_review" if sampled else "auto_applied"
        reason_codes.append("MEDIUM_SAMPLED" if sampled else "MEDIUM_AUTO_APPLY")

    out = dict(proposal)
    out["risk_score"] = score
    out["risk_level"] = level
    out["policy_decision"] = policy_decision
    out["decision"] = decision
    out["reason_codes"] = sorted(set(reason_codes))
    out["retryable"] = bool(out.get("retryable", False))
    return out


def route_proposals(input_path: str, config_path: str | None = None, output_path: str | None = None) -> dict:
    cfg = load_gate_config(config_path)
    proposals = load_proposals(input_path)
    routed = [route_proposal(p, cfg) for p in proposals]

    counts = {
        "total": len(routed),
        "auto_applied": sum(1 for x in routed if x["decision"] == "auto_applied"),
        "pending_review": sum(1 for x in routed if x["decision"] == "pending_review"),
        "quarantined": sum(1 for x in routed if x["decision"] == "quarantined"),
    }
    by_level = {
        "low": sum(1 for x in routed if x["risk_level"] == "low"),
        "medium": sum(1 for x in routed if x["risk_level"] == "medium"),
        "high": sum(1 for x in routed if x["risk_level"] == "high"),
    }

    result = {
        "ok": True,
        "decision": "success" if counts["pending_review"] == 0 else "partial_success",
        "counts": counts,
        "by_risk_level": by_level,
        "proposals": routed,
    }

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["output"] = str(Path(output_path).resolve())

    return result
