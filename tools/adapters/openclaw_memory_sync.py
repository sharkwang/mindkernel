#!/usr/bin/env python3
"""
OpenClaw MEMORY.md → MindKernel 同步适配器

读取 OpenClaw 工作区的 MEMORY.md 和 memory/YYYY-MM-DD.md，
解析为结构化记忆条目，通过 MindKernel REST API 写入记忆库。

实现要点：
- MEMORY.md：按 ## 二级标题切分，每节一条记忆
- memory/YYYY-MM-DD.md：按 ### 三级标题切分，跳过复核相关节
- 去重：内容前200字符的 MD5 哈希，已同步则跳过
- Checkpoint：记录每文件 mtime + 已同步内容哈希集合
- API：POST http://localhost:18793/api/v1/retain

Usage:
  python3 openclaw_memory_sync.py [--once] [--poll --interval 300]
  默认 --once（适合 cron）；--poll 持续运行

Cron 示例（每30分钟一次）：
  */30 * * * *  /opt/homebrew/bin/python3 /Users/zhengwang/projects/mindkernel/tools/adapters/openclaw_memory_sync.py --once
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

API_BASE = "http://localhost:18793"
API_KEY = "mk_IsQ2BrHQCmKx6vqDU0wv5JceElh4hjE7zjQks2YdxTM"
CHECKPOINT_FILE = ROOT / "data" / "adapters" / "openclaw_memory_sync_checkpoint.json"

MEMORY_MD = Path.home() / ".openclaw" / "workspace" / "MEMORY.md"
DAILY_DIR = Path.home() / ".openclaw" / "workspace" / "memory"

PYTHON = "/opt/homebrew/bin/python3"


# ---------------------------------------------------------------------------
# API 调用
# ---------------------------------------------------------------------------

def api_retain(content: str, source: str, tags: list[str],
               event_date: str | None = None) -> dict | None:
    """调用 MindKernel /retain 接口。"""
    import urllib.request

    payload = {
        "content": content,
        "source": source,
        "confidence": 0.75,
        "tags": tags,
    }
    if event_date:
        payload["event_date"] = event_date

    body = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/retain",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "X-MindKernel-Key": API_KEY,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  [WARN] retain failed {e.code}: {body}")
        return None
    except Exception as e:
        print(f"  [WARN] retain error: {e}")
        return None


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        return json.loads(CHECKPOINT_FILE.read_text())
    return {"files": {}, "content_hashes": []}


def save_checkpoint(cp: dict):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_FILE.write_text(json.dumps(cp, ensure_ascii=False, indent=2))


def content_hash(text: str) -> str:
    return hashlib.md5(text[:200].encode()).hexdigest()


# ---------------------------------------------------------------------------
# 解析 MEMORY.md
# ---------------------------------------------------------------------------

def parse_memory_md(text: str) -> list[tuple[str, str, list[str]]]:
    """
    返回 [(section_title, section_content, tags)] 列表。
    按 ## 二级标题切分，每节一条。
    """
    sections = []
    # 匹配 ## 标题（## 标题文字）
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        # 跳过空节
        if not content or len(content) < 20:
            continue

        # 标签：从标题推断
        tags = ["memory-md", "curated"]
        if any(kw in title for kw in ["项目", "项目名", "核心"]):
            tags.append("project")
        if any(kw in title for kw in ["偏好", "风格", "沟通"]):
            tags.append("preference")
        if any(kw in title for kw in ["健康", "医疗"]):
            tags.append("health")
        if any(kw in title for kw in ["兴趣", "爱好"]):
            tags.append("hobby")
        if any(kw in title for kw in ["老人", "产品"]):
            tags.append("product")
        if any(kw in title for kw in ["工具", "版本", "OpenClaw"]):
            tags.append("platform")

        sections.append((title, content, tags))

    return sections


# ---------------------------------------------------------------------------
# 解析 daily memory
# ---------------------------------------------------------------------------

def parse_daily_memory(text: str, date_str: str) -> list[tuple[str, str, list[str]]]:
    """
    返回 [(subsection_title, content, tags)] 列表。
    按 ### 三级标题切分。
    跳过：复核范围（是元注释，不是新信息）
    """
    sections = []
    pattern = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(text))

    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if not content or len(content) < 20:
            continue

        # 跳过复核范围（meta-commentary）
        if "复核范围" in title or "复核" in title:
            continue

        # 日期化
        event_date = f"{date_str}T00:00:00Z"

        tags = ["daily-memory", f"date:{date_str}"]

        if "待跟踪" in title or "待办" in title:
            tags.append("todo")
        if "工程记录" in title or "项目" in title:
            tags.append("project")
        if "健康" in title:
            tags.append("health")
        if "兴趣" in title:
            tags.append("hobby")

        sections.append((f"[{date_str}] {title}", content, tags, event_date))

    return sections


# ---------------------------------------------------------------------------
# 核心同步逻辑
# ---------------------------------------------------------------------------

def sync_file(
    file_path: Path,
    parser_fn,
    cp: dict,
    source_prefix: str,
    parser_args: dict | None = None,
) -> tuple[int, int]:
    """
    同步单个文件。
    返回 (retained_count, skipped_count)。
    """
    if not file_path.exists():
        return 0, 0

    mtime = file_path.stat().st_mtime
    file_key = str(file_path)
    file_meta = cp.setdefault("files", {}).setdefault(file_key, {})

    # 检查 mtime 未变且已有哈希记录 → 跳过整文件
    if file_meta.get("mtime") == mtime and file_meta.get("content_hashes"):
        print(f"  [SKIP] {file_path.name} unchanged")
        return 0, file_meta["content_hashes"].__len__()

    text = file_path.read_text()
    sections = parser_fn(text, **(parser_args or {}))

    retained = 0
    skipped = 0
    new_hashes = []

    for sec in sections:
        if len(sec) == 4:
            title, content, tags, event_date = sec
        else:
            title, content, tags = sec
            event_date = None

        h = content_hash(content)

        if h in cp["content_hashes"]:
            skipped += 1
            new_hashes.append(h)
            continue

        result = api_retain(content, f"{source_prefix}:{file_path.name}", tags, event_date)
        if result and result.get("ok"):
            retained += 1
            new_hashes.append(h)
            cp["content_hashes"].append(h)
            print(f"  [RETAINED] {title[:60]}")
        else:
            # API 失败则不记哈希，下次重试
            print(f"  [FAIL] {title[:60]}")

    # 更新文件元数据
    file_meta["mtime"] = mtime
    file_meta["content_hashes"] = new_hashes

    return retained, skipped


def run_once() -> dict:
    """单次同步。返回统计。"""
    print(f"\n[{now_iso()}] OpenClaw MEMORY → MindKernel sync start")

    cp = load_checkpoint()
    total_retained = 0
    total_skipped = 0

    # 1. MEMORY.md
    print(f"\n[*] Syncing MEMORY.md")
    r, s = sync_file(MEMORY_MD, parse_memory_md, cp, "openclaw:memory-md")
    total_retained += r
    total_skipped += s

    # 2. Daily memory files (today + yesterday)
    if DAILY_DIR.exists():
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc).timestamp() - 86400)
        yesterday_str = datetime.fromtimestamp(yesterday, tz=timezone.utc).strftime("%Y-%m-%d")

        for day in [yesterday_str, today]:
            daily_file = DAILY_DIR / f"{day}.md"
            if daily_file.exists():
                print(f"\n[*] Syncing {daily_file.name}")
                r, s = sync_file(
                    daily_file,
                    parse_daily_memory,
                    cp,
                    "openclaw:daily",
                    {"date_str": day},
                )
                total_retained += r
                total_skipped += s

    save_checkpoint(cp)

    print(f"\n[{now_iso()}] Done — retained: {total_retained}, skipped: {total_skipped}")
    return {"retained": total_retained, "skipped": total_skipped}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="OpenClaw MEMORY.md → MindKernel sync")
    parser.add_argument("--once", action="store_true", help="单次运行（适合 cron）")
    parser.add_argument("--poll", action="store_true", help="持续轮询模式")
    parser.add_argument("--interval", type=int, default=300, help="轮询间隔秒数（默认300）")
    args = parser.parse_args()

    if args.poll:
        print(f"[adapter] polling mode, interval={args.interval}s")
        while True:
            run_once()
            time.sleep(args.interval)
    else:
        run_once()


if __name__ == "__main__":
    main()
