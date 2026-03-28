#!/usr/bin/env python3
"""
DialogueContextResolver — 对话流语义闭环合并

优先级：
  1. 任务型（首发）  ：提案 → 确认 → 完成
  2. 问答型（扩展位）
  3. 信息共享型（扩展位）

设计原则：
  - 自然日存续，当日有效，跨日关闭未完成任务
  - importance 继承提案方，不被确认词拉低
  - 保守匹配：宁可漏掉，不要误报
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# ── 关键词定义（保守策略）────────────────────────────────────────────────────

# 提案：assistant 开头提出的方案/计划
# 要求：content 开头包含这些词，且内容长度 > 20
PROPOSAL_PREFIXES = [
    "要不要", "要不要我", "要不要试试",
    "方案是", "方案：",
    "可以这样", "可以这样处理",
    "这样行不行", "这样处理",
    "我来搞", "我来写", "我来改",
    "我打算", "我计划",
    "先这样",
]

# 提案关键词（substring 匹配，宽松模式）
PROPOSAL_KEYWORDS = [
    "要不要", "方案是", "可以这样", "这样行不行",
    "我来搞", "我来写", "我来改",
    "我打算", "我计划",
    "先这样", "第一步",
    "修复方案", "处理方案", "改进方案",
    "方案",   # 泛指方案，如"出方案""提方案""给个方案"
]

# 确认：user 回复同意
APPROVAL_EXACT = {"同意", "可以", "行", "没问题", "就这么办", "好", "好呀", "好的"}

# 完成确认：有 active_task 时的 user 完成信号
COMPLETION_PREFIXES = [
    "好", "好的", "好嘞",
    "收到", "知道了", "明白了",
    "完成了", "好了", "搞定", "解决了",
    "👍", "OK", "ok",
]

# 弃权
CANCEL_EXACT = {"算了", "不用了", "取消", "算了不用"}


# ── 数据结构 ────────────────────────────────────────────────────────────────

@dataclass
class TaskItem:
    task_id: str
    proposal_text: str          # 方案摘要
    proposal_ts: str
    proposal_index: int
    approved: bool = False
    approved_ts: Optional[str] = None
    completed: bool = False
    completed_ts: Optional[str] = None
    status: str = "active"       # active | completed | cancelled | expired

    def closure_summary(self) -> Optional[str]:
        if self.status == "completed":
            return f"「{self.proposal_text}」已完成"
        elif self.status == "cancelled":
            return f"「{self.proposal_text}」已取消"
        elif self.status == "expired":
            return f"「{self.proposal_text}」已批准，状态未知"
        return None

    def close(self, status: str, ts: Optional[str] = None):
        self.status = status
        self.completed = (status == "completed")
        if ts:
            self.completed_ts = ts


@dataclass
class ResolvedMessage:
    content: str
    importance: float
    timestamp: str
    role: str = "system"
    sources: list[int] = field(default_factory=list)
    task_id: Optional[str] = None


# ── 核心解析器 ──────────────────────────────────────────────────────────────

class DialogueContextResolver:
    """
    在一个 session 消息列表内检测任务型语义闭环：
    「提案（assistant）→ 确认（user）→ 完成（user）」

    算法：
      1. 扫描 assistant 消息，检测提案 → 创建 active_task
      2. 扫描 user 消息，检查是否有 active_task：
         - 有 → 判断是 approve 还是 complete
         - 无 → 忽略（不触发独立完成）
      3. 自然日边界：未完成的任务关闭
    """

    def __init__(self, today: Optional[date] = None):
        self.today = today or date.today()
        self.active_tasks: list[TaskItem] = []   # 有序，最近的在后面
        self.consumed: set[int] = set()          # 已合并的消息索引

    # ── 基础判断 ───────────────────────────────────────────────────────────

    def _extract_text(self, content) -> str:
        if isinstance(content, list):
            return "".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        return str(content) if content else ""

    def _strip_reply_marker(self, text: str) -> str:
        """去除开头的 [[reply_to_current]] 等标记"""
        text = text.strip()
        text = re.sub(r"^\[\[reply_to[^\]]*\]\]\s*", "", text)
        return text.strip()

    def _is_proposal(self, text: str) -> bool:
        """提案判断：内容较长（≥10字），含提案关键词，且关键词在开头附近（≤50字）"""
        text = self._strip_reply_marker(text)
        if len(text) < 10:
            return False
        head = text[:50]
        return (
            any(head.startswith(p) for p in PROPOSAL_PREFIXES)
            or any(kw in head for kw in PROPOSAL_KEYWORDS)
        )

    def _is_approval(self, text: str) -> bool:
        text = text.strip()
        return text in APPROVAL_EXACT

    def _is_completion(self, text: str) -> bool:
        """完成确认：必须有 active_task；单独的好/收到不算"""
        if not self.active_tasks:
            return False
        text = self._strip_reply_marker(text.strip())
        return any(text.startswith(p) for p in COMPLETION_PREFIXES) or text in {"好", "好的", "收到", "OK", "ok"}

    def _is_cancel(self, text: str) -> bool:
        return text.strip() in CANCEL_EXACT

    def _clean_proposal_text(self, text: str) -> str:
        """提取并截取方案核心"""
        text = self._strip_reply_marker(text)
        for prefix in PROPOSAL_PREFIXES:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break
        # 去除开头的标点
        text = text.lstrip("：:：、，,")
        return text.strip()[:120]

    def _gen_task_id(self, text: str, ts: str) -> str:
        seed = f"{text[:50]}|{ts}"
        return f"task_{hashlib.sha1(seed.encode()).hexdigest()[:12]}"

    # ── 主入口 ────────────────────────────────────────────────────────────

    def resolve(self, messages: list[dict]) -> list[ResolvedMessage]:
        """
        输入：[{role, content, timestamp, index}, ...]
        输出：[ResolvedMessage, ...]
        """
        resolved = []
        n = len(messages)

        for i, msg in enumerate(messages):
            if i in self.consumed:
                continue

            text = self._extract_text(msg.get("content", ""))
            role = msg.get("role", "")
            ts = msg.get("timestamp", "")

            if not text.strip() or role not in ("user", "assistant"):
                continue

            # ── 1. 提案检测（assistant）─────────────────────────────────
            # 关键约束：同 segment 内，只创建第一个未批准的提案；
            # 后续含提案关键词的 assistant 消息视为执行进展，不重复提案
            if role == "assistant" and self._is_proposal(text):
                # 检查是否已有未批准的 active task
                existing_unapproved = any(
                    t.status == "active" and not t.approved
                    for t in self.active_tasks
                )
                if existing_unapproved:
                    # 同 topic 已有提案，后续执行消息不重复创建
                    pass
                else:
                    task_id = self._gen_task_id(text, ts)
                    task = TaskItem(
                        task_id=task_id,
                        proposal_text=self._clean_proposal_text(text),
                        proposal_ts=ts,
                        proposal_index=i,
                    )
                    self.active_tasks.append(task)
                    self.consumed.add(i)
                    resolved.append(ResolvedMessage(
                        content=f"[任务提案] {task.proposal_text}",
                        importance=0.8,
                        timestamp=ts,
                        role="assistant",
                        sources=[i],
                        task_id=task_id,
                    ))

            # ── 2. User 消息处理 ────────────────────────────────────────
            elif role == "user":
                cleaned = self._strip_reply_marker(text)

                # 2a. 取消
                if self._is_cancel(cleaned):
                    self.consumed.add(i)
                    # 关闭最近一个未完成的 task
                    for task in reversed(self.active_tasks):
                        if task.status == "active":
                            task.close("cancelled", ts=ts)
                            resolved.append(ResolvedMessage(
                                content=f"「{task.proposal_text}」已取消",
                                importance=0.6,
                                timestamp=ts,
                                role="user",
                                sources=[i],
                                task_id=task.task_id,
                            ))
                            break

                # 2b. 完成确认（有 active_task）
                elif self._is_completion(cleaned):
                    self.consumed.add(i)
                    # 关闭最近一个未完成 task
                    for task in reversed(self.active_tasks):
                        if task.status == "active":
                            task.close("completed", ts=ts)
                            resolved.append(ResolvedMessage(
                                content=f"「{task.proposal_text}」已完成",
                                importance=0.9,
                                timestamp=ts,
                                role="user",
                                sources=[i],
                                task_id=task.task_id,
                            ))
                            break

                # 2c. 确认批准（有 active_task 且尚未 approved）
                elif self._is_approval(cleaned):
                    self.consumed.add(i)
                    for task in reversed(self.active_tasks):
                        if task.status == "active" and not task.approved:
                            task.approved = True
                            task.approved_ts = ts
                            resolved.append(ResolvedMessage(
                                content=f"「{task.proposal_text}」已获批待执行",
                                importance=0.85,
                                timestamp=ts,
                                role="user",
                                sources=[i],
                                task_id=task.task_id,
                            ))
                            break

        # ── 3. 自然日边界：关闭未完成任务 ────────────────────────────────
        resolved.extend(self._expire_stale())

        return resolved

    def _expire_stale(self) -> list[ResolvedMessage]:
        """自然日边界：所有未完成任务输出『状态未知』"""
        resolved = []
        now = datetime.now(timezone.utc).isoformat()
        for task in self.active_tasks:
            if task.status == "active":
                task.close("expired", ts=now)
                resolved.append(ResolvedMessage(
                    content=task.closure_summary(),
                    importance=0.7,
                    timestamp=now,
                    role="system",
                    sources=[],
                    task_id=task.task_id,
                ))
        return resolved


# ── 工具函数 ───────────────────────────────────────────────────────────────

def read_session_messages(transcript_path: str, limit: int = 200) -> list[dict]:
    """从 transcript JSONL 读取消息列表"""
    messages = []
    try:
        with open(transcript_path) as f:
            for idx, line in enumerate(f):
                if idx >= limit:
                    break
                obj = json.loads(line.strip())
                if obj.get("type") != "message":
                    continue
                msg = obj.get("message", {})
                role = msg.get("role", "")
                if role not in ("user", "assistant"):
                    continue
                content = msg.get("content", [])
                text = ""
                if isinstance(content, list):
                    text = "".join(
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
                elif isinstance(content, str):
                    text = content
                if len(text.strip()) < 2:
                    continue
                messages.append({
                    "role": role,
                    "content": content,
                    "timestamp": obj.get("timestamp", ""),
                    "index": idx,
                })
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return messages


def resolve_transcript(transcript_path: str, limit: int = 200) -> list[ResolvedMessage]:
    """对单个 transcript 进行语义闭环解析"""
    messages = read_session_messages(transcript_path, limit=limit)
    resolver = DialogueContextResolver()
    return resolver.resolve(messages)


# ── 入口脚本 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DialogueContextResolver")
    parser.add_argument("--transcript", help="transcript JSONL 路径")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.transcript:
        results = resolve_transcript(args.transcript)
        for r in results:
            if args.json:
                print(json.dumps({
                    "content": r.content,
                    "importance": r.importance,
                    "timestamp": r.timestamp,
                    "role": r.role,
                    "task_id": r.task_id,
                }, ensure_ascii=False))
            else:
                print(f"[{r.timestamp[:19]}] [{r.role}] imp={r.importance} | {r.content}")
