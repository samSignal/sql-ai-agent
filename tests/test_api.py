from fastapi.testclient import TestClient

from app import main
from app.agent import SQLAgent
from app.llm import Reply

from .conftest import call


def client_with(db, model, monkeypatch):
    monkeypatch.setattr(main, "get_agent", lambda: SQLAgent(db, model))
    return TestClient(main.app)


def test_ask_endpoint(db, scripted, monkeypatch):
    model = scripted([call("run_sql", sql="SELECT COUNT(*) AS n FROM products"), Reply(content="There are 12 products.")])
    c = client_with(db, model, monkeypatch)
    body = c.post("/ask", json={"question": "How many products?"}).json()
    assert body["answer"] == "There are 12 products."
    assert body["sql"] == "SELECT COUNT(*) AS n FROM products"
    assert body["steps"][0]["output"] == "n\n12"


def test_health_schema_ui_and_validation(db, scripted, monkeypatch):
    c = client_with(db, scripted([]), monkeypatch)
    assert c.get("/health").json()["tables"] == ["customers", "order_items", "orders", "products"]
    assert "customer_id" in c.get("/schema").json()["orders"]
    assert c.get("/").status_code == 200
    assert c.post("/ask", json={"question": ""}).status_code == 422


def test_backend_error_returns_502(db, monkeypatch):
    class Broken:
        name = "broken"

        def chat(self, *a):
            raise ConnectionError("model offline")

    c = client_with(db, Broken(), monkeypatch)
    r = c.post("/ask", json={"question": "hi"})
    assert r.status_code == 502 and "model offline" in r.json()["detail"]
