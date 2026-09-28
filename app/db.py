"""Safe, read-only access to a SQLite database for the agent.

Three independent layers stop the model from changing data:
1. the file is opened with SQLite's read-only URI mode (`mode=ro`),
2. an authorizer callback denies every action except reads and a few safe functions,
3. only a single SELECT / WITH statement is accepted.
A progress handler aborts long-running queries, and results are capped at `max_rows`.
"""
from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                    getattr(sqlite3, "SQLITE_RECURSIVE", 33)}  # recursive CTEs
_ALLOWED_PRAGMAS = {"table_info", "foreign_key_list", "index_list"}


class QueryError(Exception):
    """Raised for rejected or failed queries. The message is shown to the model so it can self-correct."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool

    def to_text(self) -> str:
        if not self.rows:
            return "(no rows)"
        lines = [" | ".join(self.columns)]
        lines += [" | ".join("NULL" if v is None else str(v) for v in r) for r in self.rows]
        if self.truncated:
            lines.append(f"... (truncated to {len(self.rows)} rows; add LIMIT or aggregate)")
        return "\n".join(lines)


class Database:
    def __init__(self, path: str, max_rows: int = 50, timeout_s: float = 5.0):
        if not Path(path).exists():
            raise FileNotFoundError(f"Database not found: {path} (run `python seed.py` to create the sample DB)")
        self.path = path
        self.max_rows = max_rows
        self.timeout_s = timeout_s

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{Path(self.path).resolve()}?mode=ro", uri=True, check_same_thread=False)
        conn.set_authorizer(self._authorizer)
        return conn

    @staticmethod
    def _authorizer(action, arg1, arg2, dbname, source):
        if action in _ALLOWED_ACTIONS:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_PRAGMA and arg1 in _ALLOWED_PRAGMAS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    # ---------- schema tools ----------
    def list_tables(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]

    def describe_table(self, table: str) -> str:
        if table not in self.list_tables():
            raise QueryError(f"Unknown table '{table}'. Available: {', '.join(self.list_tables())}")
        with self._connect() as conn:
            cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            fks = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            sample = conn.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()
            count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        lines = [f"Table {table} ({count} rows)", "Columns:"]
        lines += [f"  {c[1]} {c[2]}{' PRIMARY KEY' if c[5] else ''}{' NOT NULL' if c[3] else ''}" for c in cols]
        if fks:
            lines.append("Foreign keys:")
            lines += [f"  {fk[3]} -> {fk[2]}.{fk[4]}" for fk in fks]
        lines.append("Sample rows:")
        lines += [f"  {tuple(r)}" for r in sample]
        return "\n".join(lines)

    # ---------- query tool ----------
    @staticmethod
    def validate(sql: str) -> str:
        cleaned = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql, flags=re.S).strip().rstrip(";").strip()
        if not cleaned:
            raise QueryError("Empty query")
        if ";" in cleaned:
            raise QueryError("Only one statement is allowed")
        if not re.match(r"(?is)^(select|with)\b", cleaned):
            raise QueryError("Only read-only SELECT (or WITH ... SELECT) queries are allowed")
        return cleaned

    def run_sql(self, sql: str) -> QueryResult:
        query = self.validate(sql)
        conn = self._connect()
        deadline = time.monotonic() + self.timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cur = conn.execute(query)
            rows = cur.fetchmany(self.max_rows + 1)
            columns = [d[0] for d in cur.description or []]
        except sqlite3.DatabaseError as e:
            msg = "Query timed out" if "interrupted" in str(e) else f"SQL error: {e}"
            raise QueryError(msg) from e
        finally:
            conn.close()
        return QueryResult(columns, [tuple(r) for r in rows[: self.max_rows]], len(rows) > self.max_rows)
