"""Load the CSV into the MariaDB star schema, validate it, and seed the demo users.

  python -m app.ingest              reload the dataset (dimensions + facts); seeds demo users only if there are none
  python -m app.ingest --users      ALSO reset the users table to the demo accounts (ends all sessions)

Runs as the schema owner.  Constraints in migration 001 (foreign keys, CHECKs) re-verify the data as it is inserted.
"""
from __future__ import annotations

import datetime as dt
import sys

import pandas as pd

from .config import CSV_PATH
from .db import connect
from .security import hash_password

RENAME = {
    "Order_ID": "order_id", "Order_Date": "order_date", "Year": "year", "Month": "month",
    "Quarter": "quarter", "Season": "season", "Customer_ID": "customer_id",
    "Customer_Gender": "customer_gender", "Customer_Segment": "customer_segment",
    "Region": "region", "Country": "country", "Category": "category", "Sub_Category": "sub_category",
    "Product_Name": "product_name", "Unit_Price": "unit_price", "Quantity": "quantity",
    "Discount": "discount", "Revenue": "revenue", "Cost": "cost", "Profit": "profit",
    "Profit_Margin_%": "profit_margin", "Shipping_Cost": "shipping_cost",
    "Shipping_Method": "shipping_method", "Shipping_Days": "shipping_days",
    "Payment_Method": "payment_method", "Order_Status": "order_status",
}

# username, display name, password, role, scope value
DEMO_USERS = [
    ("admin", "Amina Admin", "admin123", "admin", None),
    ("executive", "Elias Executive", "exec123", "executive", None),
    ("asia.manager", "Aiko Tanaka", "manager123", "regional_manager", "Asia"),
    ("europe.manager", "Elena Rossi", "manager123", "regional_manager", "Europe"),
    ("me.manager", "Omar Haddad", "manager123", "regional_manager", "Middle East"),
    ("na.manager", "Noah Carter", "manager123", "regional_manager", "North America"),
    ("electronics.manager", "Ethan Cole", "category123", "category_manager", "Electronics"),
    ("clothing.manager", "Chloe Wright", "category123", "category_manager", "Clothing"),
    ("home.manager", "Hana Berg", "category123", "category_manager", "Home & Kitchen"),
    ("ops", "Olivia Ops", "ops123", "operations", None),
]

NET_STATUSES = {"Delivered": 1, "Processing": 1, "Returned": 0, "Cancelled": 0}   # the business rule, stored in dim_order_status
SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall", 10: "Fall", 11: "Fall"}


def load_frame() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH).rename(columns=RENAME)
    df["order_date"] = pd.to_datetime(df["order_date"], format="%m/%d/%Y")
    return df


