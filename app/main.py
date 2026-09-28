"""FastAPI app: ask questions in plain English, get answers plus the SQL and every agent step."""
from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .agent import SQLAgent
from .config import get_settings
from .db import Database
from .llm import get_model

app = FastAPI(title="SQL AI Agent", version="1.0.0",
              description="An LLM agent that answers business questions by exploring and querying a SQL database.")


@lru_cache
def get_agent() -> SQLAgent:
    s = get_settings()
    if not Path(s.db_path).exists() and s.db_path == "data/shop.db":
        from seed import build  # first run: create the sample database

        build(s.db_path)
    return SQLAgent(Database(s.db_path, s.max_rows, s.query_timeout_s), get_model(s), s.max_steps)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, examples=["Which 5 products earned the most revenue?"])


@app.get("/", include_in_schema=False)
def ui() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health() -> dict:
    agent = get_agent()
    return {"status": "ok", "model": agent.model.name, "tables": agent.db.list_tables()}


@app.get("/schema")
def schema() -> dict:
    db = get_agent().db
    return {t: db.describe_table(t) for t in db.list_tables()}


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    try:
        return asdict(get_agent().ask(req.question))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:  # model/network errors
        raise HTTPException(502, f"Model backend error: {e}") from e
