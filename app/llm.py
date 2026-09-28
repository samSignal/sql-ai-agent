"""Chat-model backends with tool calling. Messages are kept in the OpenAI chat format internally."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from .config import Settings


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class Reply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    name: str

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply: ...


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


class OpenAIChat:
    def __init__(self, settings: Settings):
        from openai import OpenAI

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set (or use LLM_PROVIDER=ollama)")
        kwargs = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self.client = OpenAI(**kwargs)
        self.model = settings.openai_model
        self.name = f"openai:{self.model}"

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        resp = self.client.chat.completions.create(model=self.model, messages=messages, tools=tools, temperature=0)
        msg = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, _parse_args(tc.function.arguments)) for tc in (msg.tool_calls or [])]
        return Reply(msg.content or "", calls)


class OllamaChat:
    """Ollama's /api/chat supports tools for models such as qwen2.5, llama3.1+ and mistral-nemo."""

    def __init__(self, settings: Settings):
        self.url = settings.ollama_url.rstrip("/")
        self.model = settings.ollama_model
        self.name = f"ollama:{self.model}"

    @staticmethod
    def _to_ollama(messages: list[dict]) -> list[dict]:
        out = []
        names = {}  # tool_call_id -> tool name (Ollama wants the name, OpenAI wants the id)
        for m in messages:
            if m["role"] == "assistant" and m.get("tool_calls"):
                names.update({tc["id"]: tc["function"]["name"] for tc in m["tool_calls"]})
                out.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": [
                        {"function": {"name": tc["function"]["name"], "arguments": json.loads(tc["function"]["arguments"])}}
                        for tc in m["tool_calls"]
                    ],
                })
            elif m["role"] == "tool":
                out.append({"role": "tool", "content": m["content"], "tool_name": names.get(m.get("tool_call_id"), "")})
            else:
                out.append({"role": m["role"], "content": m.get("content") or ""})
        return out

    def chat(self, messages: list[dict], tools: list[dict]) -> Reply:
        resp = requests.post(
            f"{self.url}/api/chat",
            json={"model": self.model, "messages": self._to_ollama(messages), "tools": tools,
                  "stream": False, "options": {"temperature": 0}},
            timeout=300,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
        calls = [
            ToolCall(f"call_{uuid.uuid4().hex[:8]}", tc["function"]["name"], _parse_args(tc["function"].get("arguments")))
            for tc in msg.get("tool_calls") or []
        ]
        return Reply(msg.get("content") or "", calls)


def get_model(settings: Settings) -> ChatModel:
    if settings.llm_provider.lower() == "ollama":
        return OllamaChat(settings)
    return OpenAIChat(settings)