def sanity_checks(df: pd.DataFrame) -> list[str]:
    report = []

    def check(name, bad):
        report.append(f"{'OK  ' if bad == 0 else 'WARN'} {name}: {bad} violations")

    check("duplicate order ids", int(df["order_id"].duplicated().sum()))
    check("null cells", int(df.isna().sum().sum()))
    check("revenue = price*qty*(1-discount)", int(((df.unit_price * df.quantity * (1 - df.discount) - df.revenue).abs() > 0.05).sum()))
    check("profit = revenue - cost", int(((df.revenue - df.cost - df.profit).abs() > 0.05).sum()))
    check("margin = profit/revenue", int(((df.profit / df.revenue * 100 - df.profit_margin).abs() > 0.05).sum()))
    d = df.order_date
    check("year/month columns match order_date", int(((d.dt.year != df.year) | (d.dt.month != df.month)).sum()))
    check("season matches the calendar month", int((d.dt.month.map(SEASONS) != df.season).sum()))
    check("quarter matches the calendar month", int((("Q" + ((d.dt.month - 1) // 3 + 1).astype(str)) != df.quarter).sum()))
    check("one category per product", int((df.groupby("product_name").category.nunique() > 1).sum()))
    check("one region per country", int((df.groupby("country").region.nunique() > 1).sum()))
    seg = df.groupby("customer_id").customer_segment.nunique()
    report.append(f"NOTE customers whose segment changes between orders: {int((seg > 1).sum()):,} of {len(seg):,} "
                  "(segment/gender are therefore modelled as order-level attributes)")
    return report


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def refresh_reporting(conn) -> int:
    """Rebuild the denormalised reporting table `orders` from the star schema (the source of truth). Returns the row count."""
    conn.execute("TRUNCATE TABLE orders")
    conn.execute("INSERT INTO orders SELECT * FROM v_orders_flat")
    conn.commit()
    conn.execute("ANALYZE TABLE orders").fetchall()
    return conn.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]


def load_all(verbose: bool = True) -> dict:
    df = load_frame()
    if verbose:
        print(f"Loaded {len(df):,} rows from {CSV_PATH}")
        for line in sanity_checks(df):
            print("  ", line)

    conn = connect(admin=True)
    try:
        conn.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in ("fact_orders", "dim_customer", "dim_product", "dim_geography", "dim_order_status",
                  "dim_shipping_method", "dim_payment_method", "dim_date"):
            conn.execute(f"TRUNCATE TABLE {t}")
        conn.execute("SET FOREIGN_KEY_CHECKS = 1")

        # ---- dimensions
        geo = df[["region", "country"]].drop_duplicates().sort_values(["region", "country"])
        conn.executemany("INSERT INTO dim_geography (region, country) VALUES (?,?)", [tuple(r) for r in geo.itertuples(index=False)])
        prod = df[["product_name", "sub_category", "category"]].drop_duplicates().sort_values("product_name")
        conn.executemany("INSERT INTO dim_product (product_name, sub_category, category) VALUES (?,?,?)", [tuple(r) for r in prod.itertuples(index=False)])
        first = df.groupby("customer_id").order_date.min()
        conn.executemany("INSERT INTO dim_customer (customer_id, first_order_date) VALUES (?,?)",
                         [(c, d.date()) for c, d in first.sort_index().items()])
        conn.executemany("INSERT INTO dim_order_status (status, is_net) VALUES (?,?)", list(NET_STATUSES.items()))
        conn.executemany("INSERT INTO dim_shipping_method (shipping_method) VALUES (?)", [(v,) for v in sorted(df.shipping_method.unique())])
        conn.executemany("INSERT INTO dim_payment_method (payment_method) VALUES (?)", [(v,) for v in sorted(df.payment_method.unique())])
        d0, d1 = dt.date(int(df.year.min()), 1, 1), dt.date(int(df.year.max()), 12, 31)
        days = [d0 + dt.timedelta(days=i) for i in range((d1 - d0).days + 1)]
        conn.executemany(
            "INSERT INTO dim_date (date_key, full_date, `year`, `quarter`, `month`, month_name, season, yr_month, yr_quarter) VALUES (?,?,?,?,?,?,?,?,?)",
            [(int(d.strftime("%Y%m%d")), d, d.year, f"Q{(d.month - 1) // 3 + 1}", d.month, d.strftime("%b"), SEASONS[d.month],
              d.strftime("%Y-%m"), f"{d.year}-Q{(d.month - 1) // 3 + 1}") for d in days])

        # ---- fact table (surrogate keys looked up from the dimensions we just loaded)
        def lookup(sql):
            return {r[0]: r[1] for r in conn.execute(sql).fetchall()}

        geo_id = lookup("SELECT country, geo_id FROM dim_geography")
        prod_id = lookup("SELECT product_name, product_id FROM dim_product")
        status_id = lookup("SELECT status, status_id FROM dim_order_status")
        ship_id = lookup("SELECT shipping_method, shipping_method_id FROM dim_shipping_method")
        pay_id = lookup("SELECT payment_method, payment_method_id FROM dim_payment_method")
        rows = [
            (r.order_id, int(r.order_date.strftime("%Y%m%d")), geo_id[r.country], prod_id[r.product_name], r.customer_id,
             status_id[r.order_status], ship_id[r.shipping_method], pay_id[r.payment_method], r.customer_segment, r.customer_gender,
             int(r.quantity), round(float(r.unit_price), 2), round(float(r.discount), 2), round(float(r.revenue), 2),
             round(float(r.cost), 2), round(float(r.profit), 2), round(float(r.shipping_cost), 2), int(r.shipping_days))
            for r in df.itertuples(index=False)
        ]
        for chunk in _chunks(rows, 1000):
            conn.executemany(
                "INSERT INTO fact_orders (order_id, date_key, geo_id, product_id, customer_id, status_id, shipping_method_id, payment_method_id, "
                "customer_segment, customer_gender, quantity, unit_price, discount, revenue, cost, profit, shipping_cost, shipping_days) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", chunk)
        conn.commit()
        for t in ("fact_orders", "dim_customer", "dim_product", "dim_geography", "dim_date"):
            conn.execute(f"ANALYZE TABLE {t}").fetchall()
        n = refresh_reporting(conn)
    finally:
        conn.close()
    if n != len(df):
        raise RuntimeError(f"row count mismatch after load: file {len(df)} vs database {n}")
    if verbose:
        print(f"Star schema loaded: {n:,} orders, {len(geo)} geographies, {len(prod)} products, {len(first):,} customers, {len(days):,} dates")
    return {"orders": n}


def seed_users(reset: bool = False, verbose: bool = True) -> int:
    conn = connect(admin=True)
    try:
        if reset:
            conn.execute("DELETE FROM users")  # sessions, targets and chat history cascade
        elif conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]:
            return 0
        for username, name, pw, role, scope in DEMO_USERS:
            conn.execute("INSERT INTO users (username, name, password_hash, role, scope_value) VALUES (?,?,?,?,?)",
                         (username, name, hash_password(pw), role, scope))
        conn.commit()
    finally:
        conn.close()
    if verbose:
        print(f"{len(DEMO_USERS)} demo users seeded")
    return len(DEMO_USERS)


def main() -> int:
    from .migrate import ensure_database

    ensure_database(load_if_empty=False)
    load_all()
    seed_users(reset="--users" in sys.argv)
    print("Database ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
