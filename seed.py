"""Create the sample database: a small fictional online shop (deterministic, so results are reproducible).

    python seed.py            # writes data/shop.db
"""
from __future__ import annotations

import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    country TEXT NOT NULL,
    signup_date TEXT NOT NULL
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('paid', 'shipped', 'delivered', 'cancelled'))
);
CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL
);
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_order ON order_items(order_id);
"""

PRODUCTS = [
    ("Wireless Mouse", "Accessories", 18.50), ("Mechanical Keyboard", "Accessories", 64.00),
    ("USB-C Hub", "Accessories", 29.90), ("27-inch Monitor", "Displays", 219.00),
    ("Portable SSD 1TB", "Storage", 89.00), ("Laptop Stand", "Accessories", 34.00),
    ("Noise-Cancelling Headphones", "Audio", 149.00), ("Webcam 1080p", "Video", 49.00),
    ("Bluetooth Speaker", "Audio", 59.00), ("External HDD 2TB", "Storage", 74.00),
    ("Office Chair", "Furniture", 189.00), ("Standing Desk", "Furniture", 349.00),
]
COUNTRIES = ["Zimbabwe", "South Africa", "Kenya", "Nigeria", "United Kingdom", "Lithuania", "Germany", "Botswana"]
FIRST = ["Tendai", "Amara", "John", "Lina", "Tariro", "Kwame", "Sarah", "Jonas", "Rudo", "Ada", "Peter", "Nia"]
LAST = ["Moyo", "Okafor", "Smith", "Petrauskas", "Dube", "Mensah", "Brown", "Schmidt", "Ncube", "Banda"]


def build(path: str = "data/shop.db", seed: int = 42) -> str:
    rng = random.Random(seed)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.unlink(missing_ok=True)
    conn = sqlite3.connect(p)
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO products (name, category, unit_price) VALUES (?, ?, ?)", PRODUCTS)

    start = date(2025, 1, 1)
    for cid in range(1, 121):
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        email = f"{name.lower().replace(' ', '.')}{cid}@example.com"
        signup = start + timedelta(days=rng.randint(0, 540))
        conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?, ?)",
                     (cid, name, email, rng.choice(COUNTRIES), signup.isoformat()))
        for _ in range(rng.randint(0, 6)):
            od = signup + timedelta(days=rng.randint(0, 200))
            status = rng.choices(["paid", "shipped", "delivered", "cancelled"], [2, 2, 7, 1])[0]
            oid = conn.execute("INSERT INTO orders (customer_id, order_date, status) VALUES (?, ?, ?)",
                               (cid, od.isoformat(), status)).lastrowid
            for pid in rng.sample(range(1, len(PRODUCTS) + 1), rng.randint(1, 3)):
                conn.execute("INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                             (oid, pid, rng.randint(1, 3), PRODUCTS[pid - 1][2]))
    conn.commit()
    conn.close()
    return str(p)


if __name__ == "__main__":
    print("created", build(sys.argv[1] if len(sys.argv) > 1 else "data/shop.db"))
