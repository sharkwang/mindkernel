#!/usr/bin/env python3
"""
Topic Segmenter — 启发式对话主题分割

阶段1（当前）：基于语义断点的启发式分割
  - 识别话题边界（用户问新问题、长时间间隔、明确的话题标签）
  - 为每个 segment 生成摘要

阶段2（预留）：LLM-driven 分割
  - 接口已定义（segment_with_llm）
  - 等待 LLM 调用路径打通后替换

输入：消息列表
输出：按 topic 分组，每组含 messages + summary + type
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# ── 断点检测模式 ──────────────────────────────────────────────────────────

# 新话题指示词（用户消息中出现 = 潜在话题切换）
NEW_TOPIC_PATTERNS = [
    re.compile(r"^(另外|还有|顺便|对了|话说)"),
    re.compile(r"^(那|那好|好的|好)[，,]"),
    re.compile(r"^(顺便|顺带)问"),
    # 明确的任务切换
    re.compile(r"^(先暂停|先停)"),
    re.compile(r"^(回到?|回到)"),
    # 明确的 QA 切换
    re.compile(r"^(那|那好)[，,]"),
]

# 用户问题类型 → 新 topic
QUESTION_STARTS = [
    re.compile(r"^[是否]"),
    re.compile(r"^[怎么|如何|为什么|啥|什么]"),
    re.compile(r"^有[没有]"),
    re.compile(r"^能不能"),
    re.compile(r"^请问"),
]

# 任务型提案指示词
TASK_PROPOSAL_PATTERNS = [
    re.compile(r"要不要"),
    re.compile(r"方案[是为]"),
    re.compile(r"可以这样"),
    re.compile(r"我来搞"),
    re.compile(r"第一步"),
    re.compile(r"分步"),
]

# 信息型指示词
INFO_PATTERNS = [
    re.compile(r"^(顺便|分享|告诉你|发现)"),
    re.compile(r"有个"),
    re.compile(r"刚才说到"),
]

# 执行动词（assistant 含这些词 → 即使无提案词也判 task）
EXECUTION_VERBS = [
    re.compile(r"^(修复|修改|更新|写入|创建|删除|重启|启动|停止|运行|执行|重置|加载|保存|编译|推送)"),
    re.compile(r"(修复|修改|写入|创建|删除|重启|启动|停止|运行|执行|重置|加载|保存|推送|完成|搞定)了"),
    re.compile(r"正在(修复|修改|运行|执行|重启|写入)"),
    re.compile(r"(搞定|完成|修复好|修好了|重启了|写入了|创建了|推送了)"),
]

# 系统类消息（不作为 topic 边界）
SYSTEM_PATTERNS = [
    re.compile(r"^System:"),
    re.compile(r"HEARTBEAT"),
    re.compile(r"\[retain\]"),
    re.compile(r"\[cron:"),
    re.compile(r"^—+$"),
]

# Telegram metadata 消息（不作为 topic 内容）
TELEGRAM_METADATA_PATTERNS = [
    re.compile(r"Conversation info"),
    re.compile(r'Sender \(untrusted metadata\)'),
    re.compile(r'^```json\s*\{'),
]


# ── 数据结构 ──────────────────────────────────────────────────────────────

@dataclass
class TopicSegment:
    id: str
    description: str      # 简短描述 ≤15字
    type: str            # task | info | qa
    summary: str         # 内容摘要 ≤30字
    start_ts: str
    end_ts: str
    messages: list[dict] = field(default_factory=list)
    message_indices: list[int] = field(default_factory=list)  # 兼容 LLM 版

    @property
    def duration_seconds(self) -> int:
        if not self.start_ts or not self.end_ts:
            return 0
        try:
            fmt = "%Y-%m-%dT%H:%M:%S"
            s = datetime.fromisoformat(self.start_ts.replace("Z", "+00:00"))
            e = datetime.fromisoformat(self.end_ts.replace("Z", "+00:00"))
            return int((e - s).total_seconds())
        except Exception:
            return 0


# ── 启发式分割器 ─────────────────────────────────────────────────────────

class TopicSegmenter:
    """
    基于语义断点的轻量 topic segmenter。

    分割策略：
    1. 识别 topic 边界（断点）
    2. 每段分配 topic type
    3. 生成摘要
    """

    # 连续消息最大时间间隔（秒），超过则视为新 topic
    MAX_GAP_SECONDS = 600  # 10 分钟

    def __init__(self):
        self._counter = 0

    def segment(self, messages: list[dict]) -> list[TopicSegment]:
        """
        输入：[{role, content, timestamp, index}, ...]
        输出：[TopicSegment, ...]
        """
        if not messages:
            return []

        # 预处理：去除纯系统消息
        clean = self._filter_system(messages)
        if not clean:
            return []

        # 识别边界
        boundaries = self._find_boundaries(clean)

        # 构建 segments
        segments = self._build_segments(clean, boundaries)

        return segments

    def _filter_system(self, messages: list[dict]) -> list[dict]:
        """过滤纯系统消息"""
        result = []
        for m in messages:
            text = self._extract_text(m.get("content", ""))
            if any(p.search(text) for p in SYSTEM_PATTERNS):
                continue
            # Telegram JSON metadata 消息：如果整个内容都是 metadata，尝试提取实际文本
            if any(p.search(text) for p in TELEGRAM_METADATA_PATTERNS):
                cleaned = self._extract_telegram_text(text)
                if cleaned:
                    # 替换 content 后保留
                    m = dict(m)  # copy
                    m["content"] = [{"type": "text", "text": cleaned}]
                    result.append(m)
                continue
            result.append(m)
        return result

    def _extract_telegram_text(self, raw: str) -> str:
        """从 Telegram 元数据包装中提取实际用户消息"""
        fences = [i for i, ch in enumerate(raw) if raw[i:i+3] == "```"]
        if len(fences) >= 2:
            last_fence_end = fences[-1] + 3
            candidate = raw[last_fence_end:].strip()
            for sep in ["\nSender", "\n\nSender", "Sender (untrusted"]:
                idx = candidate.find(sep)
                if idx >= 0:
                    candidate = candidate[:idx].strip()
            # 清理残留 JSON 行
            lines = candidate.split("\n")
            clean_lines = []
            for line in lines:
                s = line.strip()
                if not s:
                    continue
                try:
                    json.loads(s)
                    continue
                except (ValueError, json.JSONDecodeError):
                    pass
                if any(k in s for k in ["Conversation info", "Sender (untrusted",
                                         "message_id", "timestamp", "sender_id",
                                         "```json", "```"]):
                    continue
                clean_lines.append(s)
            result = " ".join(clean_lines).strip()
            if len(result) >= 2:
                return result
        # 回退：直接移除 metadata 行
        lines = raw.split("\n")
        clean = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            try:
                json.loads(s)
                continue
            except (ValueError, json.JSONDecodeError):
                pass
            if any(k in s for k in ["Conversation info", "Sender (untrusted",
                                     "message_id", "timestamp", "sender_id",
                                     "```json", "```"]):
                continue
            clean.append(s)
        return " ".join(clean).strip()

    def _extract_text(self, content) -> str:
        if isinstance(content, list):
            return "".join(
                c.get("text", "") for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
        return str(content) if content else ""

    def _find_boundaries(self, messages: list[dict]) -> list[int]:
        """
        返回 boundary indices（分割点）。
        """
        boundaries = [0]
        last_ts: Optional[datetime] = None
        last_was_task_proposal = False

        for i, m in enumerate(messages):
            text = self._extract_text(m.get("content", ""))
            ts_str = m.get("timestamp", "")
            role = m.get("role", "")

            # 时间间隔断点
            if last_ts and ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = ts.astimezone(timezone.utc)
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    gap = (ts - last_ts).total_seconds()
                    if gap > self.MAX_GAP_SECONDS:
                        boundaries.append(i)
                        last_was_task_proposal = False
                except Exception:
                    pass

            last_ts_str = m.get("timestamp", "")
            if last_ts_str:
                try:
                    last_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
                    last_ts = last_ts.astimezone(timezone.utc)
                except Exception:
                    pass

            # 新话题指示词断点（user 消息）
            if role == "user":
                for pat in NEW_TOPIC_PATTERNS:
                    if pat.search(text.strip()):
                        if i > 0 and i not in boundaries:
                            boundaries.append(i)
                            last_was_task_proposal = False
                            break

            # 问题开头（新 QA topic）
            if role == "user":
                for pat in QUESTION_STARTS:
                    if pat.search(text.strip()):
                        if i > 0 and i not in boundaries:
                            boundaries.append(i)
                            last_was_task_proposal = False
                            break

            # 任务型提案出现 → 新 topic
            if role == "assistant":
                is_proposal = any(p.search(text) for p in TASK_PROPOSAL_PATTERNS)
                if is_proposal and not last_was_task_proposal:
                    if i > 0 and i not in boundaries:
                        boundaries.append(i)
                        last_was_task_proposal = True

        return sorted(set(boundaries))
        """
        返回 boundary indices（分割点）。
        索引 i 表示 messages[i] 是新 topic 的第一条消息。
        第一个 segment 从 0 开始。
        """
        boundaries = [0]
        last_ts: Optional[datetime] = None
        last_role = ""
        last_was_task_proposal = False

        for i, m in enumerate(messages):
            text = self._extract_text(m.get("content", ""))
            ts_str = m.get("timestamp", "")
            role = m.get("role", "")

            # 时间间隔断点
            if last_ts and ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    ts = ts.astimezone(timezone.utc)
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    gap = (ts - last_ts).total_seconds()
                    if gap > self.MAX_GAP_SECONDS:
                        boundaries.append(i)
                        last_was_task_proposal = False
                except Exception:
                    pass

            last_ts_str = m.get("timestamp", "")
            if last_ts_str:
                try:
                    last_ts = datetime.fromisoformat(last_ts_str.replace("Z", "+00:00"))
                    last_ts = last_ts.astimezone(timezone.utc)
                except Exception:
                    pass

            # 新话题指示词断点（user 消息）
            if role == "user":
                for pat in NEW_TOPIC_PATTERNS:
                    if pat.search(text.strip()):
                        if i > 0 and i not in boundaries:
                            boundaries.append(i)
                            last_was_task_proposal = False
                            break

            # 问题开头（新 QA topic）
            if role == "user":
                for pat in QUESTION_STARTS:
                    if pat.search(text.strip()):
                        if i > 0 and i not in boundaries:
                            boundaries.append(i)
                            last_was_task_proposal = False
                            break

            # 任务型提案出现 → 新 topic
            if role == "assistant":
                is_proposal = any(p.search(text) for p in TASK_PROPOSAL_PATTERNS)
                if is_proposal and not last_was_task_proposal:
                    if i > 0 and i not in boundaries:
                        boundaries.append(i)
                        last_was_task_proposal = True

            last_role = role

        return sorted(set(boundaries))

    def _build_segments(self, messages: list[dict], boundaries: list[int]) -> list[TopicSegment]:
        """根据边界构建 TopicSegment"""
        segments = []
        n = len(messages)

        for bi, start_idx in enumerate(boundaries):
            end_idx = boundaries[bi + 1] if bi + 1 < len(boundaries) else n
            chunk = messages[start_idx:end_idx]

            if not chunk:
                continue

            self._counter += 1
            ts_list = [m.get("timestamp", "") for m in chunk]
            desc, seg_type = self._classify(chunk)
            summary = self._summarize(chunk)

            seg = TopicSegment(
                id=f"seg_{self._counter:03d}",
                description=desc,
                type=seg_type,
                summary=summary,
                start_ts=min(ts_list),
                end_ts=max(ts_list),
                messages=chunk,
                message_indices=[start_idx + i for i in range(len(chunk))],
            )
            segments.append(seg)

        return segments

    def _classify(self, messages: list[dict]) -> tuple[str, str]:
        """判断 topic type 并生成简短描述"""
        # 统计角色分布
        roles = [m.get("role", "") for m in messages]
        user_count = roles.count("user")
        assistant_count = roles.count("assistant")

        all_text = " ".join(self._extract_text(m.get("content", "")) for m in messages)

        # 任务型：含提案关键词
        if any(p.search(all_text) for p in TASK_PROPOSAL_PATTERNS):
            if "同意" in all_text or "可以" in all_text or "行" in all_text:
                return "任务执行", "task"
            return "任务讨论", "task"

        # 执行型：无提案词但含执行动词 → task
        # （对应 LLM 检测到的"结论式汇报"场景）
        if any(p.search(all_text) for p in EXECUTION_VERBS):
            return "任务执行", "task"

        # QA 型：用户多问句
        question_count = sum(
            1 for m in messages
            if m.get("role") == "user"
            and any(p.search(self._extract_text(m.get("content", "")).strip())
                    for p in QUESTION_STARTS)
        )
        if question_count >= 1 and user_count >= 2:
            return "问答讨论", "qa"

        # 信息型：assistant 长回复为主
        if assistant_count > user_count:
            return "信息分享", "info"

        return "一般对话", "info"

    def _summarize(self, messages: list[dict]) -> str:
        """生成 topic 摘要（取用户消息的核心内容）"""
        user_msgs = [
            self._extract_text(m.get("content", "")).strip()
            for m in messages
            if m.get("role") == "user"
        ]
        if not user_msgs:
            return "Assistant 回复"

        # 取第一条用户消息的前80字
        first = user_msgs[0]
        if len(first) > 80:
            # 在句号或逗号处截断
            for cut in ["。", ".", "，", ","]:
                idx = first[:60].rfind(cut)
                if idx > 10:
                    first = first[:idx + 1]
                    break
            else:
                first = first[:80] + "..."

        # 清理格式标记
        first = re.sub(r"\[\[reply_to[^\]]*\]\]\s*", "", first)
        first = re.sub(r"Conversation info.*?```\s*", "", first, flags=re.DOTALL)
        first = re.sub(r"Sender.*?```\s*", "", first, flags=re.DOTALL)
        return first.strip()[:100]


# ── 入口脚本 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from dialogue_context_resolver import read_session_messages

    parser = argparse.ArgumentParser(description="TopicSegmenter")
    parser.add_argument("--transcript", help="transcript JSONL 路径")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    if args.transcript:
        messages = read_session_messages(args.transcript)
        print(f"[TopicSegmenter] {len(messages)} messages loaded")

        segmenter = TopicSegmenter()
        segments = segmenter.segment(messages)
        print(f"\n=== {len(segments)} Topics ===\n")

        for seg in segments:
            if args.json:
                print(json.dumps({
                    "id": seg.id,
                    "description": seg.description,
                    "type": seg.type,
                    "summary": seg.summary,
                    "start": seg.start_ts[11:19] if seg.start_ts else "",
                    "end": seg.end_ts[11:19] if seg.end_ts else "",
                    "msg_count": len(seg.messages),
                }, ensure_ascii=False))
            else:
                print(f"[{seg.id}] {seg.description} ({seg.type})")
                print(f"  {seg.start_ts[11:19] if seg.start_ts else '?'} → {seg.end_ts[11:19] if seg.end_ts else '?'} | {len(seg.messages)} msgs")
                print(f"  {seg.summary[:100]}")
                print()
