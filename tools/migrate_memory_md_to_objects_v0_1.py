#!/usr/bin/env python3
"""Dry-run migration: memory.md -> memory objects (v0.1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT

BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")
NUMBERED_RE = re.compile(r"^\s*\d+[\.)]\s+(.+)$")
HEADING_RE = re.compile(r"^\s*#{1,6}\s+(.+)$")

SENSITIVE_KEYWORDS = {
    "high": [
        "身份证", "护照", "银行卡", "信用卡", "cvv", "social security", "ssn", "password", "密码", "private key", "seed phrase",
    ],
    "medium": [
        "邮箱", "email", "phone", "电话", "手机号", "address", "住址", "wechat", "微信", "slack", "discord",
    ],
    "low": [],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def classify_sensitivity(text: str) -> tuple[str, list[str]]:
    t = text.lower()
    matched_high = [k for k in SENSITIVE_KEYWORDS["high"] if k.lower() in t]
    if matched_high:
        return "high", matched_high

    matched_mid = [k for k in SENSITIVE_KEYWORDS["medium"] if k.lower() in t]
    if matched_mid:
        return "medium", matched_mid

    return "low", []


def parse_memory_md(path: Path, rel_path: str):
    lines = path.read_text(errors="ignore").splitlines()
    section = "root"
    records = []

    for i, line in enumerate(lines, start=1):
        h = HEADING_RE.match(line)
        if h:
            section = h.group(1).strip()
            continue

        content = None
        m = BULLET_RE.match(line)
        if m:
            content = m.group(1).strip()
        else:
            n = NUMBERED_RE.match(line)
            if n:
                content = n.group(1).strip()
            elif line.strip() and not line.strip().startswith("---"):
                # keep non-empty plain lines as candidates too
                content = line.strip()

        if not content:
            continue

        sensitivity, markers = classify_sensitivity(content)
        source_ref = f"{rel_path}#L{i}"
        rid = f"mem_mig_{hashlib.sha1(source_ref.encode('utf-8')).hexdigest()[:12]}"

        records.append(
            {
                "id": rid,
                "kind": "fact",
                "content": content,
                "source": {"source_type": "file", "source_ref": source_ref},
                "evidence_refs": [source_ref],
                "confidence": 0.6,
                "risk_tier": "low" if sensitivity == "low" else "medium",
                "impact_tier": "medium" if sensitivity == "low" else "high",
                "status": "candidate",
                "created_at": now_iso(),
                "review_due_at": (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "next_action_at": (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "migration_meta": {
                    "section": section,
                    "line_no": i,
                    "sensitivity": sensitivity,
                    "sensitivity_markers": markers,
                },
            }
        )

    return records


def main():
    p = argparse.ArgumentParser(description="Dry-run migrate memory.md into memory objects")
    p.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="workspace root")
    p.add_argument("--input", default="memory.md", help="input markdown path relative to workspace")
    p.add_argument("--out", default="reports/memory_md_migration_dryrun_v0_1.json", help="report path relative to workspace")
    args = p.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    in_path = (workspace / args.input).resolve()
    out_path = (workspace / args.out).resolve()

    if not in_path.exists():
        raise SystemExit(f"input not found: {in_path}")

    rel_input = str(in_path.relative_to(workspace))
    objects = parse_memory_md(in_path, rel_input)

    high = sum(1 for x in objects if x["migration_meta"]["sensitivity"] == "high")
    medium = sum(1 for x in objects if x["migration_meta"]["sensitivity"] == "medium")
    low = sum(1 for x in objects if x["migration_meta"]["sensitivity"] == "low")

    report = {
        "ok": True,
        "mode": "dry-run",
        "generated_at": now_iso(),
        "input": rel_input,
        "summary": {
            "total_candidates": len(objects),
            "sensitivity": {"high": high, "medium": medium, "low": low},
        },
        "objects_preview": objects,
        "notes": [
            "No DB writes performed.",
            "No source files changed.",
            "Review sensitivity=high items manually before any real migration.",
        ],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"ok": True, "mode": "dry-run", "output": str(out_path), "total_candidates": len(objects)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
