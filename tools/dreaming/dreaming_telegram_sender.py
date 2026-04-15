#!/usr/bin/env python3
"""
Dreaming Telegram Sender — M2 ask_human 行动分发到 Telegram

功能：
- 读取 active_push_buffer 中 source=dreaming 的条目
- 通过 openclaw message send --channel telegram 发送给王大爷
- 幂等 ledger 防重复发送

王大爷 Telegram ID: 7160024547
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUFFER = ROOT / "data" / "governance" / "active_push_buffer.jsonl"
LEDGER = ROOT / "data" / "dreaming" / "telegram_sent_ledger.jsonl"
SENT_IDS = ROOT / "data" / "dreaming" / "telegram_sent_ids.json"


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_sent_ids() -> set:
    p = SENT_IDS
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except Exception:
        return set()


def save_sent_ids(ids: set):
    p = SENT_IDS
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(ids)))


def send_telegram(text: str, target_id: str = "7160024547") -> bool:
    """通过 openclaw message 发送 Telegram 消息。"""
    cmd = [
        "openclaw", "message", "send",
        "--channel", "telegram",
        "--target", target_id,
        "--message", text,
    ]
    env = dict(os.environ)
    env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
            env=env,
        )
        if result.returncode == 0:
            print(f"[TG] Sent to {target_id}: {text[:80]}")
            return True
        else:
            print(f"[TG] Failed RC={result.returncode}: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"[TG] Exception: {e}")
        return False


def main():
    sent_ids = load_sent_ids()
    new_sent = set()
    remaining = []

    if not BUFFER.exists():
        print("[TG] Buffer empty, nothing to send")
        return

    for line in BUFFER.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            remaining.append(line)
            continue

        # Only process dreaming entries
        if entry.get("source") != "dreaming":
            remaining.append(line)
            continue

        entry_id = entry.get("id", "")
        entry_type = entry.get("type", "dreaming")
        text = entry.get("text", "")
        urgency = entry.get("urgency", "medium")

        if entry_id in sent_ids:
            remaining.append(line)
            continue

        # Build Telegram message
        if entry_type == "ask_human":
            prefix = "🤔"
        elif entry_type == "emotion_action":
            prefix = "💬"
        elif entry_type == "task_activation":
            prefix = "🎯"
        elif entry_type == "association":
            prefix = "🔗"
        else:
            prefix = "🌙"

        urgency_icon = "🔴" if urgency == "high" else ("🟡" if urgency == "medium" else "⚪")
        msg = f"{prefix} {urgency_icon} *M2 行动提醒*\n\n{text}\n\n_来自 MindKernel 做梦机制_"

        if send_telegram(msg):
            new_sent.add(entry_id)
            sent_ids.add(entry_id)
        else:
            # Keep in buffer for retry next cycle
            remaining.append(line)

    # Rewrite buffer (remove sent entries)
    BUFFER.write_text("\n".join(remaining) + "\n")
    save_sent_ids(sent_ids)

    if new_sent:
        print(f"[TG] Done. Sent {len(new_sent)} messages: {new_sent}")
    else:
        print("[TG] No new messages to send")


if __name__ == "__main__":
    main()
