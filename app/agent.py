"""The agent loop: the model plans, calls tools, reads results, fixes errors, and answers."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .db import Database
from .llm import ChatModel
from .tools import TOOL_SPECS, ToolRunner

SYSTEM_PROMPT = """You are a careful data analyst working with a SQLite database.
Answer the user's question using the tools:
1. Use list_tables and describe_table to learn the schema. Never guess table or column names.
2. Write ONE read-only SQLite SELECT with run_sql. Prefer aggregates (SUM, COUNT, AVG) over fetching raw rows.
3. If a query returns an ERROR, read it, fix the query and try again.
4. When you have the data, reply in plain English with the key numbers, then a line "SQL used:" with the final query.
If the question cannot be answered from this database, say so. Never invent numbers."""


@dataclass
class Step:
    tool: str
    args: dict
    output: str
    ok: bool


@dataclass
class AgentResult:
    question: str
    answer: str
    sql: str | None = None
    steps: list[Step] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0


class SQLAgent:
    def __init__(self, db: Database, model: ChatModel, max_steps: int = 8):
        self.db = db
        self.model = model
        self.tools = ToolRunner(db)
        self.max_steps = max_steps

    def ask(self, question: str) -> AgentResult:
        start = time.perf_counter()
        question = question.strip()
        if not question:
            raise ValueError("Question must not be empty")

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        steps: list[Step] = []
        last_sql: str | None = None

        for _ in range(self.max_steps):
            reply = self.model.chat(messages, TOOL_SPECS)
            if not reply.tool_calls:  # the model is done
                return AgentResult(question, reply.content.strip(), last_sql, steps, self.model.name,
                                   int((time.perf_counter() - start) * 1000))

            messages.append({
                "role": "assistant",
                "content": reply.content or None,
                "tool_calls": [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.args)}}
                    for c in reply.tool_calls
                ],
            })
            for call in reply.tool_calls:
                output, ok = self.tools.run(call.name, call.args)
                steps.append(Step(call.name, call.args, output, ok))
                if call.name == "run_sql" and ok:
                    last_sql = call.args.get("sql")
                # Cap what goes back into the context window
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output[:4000]})

        return AgentResult(question, f"Stopped after {self.max_steps} steps without a final answer. "
                           "Try rephrasing the question more specifically.", last_sql, steps, self.model.name,
                           int((time.perf_counter() - start) * 1000))
