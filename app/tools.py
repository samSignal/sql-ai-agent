"""Tools the agent can call, described with JSON Schema (the format OpenAI and Ollama both accept)."""
from __future__ import annotations

from typing import Any

from .db import Database, QueryError

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "List all tables in the database.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Show a table's columns, types, foreign keys, row count and 3 sample rows.",
            "parameters": {
                "type": "object",
                "properties": {"table": {"type": "string", "description": "Table name"}},
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Run ONE read-only SQLite SELECT query and return up to 50 rows.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "A single SQLite SELECT statement"}},
                "required": ["sql"],
            },
        },
    },
]


class ToolRunner:
    def __init__(self, db: Database):
        self.db = db

    def run(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Execute a tool. Returns (output_text, ok). Errors are returned, not raised,
        so the model sees them and can fix its query on the next step."""
        try:
            if name == "list_tables":
                return ", ".join(self.db.list_tables()), True
            if name == "describe_table":
                return self.db.describe_table(str(args.get("table", ""))), True
            if name == "run_sql":
                return self.db.run_sql(str(args.get("sql", ""))).to_text(), True
            return f"Unknown tool '{name}'", False
        except QueryError as e:
            return f"ERROR: {e}", False
