from app.agent import SQLAgent
from app.llm import Reply

from .conftest import call

GOOD_SQL = ("SELECT p.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS revenue FROM order_items oi "
            "JOIN products p ON p.id = oi.product_id JOIN orders o ON o.id = oi.order_id "
            "WHERE o.status != 'cancelled' GROUP BY p.name ORDER BY revenue DESC LIMIT 3")


def test_agent_explores_recovers_from_error_and_answers(db, scripted):
    model = scripted([
        call("list_tables"),
        call("describe_table", table="order_items"),
        call("run_sql", sql="SELECT name, SUM(total) FROM products"),  # wrong column -> error
        call("run_sql", sql=GOOD_SQL),
        Reply(content="Standing Desk earned the most.\nSQL used: " + GOOD_SQL),
    ])
    r = SQLAgent(db, model).ask("Top 3 products by revenue?")

    assert [s.tool for s in r.steps] == ["list_tables", "describe_table", "run_sql", "run_sql"]
    assert not r.steps[2].ok and "no such column" in r.steps[2].output
    assert r.steps[3].ok and r.sql == GOOD_SQL
    assert r.answer.startswith("Standing Desk")

    # The error was fed back to the model, paired with the right tool_call_id
    last_msgs = model.calls[3]
    assert last_msgs[-1]["role"] == "tool" and "ERROR" in last_msgs[-1]["content"]
    assert last_msgs[-1]["tool_call_id"] == last_msgs[-2]["tool_calls"][0]["id"]
    assert last_msgs[0]["role"] == "system"


def test_blocked_write_is_reported_not_executed(db, scripted):
    model = scripted([call("run_sql", sql="DROP TABLE orders"), Reply(content="I can only read data.")])
    r = SQLAgent(db, model).ask("delete all orders")
    assert not r.steps[0].ok and r.sql is None
    assert "orders" in db.list_tables()


def test_agent_stops_after_max_steps(db, scripted):
    model = scripted([call("list_tables")] * 3)
    r = SQLAgent(db, model, max_steps=3).ask("loop forever")
    assert len(r.steps) == 3 and "Stopped after 3 steps" in r.answer


def test_unknown_tool_is_handled(db, scripted):
    model = scripted([call("rm_rf"), Reply(content="done")])
    r = SQLAgent(db, model).ask("x")
    assert not r.steps[0].ok and "Unknown tool" in r.steps[0].output
