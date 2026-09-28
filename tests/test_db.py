import sqlite3

import pytest

from app.db import Database, QueryError


def test_schema_tools(db):
    assert db.list_tables() == ["customers", "order_items", "orders", "products"]
    desc = db.describe_table("orders")
    assert "customer_id INTEGER" in desc and "customer_id -> customers.id" in desc
    with pytest.raises(QueryError, match="Unknown table"):
        db.describe_table("users")


def test_select_works_and_matches_raw_sqlite(db, db_path):
    sql = "SELECT category, ROUND(SUM(quantity * unit_price), 2) FROM order_items JOIN products p ON p.id = product_id GROUP BY category ORDER BY 2 DESC"
    sql = sql.replace("unit_price", "order_items.unit_price")
    res = db.run_sql(sql)
    with sqlite3.connect(db_path) as raw:
        assert res.rows == raw.execute(sql).fetchall()
    assert res.columns[0] == "category"


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "DROP TABLE customers",
    "UPDATE products SET unit_price = 0",
    "INSERT INTO products (name, category, unit_price) VALUES ('x', 'y', 1)",
    "SELECT 1; DROP TABLE orders",
    "ATTACH DATABASE 'x.db' AS x",
    "PRAGMA writable_schema = 1",
])
def test_writes_are_rejected_by_validator(db, sql):
    with pytest.raises(QueryError):
        db.run_sql(sql)


def test_write_hidden_in_cte_is_blocked_by_engine(db):
    # Starts with WITH so it passes the text check; the authorizer and read-only mode must stop it.
    with pytest.raises(QueryError):
        db.run_sql("WITH x AS (SELECT 1) DELETE FROM orders")
    assert db.run_sql("SELECT COUNT(*) FROM orders").rows[0][0] > 0


def test_comments_and_trailing_semicolon_are_ok(db):
    assert db.run_sql("-- count\nSELECT COUNT(*) FROM products;").rows == [(12,)]


def test_results_are_truncated(db):
    res = db.run_sql("SELECT id FROM customers")
    assert len(res.rows) == 50 and res.truncated and "truncated" in res.to_text()


def test_runaway_query_times_out(db_path):
    slow = Database(db_path, timeout_s=0.2)
    with pytest.raises(QueryError, match="timed out"):
        slow.run_sql("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT COUNT(*) FROM r")


def test_sql_errors_are_readable(db):
    with pytest.raises(QueryError, match="no such column"):
        db.run_sql("SELECT total FROM orders")


def test_missing_db_file():
    with pytest.raises(FileNotFoundError):
        Database("nope/missing.db")
