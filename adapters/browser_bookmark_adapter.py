"""
Browser Bookmark Adapter — 增量读取浏览器书签，生成 MemoryEvent。

支持：Chrome / Edge（macOS）
增量策略：记录上次同步的书签 index，下次只同步新增的。
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADAPTER_NAME = "browser_bookmark"
STATE_FILE = ROOT / ".mindkernel" / "state" / "browser_bookmark_sync.json"
MAX_FETCH_PER_RUN = 20


def _get_bookmarks_path(browser: str = "Chrome") -> Path:
    if browser == "Chrome":
        base = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    elif browser == "Edge":
        base = Path.home() / "Library" / "Application Support" / "Microsoft Edge"
    else:
        raise ValueError(f"Unsupported browser: {browser}")
    return base / "Default" / "Bookmarks"


def _parse_chrome_bookmarks(path: Path) -> list[dict]:
    """解析 Chrome Bookmarks 文件，返回 [{id, url, title, date_added}, ...]"""
    if not path.exists():
        return []

    raw = json.loads(path.read_text())
    results = []

    def walk(node):
        if node.get("type") == "url":
            results.append({
                "id": node["id"],
                "url": node["url"],
                "title": node.get("name", ""),
                # Chrome date_added 是微秒时间戳
                "date_added": int(node.get("date_added", 0)),
            })
        for child in node.get("children", []):
            walk(child)

    walk(raw.get("roots", {}).get("bookmark_bar", {}))
    walk(raw.get("roots", {}).get("other", {}))
    return results


def _chrome_ts_to_datetime(microseconds: int) -> datetime:
    """Chrome 时间戳（1601-01-01 起微秒）转为 datetime"""
    if not microseconds:
        return datetime.now(timezone.utc)
    epoch_delta = datetime(1601, 1, 1, tzinfo=timezone.utc)
    return epoch_delta + __import__("datetime").timedelta(microseconds=microseconds)


def _load_sync_state() -> dict:
    path = STATE_FILE.expanduser()
    if path.exists():
        return json.loads(path.read_text())
    return {"last_sync_index": 0, "synced_ids": []}


def _save_sync_state(state: dict):
    path = STATE_FILE.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _fetch_page_text(url: str, timeout: int = 5) -> str | None:
    """尝试抓取页面正文（简化版：返回标题和 meta description）。"""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 MindKernel/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        # 简单提取 <title>
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
        title = title_match.group(1).strip() if title_match else ""
        return title
    except Exception:
        return None


def poll(browser: str = "Chrome") -> list[dict]:
    """
    增量获取新书签，返回 MemoryEvent 列表。
    每个 event 格式：
    {
        "id": "bm_xxx",
        "content": "页面标题",
        "source": "browser:chrome:bookmark",
        "url": "...",
        "document_date": "...",
        "tags": ["browser", "bookmark"],
        "metadata": {...}
    }
    """
    state = _load_sync_state()
    bookmarks = _parse_chrome_bookmarks(_get_bookmarks_path(browser))

    # 全量新增书签（按 Chrome ID）
    new_bookmarks = [
        bm for bm in bookmarks
        if bm["id"] not in state.get("synced_ids", [])
    ][:MAX_FETCH_PER_RUN]

    if not new_bookmarks:
        return []

    events = []
    for bm in new_bookmarks:
        doc_date = _chrome_ts_to_datetime(bm["date_added"])
        content = bm["title"] or bm["url"]
        # 尝试抓取页面标题增强内容
        page_title = _fetch_page_text(bm["url"])
        if page_title and page_title != content:
            content = f"{content} | {page_title}"

        events.append({
            "id": f"bm_{uuid.uuid4().hex[:12]}",
            "content": content,
            "source": f"browser:{browser.lower()}:bookmark",
            "url": bm["url"],
            "document_date": doc_date.isoformat().replace("+00:00", "Z"),
            "event_date": None,
            "tags": ["browser", "bookmark"],
            "metadata": {
                "bookmark_id": bm["id"],
                "original_url": bm["url"],
                "adapter": ADAPTER_NAME,
            },
        })

    # 更新同步状态
    state["synced_ids"].extend([bm["id"] for bm in new_bookmarks])
    state["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _save_sync_state(state)

    return events


if __name__ == "__main__":
    events = poll()
    print(f"Found {len(events)} new bookmarks")
    for ev in events:
        print(f"  [{ev['id']}] {ev['content'][:60]} — {ev['url']}")
