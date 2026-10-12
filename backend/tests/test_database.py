"""Database test-suite (MariaDB): schema, integrity rules, least privilege, reconciliation with the source CSV, migrations,
and concurrency of the hash-chained audit log.   Run:  python -m tests.test_database
"""
from __future__ import annotations

import sys
import threading

import pandas as pd
import pymysql

from app import audit, engine
from app.config import CSV_PATH, DB_USER
from app.db import connect, get_db, ping
from app.migrate import MigrationError, run_migrations
from app.security import ROLE_POLICY, User

results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, extra: str = ""):
    results.append((bool(ok), name))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -> ' + str(extra)) if (extra and not ok) else ''}")


def refused(sql: str, params=(), admin: bool = False) -> bool:
    """True when the database REFUSES the statement (privilege or integrity error); always rolls back."""
    c = connect(admin=admin)
    try:
        c.execute(sql, params)
        c.rollback()
        return False
    except pymysql.err.MySQLError:
        return True
    finally:
        c.close()


def U(role, scope=None):
    return User(1, role, role, role, scope, ROLE_POLICY[role])


# ---------------------------------------------------------------------------------------------------- schema
adm = connect(admin=True)
tables = {r[0] for r in adm.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'").fetchall()}
expected = {"dim_geography", "dim_product", "dim_customer", "dim_date", "dim_order_status", "dim_shipping_method", "dim_payment_method",
            "fact_orders", "users", "sessions", "login_attempts", "audit_log", "targets", "chat_messages", "docs", "schema_migrations"}
check("all expected tables exist (star schema + app tables)", expected <= tables, expected - tables)
cons = {}
for r in adm.execute("SELECT constraint_type, COUNT(*) n FROM information_schema.table_constraints WHERE table_schema = DATABASE() GROUP BY constraint_type").fetchall():
    cons[r[0]] = r[1]
check("foreign keys are declared (fact -> 7 dimensions; sessions, targets, chat -> users)", cons.get("FOREIGN KEY", 0) >= 10, cons)
check("CHECK constraints are declared", cons.get("CHECK", 0) >= 10, cons)
engines = {r[0] for r in adm.execute("SELECT DISTINCT engine FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'").fetchall()}
check("every table is InnoDB (transactions + foreign keys)", engines == {"InnoDB"}, engines)
check("database uses utf8mb4", adm.execute("SELECT @@character_set_database").fetchone()[0] == "utf8mb4")
check("session runs in strict SQL mode", "STRICT_TRANS_TABLES" in adm.execute("SELECT @@SESSION.sql_mode").fetchone()[0])

# ----------------------------------------------------------------------------------- reconciliation with the CSV
df = pd.read_csv(CSV_PATH)
net = df[~df.Order_Status.isin(["Returned", "Cancelled"])]
a = adm.execute("SELECT COUNT(*) n, SUM(revenue) rev, SUM(profit) prof, SUM(cost) cost, SUM(shipping_cost) ship FROM fact_orders").fetchone()
check("row count equals the CSV (10,000)", a["n"] == len(df) == 10000, a["n"])
check("total revenue / profit / cost / shipping equal the CSV to the cent",
      all(abs(float(a[k]) - float(df[c].sum())) < 0.01 for k, c in (("rev", "Revenue"), ("prof", "Profit"), ("cost", "Cost"), ("ship", "Shipping_Cost"))))
v = adm.execute("SELECT SUM(revenue) r FROM orders WHERE net_flag = 1").fetchone()["r"]
check("net revenue through the view equals pandas (excl. returned + cancelled)", abs(float(v) - float(net.Revenue.sum())) < 0.01)
by_region = {r[0]: r[1] for r in adm.execute("SELECT region, COUNT(*) FROM orders GROUP BY region").fetchall()}
check("orders per region equal the CSV", by_region == df.Region.value_counts().to_dict())
sample = {r[0]: float(r[1]) for r in adm.execute("SELECT order_id, profit_margin FROM fact_orders").fetchall()}
csv_pm = dict(zip(df.Order_ID, df["Profit_Margin_%"]))
check("generated profit_margin column matches the CSV's Profit_Margin_% on every row", max(abs(sample[k] - csv_pm[k]) for k in csv_pm) <= 0.011)
sample_loss = {r[0]: r[1] for r in adm.execute("SELECT order_id, loss_flag FROM fact_orders").fetchall()}
check("generated loss_flag equals (profit < 0)", all(sample_loss[o] == int(p < 0) for o, p in zip(df.Order_ID, df.Profit)))
st = {r[0]: r[1] for r in adm.execute("SELECT status, is_net FROM dim_order_status").fetchall()}
check("business rule lives in the database: only Returned/Cancelled are non-net", st == {"Delivered": 1, "Processing": 1, "Returned": 0, "Cancelled": 0})
check("view exposes the columns the engine expects", {"order_id", "order_date", "yr_month", "yr_quarter", "region", "category", "net_flag", "loss_flag"} <=
      {r[0] for r in adm.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'orders'").fetchall()})
a_ = U("admin")
q = engine.run_query(a_, ["revenue", "profit"], ["year", "category"])
gold = net.groupby(["Year", "Category"])[["Revenue", "Profit"]].sum().round(2)
check("governed engine on MariaDB equals pandas for revenue/profit by year x category",
      all(abs(r[2] - gold.loc[(r[0], r[1]), "Revenue"]) < 0.01 and abs(r[3] - gold.loc[(r[0], r[1]), "Profit"]) < 0.01 for r in q["rows"]) and len(q["rows"]) == len(gold))

# ----------------------------------------------------------- reporting table mirrors the star schema
check("reporting table `orders` is a BASE TABLE (denormalised copy), the star join is the view v_orders_flat",
      adm.execute("SELECT table_type FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'orders'").fetchone()[0] == "BASE TABLE"
      and adm.execute("SELECT table_type FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'v_orders_flat'").fetchone()[0] == "VIEW")
check("reporting table is identical to the star-schema join (no row differs in either direction)",
      adm.execute("SELECT COUNT(*) FROM (SELECT * FROM v_orders_flat EXCEPT SELECT * FROM orders) x").fetchone()[0] == 0
      and adm.execute("SELECT COUNT(*) FROM (SELECT * FROM orders EXCEPT SELECT * FROM v_orders_flat) x").fetchone()[0] == 0)
check("reporting table has indexes on the filter columns",
      {"ix_orders_region", "ix_orders_category", "ix_orders_year_month", "ix_orders_status"} <=
      {r[0] for r in adm.execute("SELECT DISTINCT index_name FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = 'orders'").fetchall()})
adm.execute("DELETE FROM orders WHERE region = 'Asia'")
adm.commit()
from app.migrate import ensure_database  # noqa: E402
ensure_database()
check("self-healing: a damaged reporting table is rebuilt from the fact table on start-up",
      adm.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 10000)
adm.commit()

# ---------------------------------------------------------------------------- integrity rules refuse bad data
row = adm.execute("SELECT * FROM fact_orders LIMIT 1").fetchone()
cols = [c for c in row.keys() if c not in ("profit_margin", "loss_flag")]


def new_fact(**over):
    """A fact row that satisfies every rule except the one(s) overridden, so each test isolates ONE constraint."""
    d = {c: row[c] for c in cols}
    d["order_id"] = "ORD-TEST-X"
    d.update(over)
    if "revenue" not in over:
        d["revenue"] = round(float(d["unit_price"]) * d["quantity"] * (1 - float(d["discount"])), 2)
    if "profit" not in over:
        d["profit"] = round(float(d["revenue"]) - float(d["cost"]), 2)
    return "INSERT INTO fact_orders (" + ", ".join(d) + ") VALUES (" + ", ".join("?" for _ in d) + ")", tuple(d.values())


check("baseline: a consistent fact row would be accepted", not refused(*new_fact(), admin=True))
check("quantity must be positive", refused(*new_fact(quantity=0), admin=True))
check("discount must be between 0 and 1", refused(*new_fact(discount=1.5), admin=True))
check("revenue must equal price x qty x (1 - discount)", refused(*new_fact(revenue=1), admin=True))
check("profit must equal revenue - cost", refused(*new_fact(profit=-1), admin=True))
check("shipping days are bounded", refused(*new_fact(shipping_days=200), admin=True))
check("foreign key: unknown geography is rejected", refused(*new_fact(geo_id=9999), admin=True))
check("foreign key: unknown product is rejected", refused(*new_fact(product_id=9999), admin=True))
check("foreign key: unknown customer is rejected", refused(*new_fact(customer_id="CUST-NOPE"), admin=True))
check("primary key: duplicate order id is rejected", refused(*new_fact(order_id=row["order_id"]), admin=True))
check("segment must be one of New/Regular/Premium/VIP", refused(*new_fact(customer_segment="Gold"), admin=True))
check("a regional manager without a region is rejected by the database",
      refused("INSERT INTO users (username, name, password_hash, role, scope_value) VALUES ('t_x1','x','h','regional_manager',NULL)", admin=True))
check("an executive WITH a region is rejected by the database",
      refused("INSERT INTO users (username, name, password_hash, role, scope_value) VALUES ('t_x2','x','h','executive','Asia')", admin=True))
check("unknown role is rejected (ENUM)", refused("INSERT INTO users (username, name, password_hash, role, scope_value) VALUES ('t_x3','x','h','root',NULL)", admin=True))
check("usernames are unique", refused("INSERT INTO users (username, name, password_hash, role) SELECT username, name, password_hash, role FROM users LIMIT 1", admin=True))
check("targets must be positive", refused("INSERT INTO targets (user_id, metric, year, value) VALUES (1, 'revenue', 2024, 0)", admin=True))
check("chat rating must be -1 or 1", refused("INSERT INTO chat_messages (user_id, role, content, ts, rating) VALUES (1, 'assistant', 'x', 1, 5)", admin=True))
check("deleting a user cascades to their sessions (FK ON DELETE CASCADE)",
      adm.execute("SELECT delete_rule FROM information_schema.referential_constraints WHERE constraint_name = 'fk_sessions_user'").fetchone()[0] == "CASCADE")
adm.rollback()
adm.close()

# ------------------------------------------------------------------------------------------ least privilege
app = connect()
check("app account: can read the flat orders view", app.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 10000)
app.close()
check("app account: cannot read the fact table directly", refused("SELECT * FROM fact_orders LIMIT 1"))
check("app account: cannot read dimension tables directly", refused("SELECT * FROM dim_customer LIMIT 1"))
check("app account: cannot read the un-flattened star view either", refused("SELECT * FROM v_orders_flat LIMIT 1"))
check("app account: cannot DROP tables", refused("DROP TABLE users"))
check("app account: cannot CREATE tables", refused("CREATE TABLE hacked (x INT)"))
check("app account: cannot ALTER tables", refused("ALTER TABLE users ADD COLUMN x INT"))
check("app account: cannot DELETE users", refused("DELETE FROM users WHERE id = -1"))
check("app account: cannot UPDATE audit entries", refused("UPDATE audit_log SET detail = 'x' WHERE id = -1"))
check("app account: cannot DELETE audit entries", refused("DELETE FROM audit_log WHERE id = -1"))
check("app account: cannot TRUNCATE audit_log", refused("TRUNCATE TABLE audit_log"))
check("app account: cannot write to the data views", refused("UPDATE orders SET revenue = 0 WHERE order_id = 'x'"))
check("app account: cannot grant itself privileges", refused(f"GRANT ALL ON panorama.* TO '{DB_USER}'@'localhost'"))
check("app account: cannot read other databases", refused("SELECT * FROM mysql.user LIMIT 1"))
with get_db() as db:
    grants = " ".join(r[0] for r in db.execute("SHOW GRANTS FOR CURRENT_USER()").fetchall())
check("app account holds no ALL / DROP / ALTER / CREATE privileges", not any(w in grants.upper() for w in ("ALL PRIVILEGES", " DROP", " ALTER", " CREATE")), grants[:200])

# -------------------------------------------------------------------------------------------------- migrations
adm = connect(admin=True)
check("migrations are idempotent: re-running applies nothing", run_migrations(adm) == [])
orig = adm.execute("SELECT checksum FROM schema_migrations WHERE version = '001'").fetchone()[0]
adm.execute("UPDATE schema_migrations SET checksum = 'tampered' WHERE version = '001'")
adm.commit()
try:
    run_migrations(adm)
    detected = False
except MigrationError:
    detected = True
adm.execute("UPDATE schema_migrations SET checksum = ? WHERE version = '001'", (orig,))
adm.commit()
adm.close()
check("an applied migration that is edited later is detected (checksum)", detected)

# ------------------------------------------------------------------------------- concurrency + pool behaviour
before = audit.verify()["entries"]
errors: list[Exception] = []


def worker(i):
    try:
        for j in range(5):
            audit.write(None, "db_test", {"worker": i, "n": j}, username=f"w{i}")
    except Exception as e:  # pragma: no cover
        errors.append(e)


threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
[t.start() for t in threads]
[t.join() for t in threads]
v = audit.verify()
check("60 concurrent audit writes from 12 threads: no errors", not errors, errors[:1])
check("hash chain stays intact under concurrency (no forks, none lost)", v["ok"] and v["entries"] == before + 60, v)
info = ping()
check("health probe reports the engine and size", info["engine"].startswith("MariaDB") and info["size_mb"] > 0, info)
adm = connect(admin=True)
adm.execute("DELETE FROM audit_log WHERE action = 'db_test'")  # remove test traffic (these are the newest rows, so the chain stays valid)
adm.commit()
adm.close()

failed = [n for ok, n in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} database checks passed")
sys.exit(1 if failed else 0)
