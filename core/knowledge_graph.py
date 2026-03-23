"""
Knowledge Graph — 实体关系图谱模块。

存储 (subject, predicate, object) 三元组，支持：
- add_relation()    — 写入一条关系
- get_relations()  — 查询某实体的所有关系
- extract_relations() — 从文本内容中 LLM 抽取关系
- query_graph()    — 图遍历查询（2度关联）
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.memory_experience_core_v0_1 import conn as _conn, now_iso

DB_PATH = ROOT / "data" / "mindkernel_v0_1.sqlite"


def init_graph_db(c: sqlite3.Connection):
    """初始化关系图谱表。"""
    c.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_relations (
            id          TEXT PRIMARY KEY,
            subject     TEXT NOT NULL,
            predicate   TEXT NOT NULL,
            object      TEXT NOT NULL,
            confidence  REAL    DEFAULT 0.8,
            source      TEXT,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_kg_subject ON knowledge_relations(subject)
    """)
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_kg_object ON knowledge_relations(object)
    """)


def ensure_graph_db():
    c = _conn(DB_PATH)
    init_graph_db(c)
    c.commit()
    c.close()


def add_relation(
    subject: str,
    predicate: str,
    obj: str,
    confidence: float = 0.8,
    source: str | None = None,
) -> str:
    """
    写入一条知识关系。
    返回 relation id。
    """
    rel_id = f"rel_{uuid.uuid4().hex[:12]}"
    now = now_iso()
    c = _conn(DB_PATH)
    init_graph_db(c)
    try:
        c.execute(
            """
            INSERT INTO knowledge_relations
                (id, subject, predicate, object, confidence, source, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (rel_id, subject, predicate, obj, confidence, source, now, now),
        )
        c.commit()
    finally:
        c.close()
    return rel_id


def get_relations(entity: str, depth: int = 1) -> list[dict]:
    """
    查询某实体的所有关系（正向+反向）。
    depth=1：直接关系
    depth=2：2度关联（朋友的友人）
    """
    c = _conn(DB_PATH)
    init_graph_db(c)
    results = []

    try:
        # 1度：entity 作为 subject 或 object
        rows = c.execute(
            """
            SELECT id, subject, predicate, object, confidence, source, created_at
            FROM knowledge_relations
            WHERE subject = ? OR object = ?
            ORDER BY confidence DESC
            """,
            (entity, entity),
        ).fetchall()

        for row in rows:
            d = dict(row)
            d["direction"] = "outgoing" if d["subject"] == entity else "incoming"
            results.append(d)

        if depth >= 2:
            # 找关联实体
            related_entities = set()
            for r in results:
                related_entities.add(r["object"] if r["subject"] == entity else r["subject"])
            related_entities.discard(entity)

            for rel_entity in related_entities:
                rows2 = c.execute(
                    """
                    SELECT id, subject, predicate, object, confidence, source, created_at
                    FROM knowledge_relations
                    WHERE (subject = ? OR object = ?)
                      AND subject != ? AND object != ?
                    ORDER BY confidence DESC
                    LIMIT 20
                    """,
                    (rel_entity, rel_entity, entity, entity),
                ).fetchall()
                for row in rows2:
                    d = dict(row)
                    d["direction"] = "outgoing" if d["subject"] == rel_entity else "incoming"
                    d["via_entity"] = rel_entity
                    results.append(d)
    finally:
        c.close()

    return results


def extract_relations_from_text(content: str, source: str | None = None) -> list[dict]:
    """
    从文本内容中抽取知识关系三元组。

    V1 使用简单正则模式匹配（轻量降级），
    v0.5 将接入 LLM 实现语义关系抽取。
    """
    import re
    results = []

    # 模式1: "X 是 Y"
    for m in re.finditer(r'([^，,\s]+?)\s*是\s*([^。，,\s]+)', content):
        results.append({
            "subject": m.group(1).strip(),
            "predicate": "是",
            "object": m.group(2).strip(),
            "confidence": 0.7,
            "source": source,
        })

    # 模式2: "X 属于 Y"
    for m in re.finditer(r'([^，,\s]+?)\s*属于\s*([^。，,\s]+)', content):
        results.append({
            "subject": m.group(1).strip(),
            "predicate": "属于",
            "object": m.group(2).strip(),
            "confidence": 0.7,
            "source": source,
        })

    return results[:5]  # 最多 5 条


def auto_extract_and_store(content: str, memory_id: str | None = None, source: str | None = None):
    """
    从文本中抽取关系并自动写入图谱。
    """
    relations = extract_relations_from_text(content, source)
    stored = []
    for rel in relations:
        rel_id = add_relation(
            subject=rel["subject"],
            predicate=rel["predicate"],
            obj=rel["object"],
            confidence=rel["confidence"],
            source=rel.get("source") or f"memory:{memory_id}",
        )
        stored.append(rel_id)
    return stored


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Knowledge Graph CLI")
    parser.add_argument("--init", action="store_true", help="初始化图谱数据库")
    parser.add_argument("--add", nargs=3, metavar=("SUBJECT", "PREDICATE", "OBJECT"), help="添加关系")
    parser.add_argument("--query", metavar="ENTITY", help="查询实体关系")
    parser.add_argument("--extract", metavar="FILE", help="从文件抽取关系")
    args = parser.parse_args()

    if args.init:
        ensure_graph_db()
        print("Graph DB initialized.")

    elif args.add:
        rel_id = add_relation(args.add[0], args.add[1], args.add[2])
        print(f"Added relation: {rel_id}")

    elif args.query:
        rels = get_relations(args.query, depth=2)
        print(f"Found {len(rels)} relations for '{args.query}':")
        for r in rels:
            direction = r.get("direction", "")
            via = r.get("via_entity", "")
            print(f"  [{direction}] {r['subject']} --{r['predicate']}--> {r['object']} (conf={r['confidence']}, via={via})")

    elif args.extract:
        content = Path(args.extract).read_text()
        relations = extract_relations_from_text(content)
        print(f"Extracted {len(relations)} relations:")
        for rel in relations:
            print(f"  {rel['subject']} --{rel['predicate']}--> {rel['object']}")
