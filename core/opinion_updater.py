"""
Opinion 自动更新器 — 在 memory_to_experience 成功后自动更新 opinions_v0_1.json

功能：
- 从 memory/experience 内容中提取实体关键词
- 匹配已有 opinions，更新置信度和访问记录
- 新实体自动创建新 opinion 条目
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OPINIONS_FILE = ROOT / "data" / "opinions_v0_1.json"


def load_opinions() -> list[dict]:
    if not OPINIONS_FILE.exists():
        return []
    return json.loads(OPINIONS_FILE.read_text())


def save_opinions(opinions: list[dict]):
    OPINIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    OPINIONS_FILE.write_text(json.dumps(opinions, indent=2, ensure_ascii=False))


def extract_entities(content: str) -> list[str]:
    """从文本中提取关键词实体。"""
    entities = []
    # 中文实体（2-6字）
    for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', content):
        entities.append(m.group())
    # 英文实体（2-20字）
    for m in re.finditer(r'[A-Za-z][A-Za-z0-9 ]{1,19}', content):
        word = m.group().strip()
        if len(word) >= 2:
            entities.append(word)
    return list(set(entities))


def update_opinions(
    memory_content: str,
    experience_summary: str,
    experience_id: str,
    outcome: str,
) -> list[dict]:
    """
    根据新产生的 experience 自动更新 opinions。
    返回更新后的 opinions 列表。
    """
    opinions = load_opinions()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    all_text = f"{memory_content} {experience_summary}"
    entities = extract_entities(all_text)

    # 预定义的关键话题匹配
    TOPIC_KEYWORDS = {
        "project:mindkernel": ["MindKernel", "mindkernel"],
        "project:omexai": ["OmexAI", "omexai"],
        "hobby:baking": ["烘焙", "夏巴塔", "烤箱", "baking"],
        "platform:openclaw": ["OpenClaw", "openclaw"],
        "product:elderly_care": ["老人陪伴", "badge", "可穿戴"],
        "channel:wechat": ["微信", "wechat", "weixin"],
        "milestone:rest_api": ["REST API", "API 服务"],
    }

    # 统计各话题匹配
    topic_hits = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw.lower() in all_text.lower())
        if hits > 0:
            topic_hits[topic] = hits

    updated_ids = set()

    # 更新已有 opinions
    for op in opinions:
        op_id = op.get("id", "")
        matched = False

        # 按 topic 匹配
        for topic in op.get("topics", []):
            if topic in topic_hits:
                # 增加置信度（最多到 0.98）
                old_conf = op.get("confidence", 0.5)
                new_conf = min(0.98, old_conf + 0.05 * topic_hits[topic])
                op["confidence"] = round(new_conf, 3)
                op["updated_at"] = now
                op["access_count"] = op.get("access_count", 0) + 1
                # 追加新证据
                if experience_id not in op.get("evidence_refs", []):
                    op.setdefault("evidence_refs", []).append(experience_id)
                matched = True
                updated_ids.add(op_id)

        # 按实体关键词匹配（未归类的新实体）
        if not matched:
            for entity in entities:
                if entity in op.get("statement", "") or entity in op.get("summary", ""):
                    old_conf = op.get("confidence", 0.5)
                    op["confidence"] = min(0.95, old_conf + 0.03)
                    op["updated_at"] = now
                    op["access_count"] = op.get("access_count", 0) + 1
                    updated_ids.add(op_id)
                    break

    # 为未匹配的高频实体创建新 opinion
    for entity in entities:
        already_covered = any(entity in op.get("statement", "") or entity in op.get("summary", "") for op in opinions)
        if already_covered:
            continue
        # 只为有意义的实体创建（长度>=2，出现>=2次）
        if len(entity) < 2:
            continue
        if all_text.count(entity) < 2:
            continue

        # 判断话题分类
        entity_topics = []
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(kw.lower() in entity.lower() for kw in keywords):
                entity_topics.append(topic)

        new_op = {
            "id": f"op_{entity[:8].lower()}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "statement": f"关于{entity}的持续关注",
            "summary": all_text[:200],
            "confidence": 0.55,  # 新实体从 0.55 开始
            "topics": entity_topics or ["general"],
            "rule_name": "auto_extracted",
            "created_at": now,
            "updated_at": now,
            "access_count": 1,
            "evidence_refs": [experience_id],
        }
        opinions.append(new_op)
        updated_ids.add(new_op["id"])

    # 保存
    save_opinions(opinions)

    return {
        "total_opinions": len(opinions),
        "updated": len(updated_ids),
        "new_entities_found": len([e for e in entities if not any(e in op.get("statement","") for op in opinions)]),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--memory-content", required=True)
    parser.add_argument("--experience-summary", required=True)
    parser.add_argument("--experience-id", required=True)
    parser.add_argument("--outcome", default="neutral")
    args = parser.parse_args()

    result = update_opinions(
        args.memory_content,
        args.experience_summary,
        args.experience_id,
        args.outcome,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
