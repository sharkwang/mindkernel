#!/usr/bin/env python3
"""
LLM-driven Topic Segmenter — 接口与启发式版完全对齐

Segmentation 策略：调用外部 LLM API 对话本进行语义切分。
支持任意兼容 OpenAI ChatCompletions 格式的 API。

与启发式 TopicSegmenter 对比：
  - 优点：理解语义边界，不依赖规则
  - 缺点：需要 LLM API，成本/延迟
  - 适用场景：topic 边界模糊、多个子话题交织的复杂对话
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]

# ── LLM 配置（可替换为任意 OpenAI-compatible API）────────────────────────────

LLM_CONFIG = {
    "api_base": "https://open.bigmodel.cn/api/coding/paas/v4",
    "api_key": "72a4bd2fc0ca4f31bc7a6364fd53071b.baux1N3EUUiM4eOS",
    "model": "glm-4.7",
}

SYSTEM_PROMPT = """你是一个对话主题分割专家。
分析下面的 AI 助手与用户的对话，按主题切分成多个片段。

规则：
1. 每个 topic 内的消息必须有语义连贯性（同一个任务或同一类讨论）
2. topic 切换点必须有明确的新话题出现（用户问了另一个问题、Agent提出了新的计划等）
3. 识别「任务型 topic」（含提案→执行→完成）和「信息型 topic」（分享→确认）
4. 每个 topic 生成简短摘要（≤20字）
5. 纯系统消息（heartbeat、retain通知）忽略，不作为独立topic
6. 只切分真正的语义边界，不要把同一个话题的讨论强行拆开

返回格式（严格JSON，不要包含其他内容）：
{
  "topics": [
    {
      "id": "topic_1",
      "description": "主题描述（≤15字中文）",
      "type": "task" | "info",
      "summary": "topic内容摘要（≤30字）",
      "start_ts": "HH:MM:SS",
      "end_ts": "HH:MM:SS",
      "message_indices": [0,1,2,3]
    }
  ]
}"""

USER_PROMPT_TEMPLATE = """分析以下对话，按主题切分：

{conversation}

