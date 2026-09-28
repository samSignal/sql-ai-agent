# SQL AI Agent

![tests](https://github.com/samSignal/sql-ai-agent/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

An **AI agent that answers business questions in plain English by exploring and querying a SQL database**. Ask *"Which 5 products earned the most revenue?"*: the agent looks up the schema, writes the SQL, runs it, fixes its own errors, and replies with the answer **and the exact query it used**, so the result can be checked.

Built with Python, FastAPI and LLM tool calling (OpenAI or a free local model through Ollama). Every query is **read-only** by design; see [Safety](#safety).

## How it works

```
question ─► LLM ─► tool call ─► result ─► LLM ─► tool call ─► ... ─► final answer + SQL
                     │
                     ├─ list_tables       what tables exist?
                     ├─ describe_table    columns, types, foreign keys, sample rows
                     └─ run_sql           one read-only SELECT (errors go back to the LLM to fix)
```

The loop runs for up to `MAX_STEPS` steps. The UI and API return every step (tool, arguments, output), so you can see how the agent reached its answer.

Example trace against the sample database (the tool outputs are real; the model's wording varies by model):

```text
1. list_tables()                     → customers, order_items, orders, products
2. describe_table("order_items")     → Table order_items (702 rows) ... product_id -> products.id
3. run_sql("SELECT name, SUM(total) FROM products")
                                     → ERROR: SQL error: no such column: total
4. run_sql("SELECT p.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue
            FROM order_items oi JOIN products p ON p.id = oi.product_id
            JOIN orders o ON o.id = oi.order_id WHERE o.status != 'cancelled'
            GROUP BY p.name ORDER BY revenue DESC LIMIT 5")
                                     → Standing Desk | 40135.0
                                       Noise-Cancelling Headphones | 21009.0
                                       Office Chair | 20601.0 ...
Answer: The top product is the Standing Desk (40,135), followed by ...
```

| File | Responsibility |
|---|---|
| `app/agent.py` | The agent loop: calls the model, runs tools, feeds results back, stops at a final answer or the step limit |
| `app/tools.py` | Tool definitions (JSON Schema) and dispatch; errors are returned to the model so it can self-correct |
| `app/db.py` | Read-only SQLite access with an authorizer, statement validation, row cap and query timeout |
| `app/llm.py` | OpenAI and Ollama adapters that share one message format |
| `app/main.py` | FastAPI endpoints and the web UI |
| `seed.py` | Builds a reproducible sample shop database (customers, products, orders, order items) |

## Quick start

```bash
git clone https://github.com/samSignal/sql-ai-agent.git
cd sql-ai-agent
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then add your OPENAI_API_KEY, or switch to Ollama (below)
uvicorn app.main:app --reload
```

Open http://localhost:8000 and click one of the example questions. The sample database is created automatically on first run (or with `python seed.py`). The API docs are at http://localhost:8000/docs.

**Free local model instead of OpenAI:** install [Ollama](https://ollama.com), run `ollama pull qwen2.5:7b`, then set `LLM_PROVIDER=ollama` in `.env`. The model you choose must support tool calling (e.g. qwen2.5, llama3.1+, mistral-nemo).

**Your own database:** point `DB_PATH` at any SQLite file.

### CLI and Docker

```bash
python cli.py -v "What share of orders were cancelled?"   # -v prints every agent step
docker build -t sql-ai-agent . && docker run -p 8000:8000 --env-file .env sql-ai-agent
```

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/ask` | `{"question": "..."}` → `answer`, `sql`, `steps[]`, `model`, `latency_ms` |
| `GET` | `/schema` | Description of every table |
| `GET` | `/health` | Active model and tables |

## Safety

Handing an LLM a database connection is risky, so the agent's access is locked down in several independent layers:

1. **Read-only connection**: the SQLite file is opened with `mode=ro`.
2. **SQLite authorizer**: the engine denies every operation except reads (INSERT, UPDATE, DELETE, DROP, ATTACH and write PRAGMAs are all refused, even inside a `WITH` clause).
3. **Statement validation**: only a single `SELECT` / `WITH` statement is accepted.
4. **Resource limits**: queries are killed after `QUERY_TIMEOUT_S`, results are capped at `MAX_ROWS`, tool output sent back to the model is truncated, and the loop stops after `MAX_STEPS`.

The tests check each layer, for example that `WITH x AS (SELECT 1) DELETE FROM orders` gets past the text check but is blocked by the engine.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

26 tests, run by GitHub Actions on every push, with no API key needed:
- **Agent loop**: a scripted stand-in model drives multi-step runs, including recovering from a SQL error, refusing writes, and the step limit.
- **LLM adapters**: the OpenAI adapter (using the real `openai` SDK) and the Ollama adapter are tested against local fake HTTP servers, which checks request and response formats.
- **Database safety**: writes, multi-statements, ATTACH, hidden CTE writes, a runaway recursive query that must time out, and row truncation.
- **API**: endpoints, validation, and a clean 502 when the model backend is down.

## Possible next steps

PostgreSQL/MySQL support through SQLAlchemy, charts for numeric results, conversation memory for follow-up questions, and an evaluation set of questions with known answers to measure accuracy across models.

## License

MIT. The sample data is randomly generated and fictional.
