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
TOKEN_RE = re.compile(r"[a-z0-9']+|[\u4e00-\u9fff]+")
SLUG_RE = re.compile(r"[^a-z0-9]+")

AUTO_START = "<!-- AUTO-GENERATED:REFLECT:START -->"
AUTO_END = "<!-- AUTO-GENERATED:REFLECT:END -->"

NEG_WORDS = {
    "not",
    "no",
    "never",
    "dont",
    "don't",
    "doesnt",
    "doesn't",
    "cannot",
    "can't",
    "won't",
    "无",
    "不",
    "没",
    "不是",
    "不要",
}

STOP_WORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "to",
    "of",
    "with",
    "for",
    "in",
    "on",
    "is",
    "are",
    "was",
    "were",
    "be",
    "do",
    "does",
    "did",
}

SUPPORT_DELTA = 0.05
CONTRADICT_DELTA = 0.08


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

        CREATE TABLE IF NOT EXISTS opinions_state (
            opinion_key TEXT PRIMARY KEY,
            statement TEXT NOT NULL,
            entities TEXT NOT NULL,
            signature TEXT NOT NULL,
            negation INTEGER NOT NULL,
            confidence REAL NOT NULL,
            support_count INTEGER NOT NULL DEFAULT 0,
            contradict_count INTEGER NOT NULL DEFAULT 0,
            evidence_refs_json TEXT NOT NULL,
            last_event TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            UNIQUE(signature, entities)
        );

        CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);
        CREATE INDEX IF NOT EXISTS idx_facts_observed_date ON facts(observed_date);
        CREATE INDEX IF NOT EXISTS idx_opinions_sig_entities ON opinions_state(signature, entities);
        """
    )
    c.commit()


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def slugify(text: str) -> str:
    s = SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return s or "entity"


def tokenize_text(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def has_negation(tokens: list[str]) -> bool:
    for t in tokens:
        if t in NEG_WORDS:
            return True
        if any(ch in t for ch in ["不", "没", "无"]) and len(t) >= 1:
            return True
    return False


def _normalize_signature_token(t: str) -> str:
    # tiny heuristic: normalize simple English plural/3rd-person suffix
    if re.fullmatch(r"[a-z']+", t) and len(t) > 3 and t.endswith("s"):
        t = t[:-1]
    return t


def opinion_signature(text: str) -> str:
    tokens = tokenize_text(text)
    cleaned = []
    for t in tokens:
        if t in NEG_WORDS or t in STOP_WORDS:
            continue
        t = t.replace("不", "").replace("没", "").replace("无", "")
        t = _normalize_signature_token(t)
        if t:
            cleaned.append(t)
    return " ".join(cleaned)


def iter_md_files(workspace: Path):
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
        entities_str = " ".join(sorted(f["entities"]))
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
    if query:
        where = []
        params: list = []

        if since_days is not None:
            day = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
            where.append("(f.observed_date IS NULL OR f.observed_date >= ?)")
            params.append(day)

        if kind:
            where.append("f.kind = ?")
            params.append(kind)

        if entity:
            where.append("f.entities LIKE ?")
            params.append(f"%{entity}%")

        where.append("facts_fts MATCH ?")
        params.append(query)

        sql = """
        SELECT f.* FROM facts_fts
        JOIN facts f ON f.id = facts_fts.fact_id
        WHERE """ + " AND ".join(where) + " ORDER BY f.observed_date DESC, f.indexed_at DESC LIMIT ?"
        params.append(limit)
        rows = c.execute(sql, params).fetchall()
    else:
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


def _upsert_autogen_block(path: Path, title: str, block_lines: list[str]):
    if path.exists():
        content = path.read_text(errors="ignore")
    else:
        content = f"# {title}\n\n"

    block = "\n".join([AUTO_START, *block_lines, AUTO_END])

    if AUTO_START in content and AUTO_END in content:
        start = content.index(AUTO_START)
        end = content.index(AUTO_END) + len(AUTO_END)
        new_content = content[:start] + block + content[end:]
    else:
        if not content.endswith("\n"):
            content += "\n"
        new_content = content + "\n" + block + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content)


def evolve_opinions(c: sqlite3.Connection, opinion_candidates: list[dict]):
    # deterministic order: observed_date then source_ref
    def _key(x):
        return (x.get("observed_date") or "", x.get("source_ref") or "")

    for op in sorted(opinion_candidates, key=_key):
        entities = sorted(op.get("entities", []))
        entities_str = " ".join(entities)
        statement = op.get("content", "").strip()
        if not statement:
            continue

        sig = opinion_signature(statement)
        neg = 1 if has_negation(tokenize_text(statement)) else 0

        row = c.execute(
            "SELECT * FROM opinions_state WHERE signature=? AND entities=?",
            (sig, entities_str),
        ).fetchone()

        src = op.get("source_ref") or ""
        base_conf = float(op.get("confidence", 0.7))

        if not row:
            opinion_key = f"op_{sha1_text(sig + '|' + entities_str)[:16]}"
            c.execute(
                """
                INSERT INTO opinions_state(
                    opinion_key, statement, entities, signature, negation,
                    confidence, support_count, contradict_count,
                    evidence_refs_json, last_event, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, 'new', ?)
                """,
                (
                    opinion_key,
                    statement,
                    entities_str,
                    sig,
                    neg,
                    max(0.05, min(0.99, base_conf)),
                    json.dumps([src], ensure_ascii=False),
                    now_iso(),
                ),
            )
            continue

        conf = float(row["confidence"])
        support = int(row["support_count"])
        contradict = int(row["contradict_count"])
        evidence = json.loads(row["evidence_refs_json"] or "[]")

        if src and src not in evidence:
            evidence.append(src)

        if int(row["negation"]) == neg:
            conf = min(0.99, conf + SUPPORT_DELTA)
            support += 1
            last_event = "support"
        else:
            conf = max(0.05, conf - CONTRADICT_DELTA)
            contradict += 1
            last_event = "contradict"

        c.execute(
            """
            UPDATE opinions_state
            SET confidence=?, support_count=?, contradict_count=?,
                evidence_refs_json=?, last_event=?, last_updated=?
            WHERE opinion_key=?
            """,
            (
                conf,
                support,
                contradict,
                json.dumps(evidence, ensure_ascii=False),
                last_event,
                now_iso(),
                row["opinion_key"],
            ),
        )

    c.commit()


def list_opinion_states(c: sqlite3.Connection, limit: int = 200):
    rows = c.execute(
        "SELECT * FROM opinions_state ORDER BY last_updated DESC LIMIT ?",
        (limit,),
    ).fetchall()

    out = []
    for r in rows:
        out.append(
            {
                "opinion_key": r["opinion_key"],
                "statement": r["statement"],
                "entities": [x for x in (r["entities"] or "").split() if x],
                "confidence": r["confidence"],
                "support_count": r["support_count"],
                "contradict_count": r["contradict_count"],
                "last_event": r["last_event"],
                "evidence_refs": json.loads(r["evidence_refs_json"] or "[]"),
                "last_updated": r["last_updated"],
            }
        )
    return out


def apply_reflect_writeback(workspace: Path, reflection: dict, max_per_entity: int, max_opinions: int):
    written = []

    entities_dir = workspace / "bank" / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)

    for summary in reflection.get("entity_summaries", []):
        entity = summary["entity"]
        facts = summary.get("top_facts", [])[:max_per_entity]

        lines = [
            f"# {entity}",
            "",
            "> Auto-generated by `memory_index_v0_1.py reflect --writeback`.",
            "",
            "## Facts",
        ]
        for f in facts:
            lines.append(
                f"- [{f['kind']} c={f['confidence']:.2f}] {f['content']} _(source: {f['source_ref']})_"
            )
        lines.append("")

        out_path = entities_dir / f"{slugify(entity)}.md"
        out_path.write_text("\n".join(lines))
        written.append(str(out_path.relative_to(workspace)))

    opinions_path = workspace / "bank" / "opinions.md"
    states = reflection.get("opinion_states", [])[:max_opinions]
    op_lines = [
        "## Auto Opinions",
        "",
    ]

    if states:
        for st in states:
            entities = " ".join(f"@{e}" for e in st.get("entities", []))
            s = int(st.get("support_count", 0))
            c = int(st.get("contradict_count", 0))
            trend = "↑" if s > c else ("↓" if c > s else "→")
            op_lines.append(
                f"- (c={float(st['confidence']):.2f}, trend={trend}, +{s}/-{c}) {entities} {st['statement']}"
            )
            ev = st.get("evidence_refs", [])[:3]
            if ev:
                op_lines.append(f"  - evidence: {', '.join(ev)}")
    else:
        # fallback for no evolved state
        for op in reflection.get("opinion_candidates", [])[:max_opinions]:
            entities = " ".join(f"@{e}" for e in op.get("entities", []))
            op_lines.append(
                f"- (c={op['confidence']:.2f}) {entities} {op['content']} _(source: {op['source_ref']})_".strip()
            )

    _upsert_autogen_block(opinions_path, "Opinions", op_lines)
    written.append(str(opinions_path.relative_to(workspace)))

    return written


def cmd_reflect(
    c: sqlite3.Connection,
    since_days: int | None,
    workspace: Path,
    writeback: bool,
    max_per_entity: int,
    max_opinions: int,
):
    params = []
    where = []
    if since_days is not None:
        day = (datetime.now(timezone.utc) - timedelta(days=since_days)).date().isoformat()
        where.append("(observed_date IS NULL OR observed_date >= ?)")
        params.append(day)

    sql = "SELECT kind, entities, confidence, content, source_ref, observed_date FROM facts"
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
                    "observed_date": r["observed_date"],
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

    out = {
        "entity_summaries": entity_summaries,
        "opinion_candidates": opinion_candidates[:50],
        "generated_at": now_iso(),
    }

    if writeback:
        evolve_opinions(c, opinion_candidates)
        out["opinion_states"] = list_opinion_states(c, limit=max_opinions)
        written = apply_reflect_writeback(workspace, out, max_per_entity=max_per_entity, max_opinions=max_opinions)
        out["writeback"] = {"enabled": True, "paths": written}

    return out


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
    rf.add_argument("--writeback", action="store_true", help="write reflection result into bank/entities + bank/opinions")
    rf.add_argument("--max-per-entity", type=int, default=8)
    rf.add_argument("--max-opinions", type=int, default=50)

    lo = sub.add_parser("list-opinions-state")
    lo.add_argument("--limit", type=int, default=50)

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
        print(
            json.dumps(
                cmd_reflect(
                    c,
                    args.since_days,
                    workspace=workspace,
                    writeback=args.writeback,
                    max_per_entity=args.max_per_entity,
                    max_opinions=args.max_opinions,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.cmd == "list-opinions-state":
        print(json.dumps(list_opinion_states(c, args.limit), ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
