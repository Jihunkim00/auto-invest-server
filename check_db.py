from pathlib import Path
print("CHECK_DB_PATH =", Path("auto_invest.db").resolve())
import sqlite3

conn = sqlite3.connect("auto_invest.db")
conn.row_factory = sqlite3.Row

print("\n[Tables]")
tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()
for t in tables:
    print("-", t[0])

print("\n[Orders schema]")
schema = conn.execute("PRAGMA table_info(orders)").fetchall()
for col in schema:
    print(tuple(col))

print("\n[Orders count]")
count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
print(count)

print("\n[Recent orders]")
rows = conn.execute("""
    SELECT
        id,
        symbol,
        side,
        qty,
        notional,
        broker_order_id,
        internal_status,
        broker_status,
        filled_qty,
        filled_avg_price,
        submitted_at,
        filled_at,
        LENGTH(last_sync_payload) as last_sync_len,
        error_message
    FROM orders
    ORDER BY id DESC
    LIMIT 5
""").fetchall()

for row in rows:
    print(dict(row))

conn.close()