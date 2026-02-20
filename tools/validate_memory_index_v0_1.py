#!/usr/bin/env python3
"""Validation script for memory_index_v0_1 opinion evolution + writeback."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "memory-workspace-evolution"
TOOL = ROOT / "tools" / "memory_index_v0_1.py"


def run(cmd: str):
    import subprocess

    p = subprocess.run(cmd, shell=True, text=True, capture_output=True, cwd=str(ROOT))
    if p.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")
    return p.stdout


def fetch_one(db_path: Path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM opinions_state LIMIT 1").fetchone()
    if not row:
        raise AssertionError("opinions_state should have at least one row")
    return row


def main():
    if not FIXTURE.exists():
        raise SystemExit(f"fixture not found: {FIXTURE}")

    tmp = Path(tempfile.mkdtemp(prefix="mk-mi-v01-"))
    ws = tmp / "workspace"
    shutil.copytree(FIXTURE, ws)
    db = tmp / "index.sqlite"

    run(f"python3 {TOOL} --workspace {ws} --db {db} init-db")
    run(f"python3 {TOOL} --workspace {ws} --db {db} reindex")
    run(f"python3 {TOOL} --workspace {ws} --db {db} reflect --writeback")

    row = fetch_one(db)
    support = int(row["support_count"])
    contradict = int(row["contradict_count"])
    conf = float(row["confidence"])

    assert support >= 1, "support_count should be >= 1"
    assert contradict >= 1, "contradict_count should be >= 1"
    assert 0.05 <= conf <= 0.99, "confidence out of bounds"

    opinions_md = ws / "bank" / "opinions.md"
    assert opinions_md.exists(), "bank/opinions.md should be written"
    txt = opinions_md.read_text()
    assert "AUTO-GENERATED:REFLECT" in txt, "opinions.md should contain autogen block"

    entities_dir = ws / "bank" / "entities"
    assert entities_dir.exists(), "entities dir should exist"
    assert any(entities_dir.glob("*.md")), "at least one entity page should be generated"

    out = {
        "ok": True,
        "workspace": str(ws),
        "db": str(db),
        "support_count": support,
        "contradict_count": contradict,
        "confidence": conf,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
