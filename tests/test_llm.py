"""Backend adapters tested against local fake HTTP servers (no API key or network needed).
The OpenAI test uses the real `openai` SDK, so request/response shapes are checked end to end."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.config import Settings
from app.llm import OllamaChat, OpenAIChat
from app.tools import TOOL_SPECS

HISTORY = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "How many products?"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "list_tables", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_1", "content": "products"},
]


@pytest.fixture
def fake_server():
    received = {}

    def start(response: dict):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received["path"], received["body"] = self.path, json.loads(body)
                out = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_port}", received

    servers = []
    yield start
    for s in servers:
        s.shutdown()


def test_openai_adapter(fake_server):
    url, received = fake_server({
        "id": "x", "object": "chat.completion", "created": 0, "model": "gpt-test",
        "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "call_2", "type": "function",
                            "function": {"name": "run_sql", "arguments": "{\"sql\": \"SELECT COUNT(*) FROM products\"}"}}]}}],
    })
    model = OpenAIChat(Settings(openai_api_key="test", openai_base_url=url + "/v1", openai_model="gpt-test"))
    reply = model.chat(HISTORY, TOOL_SPECS)

    assert received["path"] == "/v1/chat/completions"
    assert received["body"]["tools"] == TOOL_SPECS
    assert received["body"]["messages"][3] == {"role": "tool", "tool_call_id": "call_1", "content": "products"}
    assert reply.tool_calls[0].name == "run_sql"
    assert reply.tool_calls[0].args == {"sql": "SELECT COUNT(*) FROM products"}


def test_openai_requires_key():
    with pytest.raises(RuntimeError):
        OpenAIChat(Settings(openai_api_key=""))


def test_ollama_adapter(fake_server):
    url, received = fake_server({"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "describe_table", "arguments": {"table": "products"}}}]}})
    reply = OllamaChat(Settings(ollama_url=url, ollama_model="qwen2.5:7b")).chat(HISTORY, TOOL_SPECS)

    msgs = received["body"]["messages"]
    assert received["path"] == "/api/chat" and received["body"]["stream"] is False
    assert msgs[2]["tool_calls"][0]["function"] == {"name": "list_tables", "arguments": {}}
    assert msgs[3] == {"role": "tool", "content": "products", "tool_name": "list_tables"}
    assert reply.tool_calls[0].name == "describe_table" and reply.tool_calls[0].args == {"table": "products"}


def test_ollama_final_answer(fake_server):
    url, _ = fake_server({"message": {"role": "assistant", "content": "There are 12 products."}})
    reply = OllamaChat(Settings(ollama_url=url)).chat(HISTORY, TOOL_SPECS)
    assert reply.content == "There are 12 products." and reply.tool_calls == []
