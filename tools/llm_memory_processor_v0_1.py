#!/usr/bin/env python3
"""Core object for external-LLM-based memory processing (v0.1)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from schema_runtime import validate_payload


@dataclass
class LLMProcessorConfig:
    backend: str = "openai_compatible"  # openai_compatible | mock
    endpoint: str = "https://api.openai.com/v1/chat/completions"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_sec: int = 45
    temperature: float = 0.1
    max_tokens: int = 1200


class LLMProcessorError(RuntimeError):
    pass


class LLMMemoryProcessor:
    """Core object for memory extraction via external LLM calls."""

    def __init__(self, config: LLMProcessorConfig):
        self.config = config

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def in_days_iso(days: int) -> str:
        return (
            datetime.now(timezone.utc) + timedelta(days=days)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _source_type(source_ref: str) -> str:
        s = source_ref.lower()
        if s.startswith("session://") or s.startswith("msg://"):
            return "session"
        if s.startswith("file://") or ".md" in s or "/" in source_ref:
            return "file"
        if s.startswith("tool://"):
            return "tool"
        return "external"

    @staticmethod
    def _stable_id(source_ref: str, content: str) -> str:
        h = hashlib.sha1(f"{source_ref}|{content}".encode("utf-8")).hexdigest()[:12]
        return f"mem_llm_{h}"

    @staticmethod
    def _parse_json_text(text: str) -> dict:
        if not text:
            raise LLMProcessorError("empty model output")

        # 1) direct JSON
        try:
            return json.loads(text)
        except Exception:
            pass

        # 2) fenced JSON block
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
        if m:
            return json.loads(m.group(1))

        raise LLMProcessorError("model output is not valid JSON")

    @staticmethod
    def _normalize_model_content(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            out = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    out.append(str(part.get("text", "")))
            return "\n".join(out)
        return str(content)

    def _openai_compatible_chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        api_key = os.getenv(self.config.api_key_env)
        if not api_key:
            raise LLMProcessorError(f"missing API key in env: {self.config.api_key_env}")

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        req = urllib.request.Request(
            self.config.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            raise LLMProcessorError(f"LLM HTTP error: {e.code} {detail}") from e
        except Exception as e:
            raise LLMProcessorError(f"LLM request failed: {e}") from e

        try:
            raw = json.loads(body)
            content = raw["choices"][0]["message"]["content"]
            text = self._normalize_model_content(content)
            return self._parse_json_text(text)
        except Exception as e:
            raise LLMProcessorError(f"invalid LLM response: {e}") from e

    @staticmethod
    def _mock_chat_json(raw_text: str, max_items: int) -> dict:
        lines = [x.strip() for x in raw_text.splitlines() if x.strip()]
        candidates = []

        for line in lines:
            if line.startswith("-") or line.startswith("*"):
                line = line[1:].strip()

            if len(line) < 8:
                continue

            kind = "event" if re.search(r"完成|开始|继续|请求|blocked|pass|failed|done", line, re.IGNORECASE) else "fact"
            confidence = 0.88 if kind == "event" else 0.8
            impact_tier = "high" if re.search(r"P0|高风险|critical|block", line, re.IGNORECASE) else "medium"
            risk_tier = "low"

            candidates.append(
                {
                    "kind": kind,
                    "content": line,
                    "confidence": confidence,
                    "risk_tier": risk_tier,
                    "impact_tier": impact_tier,
                }
            )

            if len(candidates) >= max_items:
                break

        return {"memory_items": candidates}

    def _extract_candidates(self, raw_text: str, max_items: int) -> dict:
        if self.config.backend == "mock":
            return self._mock_chat_json(raw_text, max_items=max_items)

        if self.config.backend != "openai_compatible":
            raise LLMProcessorError(f"unsupported backend: {self.config.backend}")

        system_prompt = (
            "你是 MindKernel 的记忆抽取引擎。"
            "把输入文本抽取为结构化 memory_items。"
            "仅输出 JSON 对象，格式为{\"memory_items\":[...]}。"
            "每个 item 必须包含: kind(event|fact), content, confidence(0-1), risk_tier(low|medium|high), impact_tier(low|medium|high|critical)。"
            "禁止输出解释性文本。"
        )
        user_prompt = (
            f"最大输出条数: {max_items}\n"
            "请抽取最有长期价值且可审计的记忆候选。\n"
            "输入文本如下：\n"
            f"{raw_text}"
        )
        return self._openai_compatible_chat_json(system_prompt, user_prompt)

    def extract_memory_objects(
        self,
        *,
        raw_text: str,
        source_ref: str,
        status: str = "candidate",
        review_due_days: int = 7,
        next_action_days: int = 7,
        max_items: int = 5,
    ) -> dict:
        extracted = self._extract_candidates(raw_text, max_items=max_items)
        items = extracted.get("memory_items")
        if not isinstance(items, list):
            raise LLMProcessorError("LLM output missing `memory_items` list")

        source_type = self._source_type(source_ref)
        seen = set()
        out = []

        for raw in items:
            if not isinstance(raw, dict):
                continue

            kind = str(raw.get("kind", "fact")).lower()
            if kind not in {"event", "fact"}:
                kind = "fact"

            content = str(raw.get("content", "")).strip()
            if not content:
                continue

            dedupe_key = content.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            confidence = float(raw.get("confidence", 0.75))
            confidence = max(0.0, min(1.0, confidence))

            risk_tier = str(raw.get("risk_tier", "low")).lower()
            if risk_tier not in {"low", "medium", "high"}:
                risk_tier = "low"

            impact_tier = str(raw.get("impact_tier", "medium")).lower()
            if impact_tier not in {"low", "medium", "high", "critical"}:
                impact_tier = "medium"

            obj = {
                "id": self._stable_id(source_ref, content),
                "kind": kind,
                "content": content,
                "source": {
                    "source_type": source_type,
                    "source_ref": source_ref,
                },
                "evidence_refs": [source_ref],
                "confidence": confidence,
                "risk_tier": risk_tier,
                "impact_tier": impact_tier,
                "status": status,
                "created_at": self.now_iso(),
                "review_due_at": self.in_days_iso(max(0, int(review_due_days))),
                "next_action_at": self.in_days_iso(max(0, int(next_action_days))),
                "migration_meta": {
                    "generated_by": "llm_memory_processor_v0_1",
                    "backend": self.config.backend,
                    "model": self.config.model,
                    "task": "extract_memory",
                },
            }

            validate_payload("memory.schema.json", obj)
            out.append(obj)

        return {
            "ok": True,
            "backend": self.config.backend,
            "model": self.config.model,
            "source_ref": source_ref,
            "count": len(out),
            "memory_items": out,
        }


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description="LLM memory processor core object demo (v0.1)")
    p.add_argument("--backend", default="mock", choices=["mock", "openai_compatible"])
    p.add_argument("--endpoint", default="https://api.openai.com/v1/chat/completions")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--api-key-env", default="OPENAI_API_KEY")
    p.add_argument("--timeout-sec", type=int, default=45)
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument("--max-tokens", type=int, default=1200)
    p.add_argument("--source-ref", required=True)

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--text-file")

    p.add_argument("--status", default="candidate")
    p.add_argument("--review-due-days", type=int, default=7)
    p.add_argument("--next-action-days", type=int, default=7)
    p.add_argument("--max-items", type=int, default=5)
    p.add_argument("--out")
    p.add_argument("--jsonl-out")
    args = p.parse_args()

    raw_text = args.text
    if args.text_file:
        raw_text = Path(args.text_file).read_text(errors="ignore")

    cfg = LLMProcessorConfig(
        backend=args.backend,
        endpoint=args.endpoint,
        model=args.model,
        api_key_env=args.api_key_env,
        timeout_sec=max(1, int(args.timeout_sec)),
        temperature=float(args.temperature),
        max_tokens=max(1, int(args.max_tokens)),
    )

    processor = LLMMemoryProcessor(cfg)
    out = processor.extract_memory_objects(
        raw_text=raw_text or "",
        source_ref=args.source_ref,
        status=args.status,
        review_due_days=max(0, int(args.review_due_days)),
        next_action_days=max(0, int(args.next_action_days)),
        max_items=max(1, int(args.max_items)),
    )

    if args.out:
        pth = Path(args.out).expanduser().resolve()
        pth.parent.mkdir(parents=True, exist_ok=True)
        pth.write_text(json.dumps(out, ensure_ascii=False, indent=2))

    if args.jsonl_out:
        write_jsonl(Path(args.jsonl_out).expanduser().resolve(), out.get("memory_items", []))

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
