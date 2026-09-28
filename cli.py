"""Command-line interface.

    python cli.py "Which 5 products earned the most revenue?"
    python cli.py            # interactive mode
    python cli.py -v "..."   # also print every agent step
"""
from __future__ import annotations

import argparse
from pathlib import Path

from app.agent import SQLAgent
from app.config import get_settings
from app.db import Database
from app.llm import get_model
from seed import build


def show(agent: SQLAgent, q: str, verbose: bool) -> None:
    r = agent.ask(q)
    if verbose:
        for i, s in enumerate(r.steps, 1):
            print(f"--- step {i}: {s.tool} {s.args} {'' if s.ok else '(error)'}\n{s.output}\n")
    print(f"\n{r.answer}\n")


def main() -> None:
    p = argparse.ArgumentParser(description="SQL AI Agent CLI")
    p.add_argument("question", nargs="?")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    s = get_settings()
    if not Path(s.db_path).exists() and s.db_path == "data/shop.db":
        build(s.db_path)  # first run: create the sample database
    agent = SQLAgent(Database(s.db_path, s.max_rows, s.query_timeout_s), get_model(s), s.max_steps)
    if args.question:
        show(agent, args.question, args.verbose)
        return
    print(f"Model: {agent.model.name}. Type 'exit' to quit.")
    while (q := input("> ").strip()).lower() not in {"exit", "quit"}:
        if q:
            show(agent, q, args.verbose)


if __name__ == "__main__":
    main()
