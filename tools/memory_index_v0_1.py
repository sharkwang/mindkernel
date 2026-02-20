#!/usr/bin/env python3
"""MindKernel memory index prototype v0.1 (retain/recall/reflect)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE = ROOT
DEFAULT_DB = ROOT / ".memory" / "index.sqlite"

RETAIN_HEADER_RE = re.compile(r"^##\s+Retain\b", re.IGNORECASE)
HEADER_RE = re.compile(r"^##\s+")
# - O(c=0.95) @Peter @warelay: content
RETAIN_LINE_RE = re.compile(
    r"^\s*[-*]\s*(?P<kind>[WBOS])(?:\(c=(?P<conf>0(?:\.\d+)?|1(?:\.0+)?)\))?\s*(?P<entities>(?:@[^:\s]+\s*)*):\s*(?P<content>.+)$"
)
DATE_IN_PATH_RE = re.compile(r"memory/(\d{4}-\d{2}-\d{2})\.md$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    return c


def init_db(c: sqlite3.Connection):
    c.executescript(
        """
        PRAGMA journal_mode=WAL;

        CREATE TABLE IF NOT EXISTS documents (
            path TEXT PRIMARY KEY,
            sha1 TEXT NOT NULL,
            mtime REAL NOT NULL,
            indexed_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS facts (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            entities TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_path TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            source_ref TEXT NOT NULL,
            observed_date TEXT,
            indexed_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            fact_id UNINDEXED,
            content,
            entities,
            kind
        );

        CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);
        CREATE INDEX IF NOT EXISTS idx_facts_observed_date ON facts(observed_date);
        """
    )
    c.commit()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def iter_md_files(workspace: Path):
    # canonical sources
    candidates = []
    for p in [workspace / "memory.md"]:
        if p.exists() and p.is_file():
            candidates.append(p)

    for base in [workspace / "memory", workspace / "bank"]:
        if base.exists():
            candidates.extend(sorted(base.rglob("*.md")))

    seen = set()
    for p in candidates:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        yield p


def extract_observed_date(rel_path: str) -> str | None:
    m = DATE_IN_PATH_RE.search(rel_path.replace("\\", "/"))
    return m.group(1) if m else None


def parse_retain_facts(md_text: str, rel_path: str):
    lines = md_text.splitlines()
    in_retain = False
    out = []

    for i, line in enumerate(lines, start=1):
        if RETAIN_HEADER_RE.match(line.strip()):
            in_retain = True
            continue

        if in_retain and HEADER_RE.match(line.strip()):
            in_retain = False
            continue

        if not in_retain:
            continue

        m = RETAIN_LINE_RE.match(line)
        if not m:
            continue

        kind = m.group("kind")
        conf = float(m.group("conf") or 0.7)
        content = m.group("content").strip()
        entities_raw = m.group("entities") or ""
        entities = [e.strip()[1:] for e in entities_raw.split() if e.strip().startswith("@")]

        out.append(
            {
                "kind": kind,
                "confidence": conf,
                "content": content,
                "entities": entities,
                "line_no": i,
                "source_ref": f"{rel_path}#L{i}",
                "observed_date": extract_observed_date(rel_path),
            }
        )

    return out


def upsert_document_and_facts(c: sqlite3.Connection, workspace: Path, path: Path):
    text = path.read_text(errors="ignore")
    rel_path = str(path.relative_to(workspace))
    st = path.stat()
    sha = sha1_text(text)

    indexed_at = now_iso()
    c.execute(
        "INSERT INTO documents(path, sha1, mtime, indexed_at) VALUES (?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET sha1=excluded.sha1, mtime=excluded.mtime, indexed_at=excluded.indexed_at",
        (rel_path, sha, st.st_mtime, indexed_at),
    )

    # replace facts for this doc
    fact_rows = c.execute("SELECT id FROM facts WHERE source_path=?", (rel_path,)).fetchall()
    for r in fact_rows:
        c.execute("DELETE FROM facts_fts WHERE fact_id=?", (r["id"],))
    c.execute("DELETE FROM facts WHERE source_path=?", (rel_path,))

    facts = parse_retain_facts(text, rel_path)
    for f in facts:
        fid = f"fact_{sha1_text(f['source_ref'] + '|' + f['content'])[:16]}"
        entities_str = " ".join(f["entities"])
        c.execute(
            "INSERT INTO facts(id, kind, content, entities, confidence, source_path, line_no, source_ref, observed_date, indexed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fid,
                f["kind"],
                f["content"],
                entities_str,
                f["confidence"],
                rel_path,
                f["line_no"],
                f["source_ref"],
                f["observed_date"],
                indexed_at,
            ),
        )
        c.execute(
            "INSERT INTO facts_fts(fact_id, content, entities, kind) VALUES (?, ?, ?, ?)",
            (fid, f["content"], entities_str, f["kind"]),
        )

    return {"path": rel_path, "facts_indexed": len(facts)}


def cmd_reindex(c: sqlite3.Connection, workspace: Path):
    init_db(c)
    stats = {"docs": 0, "facts": 0, "items": []}
    for p in iter_md_files(workspace):
        r = upsert_document_and_facts(c, workspace, p)
        stats["docs"] += 1
        stats["facts"] += r["facts_indexed"]
        stats["items"].append(r)
    c.commit()
    return stats


def cmd_recall(c: sqlite3.Connection, query: str | None, kind: str | None, entity: str | None, since_days: int | None, limit: int):
    params = []
    where = []

    if since_days is not None:
        day = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
        where.append("(observed_date IS NULL OR observed_date >= ?)")
        params.append(day)

    if kind:
        where.append("kind = ?")
        params.append(kind)

    if entity:
        where.append("entities LIKE ?")
        params.append(f"%{entity}%")

    if query:
        sql = """
        SELECT f.* FROM facts_fts x
        JOIN facts f ON f.id = x.fact_id
        """
        where2 = where + ["facts_fts MATCH ?"]
        params2 = params + [query]
        if where2:
            sql += " WHERE " + " AND ".join(where2)
        sql += " ORDER BY f.observed_date DESC, f.indexed_at DESC LIMIT ?"
        params2.append(limit)
        rows = c.execute(sql, params2).fetchall()
    else:
        sql = "SELECT * FROM facts"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY observed_date DESC, indexed_at DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(sql, params).fetchall()

    facts = []
    for r in rows:
        facts.append(
            {
                "id": r["id"],
                "kind": r["kind"],
                "content": r["content"],
                "entities": [x for x in (r["entities"] or "").split() if x],
                "confidence": r["confidence"],
                "source_ref": r["source_ref"],
                "observed_date": r["observed_date"],
            }
        )
    return {"facts": facts, "count": len(facts)}


def cmd_reflect(c: sqlite3.Connection, since_days: int | None):
    params = []
    where = []
    if since_days is not None:
        day = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
        where.append("(observed_date IS NULL OR observed_date >= ?)")
        params.append(day)

    sql = "SELECT kind, entities, confidence, content, source_ref FROM facts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    rows = c.execute(sql, params).fetchall()

    entity_map: dict[str, list[dict]] = {}
    opinion_candidates = []

    for r in rows:
        entities = [e for e in (r["entities"] or "").split() if e]
        for e in entities:
            entity_map.setdefault(e, []).append(
                {
                    "kind": r["kind"],
                    "content": r["content"],
                    "source_ref": r["source_ref"],
                    "confidence": r["confidence"],
                }
            )
        if r["kind"] == "O":
            opinion_candidates.append(
                {
                    "entities": entities,
                    "content": r["content"],
                    "confidence": r["confidence"],
                    "source_ref": r["source_ref"],
                }
            )

    entity_summaries = []
    for e, items in sorted(entity_map.items()):
        entity_summaries.append(
            {
                "entity": e,
                "fact_count": len(items),
                "top_facts": items[:5],
            }
        )

    return {
        "entity_summaries": entity_summaries,
        "opinion_candidates": opinion_candidates[:20],
        "generated_at": now_iso(),
    }


def main():
    p = argparse.ArgumentParser(description="MindKernel memory index v0.1")
    p.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="workspace root path")
    p.add_argument("--db", default=str(DEFAULT_DB), help="sqlite db path")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")
    sub.add_parser("reindex")

    rc = sub.add_parser("recall")
    rc.add_argument("--query")
    rc.add_argument("--kind", choices=["W", "B", "O", "S"])
    rc.add_argument("--entity")
    rc.add_argument("--since-days", type=int)
    rc.add_argument("--limit", type=int, default=20)

    rf = sub.add_parser("reflect")
    rf.add_argument("--since-days", type=int)

    args = p.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    db_path = Path(args.db).expanduser().resolve()

    c = connect(db_path)
    init_db(c)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "db": str(db_path)}, ensure_ascii=False))
        return

    if args.cmd == "reindex":
        print(json.dumps(cmd_reindex(c, workspace), ensure_ascii=False, indent=2))
        return

    if args.cmd == "recall":
        print(
            json.dumps(
                cmd_recall(c, args.query, args.kind, args.entity, args.since_days, args.limit),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.cmd == "reflect":
        print(json.dumps(cmd_reflect(c, args.since_days), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
