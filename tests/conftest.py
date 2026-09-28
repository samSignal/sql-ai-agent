import json

import pytest

from app.db import Database
from app.llm import Reply, ToolCall
from seed import build


@pytest.fixture(scope="session")
def db_path(tmp_path_factory):
    return build(str(tmp_path_factory.mktemp("db") / "shop.db"))


@pytest.fixture
def db(db_path):
    return Database(db_path, max_rows=50, timeout_s=2)


class ScriptedModel:
    """A stand-in for the LLM that replays a fixed plan, so the agent loop is tested deterministically.
    It also records every message list it receives, to check what the agent sends back."""

    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append(json.loads(json.dumps(messages)))
        return self.replies.pop(0)


def call(name, **args):
    return Reply(tool_calls=[ToolCall(id=f"id_{name}_{len(args)}", name=name, args=args)])


@pytest.fixture
def scripted():
    return ScriptedModel
