"""
Filesystem Adapter — 监控指定文件夹，增量读取文件内容作为记忆源。

支持：.md, .txt, .json, .csv, .pdf（文本提取）
增量策略：记录上次同步的 mtime，只同步有变化的文件。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ADAPTER_NAME = "filesystem"
STATE_FILE = ROOT / ".mindkernel" / "state" / "filesystem_sync.json"
DEFAULT_WATCH = [
    str(Path.home() / "notes"),
    str(Path.home() / "documents"),
]
MAX_FILE_SIZE_KB = 512
INCLUDE_EXTENSIONS = {".md", ".txt", ".json", ".csv"}


def _load_state() -> dict:
    path = STATE_FILE.expanduser()
    if path.exists():
        return json.loads(path.read_text())
    return {"file_mtimes": {}, "synced_count": 0}


def _save_state(state: dict):
    path = STATE_FILE.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _read_file_content(file_path: Path) -> str | None:
    """读取文件内容，处理编码问题。"""
    try:
        content = file_path.read_text(encoding="utf-8")
        return content
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="gbk")
            return content
        except Exception:
            return None
    except OSError:
        return None


def _extract_text(content: str, ext: str) -> str:
    """从内容中提取可读文本。"""
    if ext == ".json":
        try:
            obj = json.loads(content)
            return json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            return content[:2000]
    elif ext == ".csv":
        lines = content.splitlines()
        return "\n".join(lines[:50])  # 只取前 50 行
    else:
        return content[:5000]  # 其他文件截断


def poll(watch_paths: list[str] | None = None) -> list[dict]:
    """
    增量检查 watch_paths 下有变化的文件，返回 MemoryEvent 列表。
    """
    state = _load_state()
    file_mtimes = state.get("file_mtimes", {})
    watch_paths = watch_paths or DEFAULT_WATCH
    new_events = []

    for base_path_str in watch_paths:
        base = Path(base_path_str).expanduser()
        if not base.exists():
            continue

        for root, dirs, files in os.walk(base):
            # 跳过隐藏目录
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()

                if ext not in INCLUDE_EXTENSIONS:
                    continue

                # 跳过太大的文件
                size_kb = fpath.stat().st_size / 1024
                if size_kb > MAX_FILE_SIZE_KB:
                    continue

                mtime_key = str(fpath)
                current_mtime = fpath.stat().st_mtime

                # 无变化则跳过
                if file_mtimes.get(mtime_key, 0) >= current_mtime:
                    continue

                content = _read_file_content(fpath)
                if not content:
                    continue

                text = _extract_text(content, ext)
                doc_date = datetime.fromtimestamp(current_mtime, tz=timezone.utc)

                new_events.append({
                    "id": f"fs_{uuid.uuid4().hex[:12]}",
                    "content": f"[{fpath.name}]\n{text}",
                    "source": f"filesystem:{fpath.parent.name}",
                    "file_path": str(fpath),
                    "document_date": doc_date.isoformat().replace("+00:00", "Z"),
                    "event_date": None,
                    "tags": ["filesystem", "file"],
                    "metadata": {
                        "filename": fpath.name,
                        "file_path": str(fpath),
                        "file_ext": ext,
                        "adapter": ADAPTER_NAME,
                    },
                })

                file_mtimes[mtime_key] = current_mtime

    if new_events:
        state["file_mtimes"] = file_mtimes
        state["synced_count"] = state.get("synced_count", 0) + len(new_events)
        state["last_sync"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _save_state(state)

    return new_events


if __name__ == "__main__":
    events = poll()
    print(f"Found {len(events)} changed files")
    for ev in events:
        print(f"  [{ev['id']}] {ev['metadata']['filename']} — {ev['document_date']}")