请返回JSON格式的主题分割结果："""


# ── 数据结构（与启发式版完全对齐）─────────────────────────────────────────────

@dataclass
class TopicSegment:
    id: str
    description: str
    type: str
    summary: str
    start_ts: str
    end_ts: str
    message_indices: list[int]
    messages: list[dict] = field(default_factory=list)


@dataclass
class ComparisonResult:
    llm_segments: list[TopicSegment]
    heuristic_segments: list[TopicSegment]
    agreements: list[dict]   # [{topic_id, agreement_type, note}]
    disagreements: list[dict] # [{topic_a, topic_b, type, note}]
    recommendation: str


# ── LLM 调用 ──────────────────────────────────────────────────────────────

def call_llm(messages: list[dict], config: dict) -> str:
    """
    调用 LLM API，返回原始文本响应。
    支持 OpenAI-compatible 和 Anthropic 格式。
    """
    api_base = config.get("api_base", "").rstrip("/")
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o")

    # 构建消息
    prompt_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": messages},
    ]

    # OpenAI-compatible 格式
    if "/v1" in api_base or "/v4" in api_base or "openai" in api_base.lower():
        payload = {
            "model": model,
            "messages": prompt_messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{api_base}/chat/completions"
    else:
        # Anthropic 格式
        # 把 messages 转成 Anthropic 格式（取最后一组 user/assistant）
        anthropic_messages = []
        for m in messages:
            if isinstance(m, dict) and "role" in m:
                anthropic_messages.append({
                    "role": m["role"],
                    "content": m.get("content", m.get("text", "")),
                })
        payload = {
            "model": model,
            "messages": anthropic_messages[-10:],  # 最多10条
            "max_tokens": 4096,
            "temperature": 0.3,
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        endpoint = f"{api_base}/messages"

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read())

            # OpenAI 格式
            if "/chat/completions" in endpoint:
                return data["choices"][0]["message"]["content"]

            # Anthropic 格式
            if "content" in data and isinstance(data["content"], list):
                for block in data["content"]:
                    if block.get("type") == "text":
                        return block["text"]

            return str(data)

    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise RuntimeError(f"LLM API error {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")


def call_llm_curl(messages: list[dict], config: dict, timeout: int = 300) -> str:
    """
    使用 subprocess + curl 调用 LLM（某些环境 urllib 会超时）。
    """
    api_base = config.get("api_base", "").rstrip("/")
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o")

    prompt_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": messages},
    ]

    if "/v1" in api_base or "/v4" in api_base:
        payload = {
            "model": model,
            "messages": prompt_messages,
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        headers = ["-H", f"Authorization: Bearer {api_key}", "-H", "Content-Type: application/json"]
        endpoint = f"{api_base}/chat/completions"
    else:
        payload = {
            "model": model,
            "messages": prompt_messages[-10:],
            "max_tokens": 4096,
            "temperature": 0.3,
        }
        headers = ["-H", f"x-api-key: {api_key}", "-H", "anthropic-version: 2023-06-01", "-H", "Content-Type: application/json"]
        endpoint = f"{api_base}/messages"

    cmd = [
        "curl", "-s", "-X", "POST", endpoint,
        *headers,
        "-d", json.dumps(payload),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr[:200]}")

    data = json.loads(result.stdout)

    if "/chat/completions" in endpoint:
        return data["choices"][0]["message"]["content"]

    if "content" in data and isinstance(data["content"], list):
        for block in data["content"]:
            if block.get("type") == "text":
                return block["text"]

    return str(data)


# ── 解析 LLM 输出 ────────────────────────────────────────────────────────

def parse_llm_json_response(text: str) -> list[dict]:
    """从 LLM 输出中提取 JSON — 简化版"""
    text = text.strip()
    if not text:
        raise ValueError("Empty LLM response")
    # 去除 markdown code fence
    for fence in ["```json", "```json\n", "```"]:
        if text.startswith(fence):
            end_fence = text.find("```", len(fence))
            if end_fence >= 0:
                text = text[len(fence):end_fence].strip()
                break
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "topics" in data:
            return data["topics"]
        if isinstance(data, list):
            return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse: {e}\nText: {text[:300]}")
    return []


class TopicSegmenterLLM:
    """
    LLM 驱动的对话主题分割器。
    """

    def __init__(self, llm_config: Optional[dict] = None):
        self.llm_config = llm_config or {}
        self._counter = 0

    def build_conversation_text(self, messages: list[dict]) -> str:
        lines = []
        for i, m in enumerate(messages):
            role = "User" if m.get("role") == "user" else "Assistant"
            ts = m.get("timestamp", "")[11:19]
            content = m.get("content", "")
            if isinstance(content, list):
                content = "".join(
                    c.get("text", "") for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                )
            content = content.strip()
            if not content:
                continue
            if len(content) > 400:
                content = content[:400] + "..."
            lines.append(f"[{i}] [{ts}] {role}: {content}")
        return "\n".join(lines)

    def segment(self, messages: list[dict]) -> list[TopicSegment]:
        if not messages:
            return []
        if not self.llm_config:
            raise RuntimeError("LLM not configured.")
        conv_text = self.build_conversation_text(messages)
        prompt = USER_PROMPT_TEMPLATE.format(conversation=conv_text)
        try:
            raw = call_llm_curl(prompt, self.llm_config, timeout=300)
        except Exception:
            raw = call_llm(prompt, self.llm_config)
        raw_topics = parse_llm_json_response(raw)
        segments = []
        for rt in raw_topics:
            indices = rt.get("message_indices", [])
            if not indices:
                continue
            self._counter += 1
            topic_msgs = [messages[idx] for idx in indices if idx < len(messages)]
            ts_list = [m.get("timestamp", "") for m in topic_msgs]
            seg = TopicSegment(
                id=rt.get("id", f"topic_{self._counter}"),
                description=rt.get("description", "未知主题"),
                type=rt.get("type", "info"),
                summary=rt.get("summary", ""),
                start_ts=min(ts_list) if ts_list else "",
                end_ts=max(ts_list) if ts_list else "",
                message_indices=indices,
                messages=topic_msgs,
            )
            segments.append(seg)
        return segments



def compare_segmentations(
    llm_segs: list[TopicSegment],
    heuristic_segs: list[TopicSegment],
) -> ComparisonResult:
    """
    对比 LLM 分割和启发式分割的结果。
    """
    agreements = []
    disagreements = []

    # 简单对齐：用时间重叠率判断
    for ls in llm_segs:
        best_overlap = 0
        best_hs = None
        for hs in heuristic_segs:
            ls_set = set(ls.message_indices)
            hs_set = set(hs.message_indices)
            overlap = len(ls_set & hs_set)
            if overlap > best_overlap:
                best_overlap = overlap
                best_hs = hs

        if best_hs and best_overlap > 0:
            overlap_ratio = best_overlap / max(len(ls.message_indices), 1)
            if overlap_ratio >= 0.7:
                agreements.append({
                    "llm_topic": ls.id,
                    "heuristic_topic": best_hs.id,
                    "overlap_ratio": round(overlap_ratio, 2),
                    "note": f"双方分割一致，类型={'一致' if ls.type == best_hs.type else '不一致'}",
                })
            else:
                disagreements.append({
                    "llm_topic": ls.id,
                    "heuristic_topic": best_hs.id,
                    "overlap_ratio": round(overlap_ratio, 2),
                    "note": "分割边界有分歧",
                })

    # 统计
    llm_topic_count = len(llm_segs)
    heuristic_topic_count = len(heuristic_segs)

    if llm_topic_count > heuristic_topic_count:
        recommendation = "LLM 切得更细，适合复杂对话；启发式更粗，适合规则明确的对话。"
    elif llm_topic_count < heuristic_topic_count:
        recommendation = "LLM 合并了相关子话题；启发式按时间间隙切分更激进。"
    else:
        recommendation = "两者 topic 数量相近，对比语义质量。"

    return ComparisonResult(
        llm_segments=llm_segs,
        heuristic_segments=heuristic_segs,
        agreements=agreements,
        disagreements=disagreements,
        recommendation=recommendation,
    )


def print_comparison(comp: ComparisonResult):
    print(f"\n{'='*60}")
    print(f"LLM-Driven Topic Segmentation vs Heuristic")
    print(f"{'='*60}")
    print(f"\nLLM Segments ({len(comp.llm_segments)}):")
    for seg in comp.llm_segments:
        print(f"  [{seg.id}] {seg.description} ({seg.type})")
        print(f"    Time: {seg.start_ts[11:19] if seg.start_ts else '?'} → {seg.end_ts[11:19] if seg.end_ts else '?'}")
        print(f"    Summary: {seg.summary[:60]}")
        print(f"    Messages: {len(seg.message_indices)} 条 (indices {seg.message_indices})")

    print(f"\nHeuristic Segments ({len(comp.heuristic_segments)}):")
    for seg in comp.heuristic_segments:
        print(f"  [{seg.id}] {seg.description} ({seg.type})")
        print(f"    Time: {seg.start_ts[11:19] if seg.start_ts else '?'} → {seg.end_ts[11:19] if seg.end_ts else '?'}")
        print(f"    Summary: {seg.summary[:60]}")
        print(f"    Messages: {len(seg.message_indices)} 条 (indices {seg.message_indices})")

    print(f"\nComparison:")
    print(f"  Agreements: {len(comp.agreements)}")
    for a in comp.agreements:
        print(f"    ✓ {a['llm_topic']} ≈ {a['heuristic_topic']} (overlap={a['overlap_ratio']}) — {a['note']}")

    print(f"  Disagreements: {len(comp.disagreements)}")
    for d in comp.disagreements:
        print(f"    ✗ {d['llm_topic']} vs {d['heuristic_topic']} (overlap={d['overlap_ratio']}) — {d['note']}")

    print(f"\nRecommendation: {comp.recommendation}")


# ── 入口脚本 ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from topic_segmenter import TopicSegmenter as HeuristicSegmenter
    from dialogue_context_resolver import read_session_messages

    parser = argparse.ArgumentParser(description="LLM-driven Topic Segmenter")
    parser.add_argument("--transcript", help="transcript JSONL 路径")
    parser.add_argument("--config", help="LLM 配置文件路径（JSON）")
    parser.add_argument("--compare", action="store_true", help="同时运行启发式并对比")
    args = parser.parse_args()

    messages = []
    if args.transcript:
        messages = read_session_messages(args.transcript, limit=100)

    if not messages:
        print("No messages loaded. Provide --transcript path.")
        sys.exit(1)

    # LLM 配置
    llm_config = LLM_CONFIG
    if args.config:
        llm_config = json.loads(Path(args.config).read_text())
    else:
        # 尝试从环境变量读取
        import os
        if os.environ.get("LLM_API_BASE"):
            llm_config = {
                "api_base": os.environ["LLM_API_BASE"],
                "api_key": os.environ.get("LLM_API_KEY", ""),
                "model": os.environ.get("LLM_MODEL", "gpt-4o"),
            }

    if not llm_config:
        print("No LLM config. Use --config or set LLM_API_BASE, LLM_API_KEY, LLM_MODEL env vars.")
        print("\nComparison mode (with heuristic only):")
        seg = HeuristicSegmenter()
        segs = seg.segment(messages)
        print(f"\nHeuristic segments: {len(segs)}")
        for s in segs:
            print(f"  [{s.id}] {s.description} ({s.type}) | {len(s.messages)} msgs | {s.summary[:50]}")
        sys.exit(0)

    # LLM 分割
    segmenter = TopicSegmenterLLM(llm_config=llm_config)
    llm_segs = segmenter.segment(messages)

    if args.compare:
        heuristic = HeuristicSegmenter()
        h_segs = heuristic.segment(messages)
        comp = compare_segmentations(llm_segs, h_segs)
        print_comparison(comp)
    else:
        print(f"\nLLM Segments: {len(llm_segs)}")
        for s in llm_segs:
            print(f"  [{s.id}] {s.description} ({s.type})")
            print(f"    {s.start_ts[11:19] if s.start_ts else '?'} → {s.end_ts[11:19] if s.end_ts else '?'} | {len(s.messages)} msgs")
            print(f"    {s.summary[:80]}")
