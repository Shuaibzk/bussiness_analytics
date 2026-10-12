"""Builds the knowledge base ("documents") that the RAG chat retrieves from.

Why not embed raw CSV rows?  Embeddings capture *meaning*, not arithmetic - "total profit in Asia in 2023"
cannot be answered by similarity search over 10,000 rows.  Instead we pre-compute readable, self-contained
fact sheets (aggregates, comparisons, definitions) at several granularities, and the chat uses exact
queries for hard numbers (see chat.py).

Security model: every document carries
  scope_region / scope_category : None = covers all rows, '*' = scope-neutral (definitions), else the slice it summarises
  needs                        : columns a role must be allowed to see for the document to be shown
Retrieval filters on these BEFORE ranking, so out-of-scope text can never reach the LLM.
"""
from __future__ import annotations

import pandas as pd

from .db import read_df
from .engine import detect_tail_off

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def usd(v) -> str:
    return f"${v:,.0f}"


def pct(v, d=1) -> str:
    return f"{v:.{d}f}%"


def _agg(g: pd.DataFrame) -> dict:
    net = g[g.net_flag == 1]
    n = len(g)
    rev = net.revenue.sum()
    return {
        "orders": n,
        "net_orders": len(net),
        "rev": rev,
        "profit": net.profit.sum(),
        "margin": (net.profit.sum() / rev * 100) if rev else 0,
        "aov": (rev / len(net)) if len(net) else 0,
        "ret": (g.order_status == "Returned").mean() * 100 if n else 0,
        "can": (g.order_status == "Cancelled").mean() * 100 if n else 0,
        "days": g.shipping_days.mean() if n else 0,
        "ship": g.shipping_cost.mean() if n else 0,
        "loss": g.loss_flag.mean() * 100 if n else 0,
        "gross": g.revenue.sum(),
    }


def _money_line(name, a, total_rev):
    share = f" ({a['rev'] / total_rev * 100:.1f}% of revenue)" if total_rev else ""
    return (f"{name}: net revenue {usd(a['rev'])}{share}, profit {usd(a['profit'])}, margin {pct(a['margin'])}, "
            f"{a['orders']:,} orders, return rate {pct(a['ret'])}.")


def _ops_line(name, a):
    return (f"{name}: {a['orders']:,} orders, return rate {pct(a['ret'])}, cancellation rate {pct(a['can'])}, "
            f"average delivery {a['days']:.1f} days, average shipping cost ${a['ship']:.2f}.")


BREAKDOWNS = [
    ("year", "year", "year"), ("region", "region", "region"), ("country", "country", "country"),
    ("category", "category", "product category"), ("sub_category", "sub_category", "sub-category"),
    ("customer_segment", "customer_segment", "customer segment"), ("customer_gender", "customer_gender", "customer gender"),
    ("shipping_method", "shipping_method", "shipping method"), ("payment_method", "payment_method", "payment method"),
    ("season", "season", "season"), ("order_status", "order_status", "order status"),
]


def build_docs(df: pd.DataFrame, scope_region: str | None, scope_category: str | None) -> list[dict]:
    label = (f"Region {scope_region}" if scope_region else f"Category {scope_category}" if scope_category else "All data")
    prefix = f"[{label}]"
    docs: list[dict] = []

    def add(topic, title, text, needs=()):
        docs.append({
            "id": f"{label.lower().replace(' ', '-')}::{topic}",
            "title": f"{prefix} {title}", "topic": topic, "text": f"{prefix} {title}\n{text}",
            "scope_region": scope_region, "scope_category": scope_category, "needs": list(needs),
        })

    a = _agg(df)
    lo, hi = df.order_date.min(), df.order_date.max()
    add("overview", "Overall performance summary",
        f"Period {lo} to {hi}. {a['orders']:,} orders. Gross revenue (all orders) {usd(a['gross'])}. "
        f"Net revenue (excluding returned and cancelled orders) {usd(a['rev'])}. Net profit {usd(a['profit'])}, "
        f"profit margin {pct(a['margin'])}. Average order value {usd(a['aov'])}. "
        f"Return rate {pct(a['ret'])}, cancellation rate {pct(a['can'])}. "
        f"{a['loss']:.1f}% of orders are loss-making.", needs=("revenue", "profit"))
    add("ops_overview", "Operations summary",
        f"Period {lo} to {hi}. {a['orders']:,} orders: " +
        ", ".join(f"{k} {v:,}" for k, v in df.order_status.value_counts().items()) +
        f". Return rate {pct(a['ret'])}, cancellation rate {pct(a['can'])}. "
        f"Average delivery time {a['days']:.1f} days, average shipping cost ${a['ship']:.2f} per order.")

    # ---- generic breakdowns (money variant + operations variant)
    for col, _key, human in BREAKDOWNS:
        if col == "region" and scope_region:
            continue
        if col == "category" and scope_category:
            continue
        groups = df.groupby(col)
        rows = sorted(((n, _agg(g)) for n, g in groups), key=lambda x: -x[1]["rev"])
        if col in ("year",):
            rows = sorted(rows, key=lambda x: x[0])
        tot = a["rev"]
        text = "\n".join(_money_line(n, r, tot) for n, r in rows)
        if col == "year":
            lines = []
            for i, (n, r) in enumerate(rows):
                if i:
                    pr = rows[i - 1][1]
                    lines.append(f"{n} versus {rows[i - 1][0]}: revenue {(r['rev'] - pr['rev']) / pr['rev'] * 100:+.1f}%, "
                                 f"orders {(r['orders'] - pr['orders']) / pr['orders'] * 100:+.1f}%.")
            text += "\nYear-over-year change:\n" + "\n".join(lines)
        add(f"by_{col}", f"Performance by {human}", text, needs=("revenue", "profit"))
        ops_rows = sorted(rows, key=lambda x: -x[1]["orders"]) if col != "year" else rows
        add(f"ops_by_{col}", f"Orders, returns and delivery by {human}",
            "\n".join(_ops_line(n, r) for n, r in ops_rows))

    # ---- seasonality
    mo = {m: _agg(g) for m, g in df.groupby("month")}
    best = sorted(mo, key=lambda m: -mo[m]["rev"])[:3]
    add("seasonality", "Monthly seasonality",
        "Net revenue by calendar month (all years combined): " +
        ", ".join(f"{MONTHS[m - 1]} {usd(mo[m]['rev'])}" for m in sorted(mo)) +
        f". Strongest months: {', '.join(MONTHS[m - 1] for m in best)}.", needs=("revenue",))
    for y, gy in df.groupby("year"):
        my = {m: _agg(g) for m, g in gy.groupby("month")}
        add(f"monthly_{y}", f"Month-by-month results for {y}",
            ", ".join(f"{MONTHS[m - 1]}: {usd(my[m]['rev'])} revenue / {my[m]['orders']:,} orders" for m in sorted(my)),
            needs=("revenue",))

    # ---- products
    prod = sorted(((n, _agg(g)) for n, g in df.groupby("product_name")), key=lambda x: -x[1]["rev"])
    add("top_products", "Top 10 products by net revenue",
        "\n".join(f"{i + 1}. {n} ({df[df.product_name == n].category.iloc[0]}): {usd(r['rev'])} revenue, profit {usd(r['profit'])}, "
                  f"margin {pct(r['margin'])}, {r['orders']:,} orders" for i, (n, r) in enumerate(prod[:10])),
        needs=("revenue", "profit"))
    add("bottom_products", "Lowest 10 products by net revenue",
        "\n".join(f"{n}: {usd(r['rev'])} revenue, profit {usd(r['profit'])}, {r['orders']:,} orders" for n, r in prod[-10:][::-1]),
        needs=("revenue", "profit"))
    by_profit = sorted(prod, key=lambda x: -x[1]["profit"])
    add("profit_products", "Most and least profitable products",
        "Most profitable: " + "; ".join(f"{n} {usd(r['profit'])}" for n, r in by_profit[:5]) +
        ". Least profitable: " + "; ".join(f"{n} {usd(r['profit'])}" for n, r in by_profit[-5:]) + ".",
        needs=("profit",))
    by_ret = sorted(((n, _agg(g)) for n, g in df.groupby("product_name")), key=lambda x: -x[1]["ret"])
    add("returned_products", "Products with the highest return rates",
        "\n".join(f"{n}: return rate {pct(r['ret'])} across {r['orders']:,} orders" for n, r in by_ret[:8]))
    add("best_selling_units", "Best-selling products by number of orders",
        "\n".join(f"{n}: {r['orders']:,} orders" for n, r in sorted(prod, key=lambda x: -x[1]["orders"])[:10]))

    # ---- discounts
    dg = sorted(((d, _agg(g)) for d, g in df.groupby("discount")), key=lambda x: x[0])
    deep = df[df.discount >= 0.3]
    add("discounts", "Discount impact on profitability",
        "Margin and loss-making share by discount level (net basis):\n" +
        "\n".join(f"{d * 100:.0f}% discount: {r['orders']:,} orders, average margin {pct(r['margin'])}, "
                  f"{pct(r['loss'], 0)} of orders lose money" for d, r in dg) +
        f"\nOrders with a discount of 30% or more: {len(deep):,} ({len(deep) / max(1, len(df)) * 100:.1f}% of orders), "
        f"of which {deep.loss_flag.mean() * 100 if len(deep) else 0:.0f}% are loss-making. "
        "Recommendation: cap discounts at 25%.", needs=("discount", "profit"))
    loss = df[df.loss_flag == 1]
    add("loss_orders", "Loss-making orders",
        f"{len(loss):,} orders ({len(loss) / max(1, len(df)) * 100:.1f}%) have negative profit, "
        f"total loss {usd(-loss.profit.sum())}. By category: " +
        ", ".join(f"{k} {v:,}" for k, v in loss.category.value_counts().items()) +
        ". By discount: " + ", ".join(f"{k * 100:.0f}% -> {v:,}" for k, v in loss.discount.value_counts().sort_index().items()) + ".",
        needs=("profit", "discount"))

    # ---- shipping & returns
    sm = {n: _agg(g) for n, g in df.groupby("shipping_method")}
    add("shipping_insight", "Shipping speed versus cost",
        "\n".join(f"{n}: {r['orders']:,} orders, average {r['days']:.1f} days, average shipping cost ${r['ship']:.2f}"
                  for n, r in sm.items()) +
        "\nObservation: delivery time is almost identical across shipping methods, although Overnight costs about "
        "12x more than Economy - premium shipping is not delivering faster." +
        (("\nWhat actually drives delivery time is geography: " +
          ", ".join(f"{n} {r['days']:.1f} days" for n, r in sorted(((n, _agg(g)) for n, g in df.groupby('region')), key=lambda x: x[1]['days'])) + ".")
         if df.region.nunique() > 1 else ""))
    # data completeness: does the monthly series taper off at the end?
    mcount = df.groupby("yr_month").size()
    tail = detect_tail_off([float(v) for v in mcount.values])
    add("data_completeness", "Data completeness and the latest months",
        "Orders per month, most recent 12 months: " + ", ".join(f"{k} {v:,}" for k, v in mcount.tail(12).items()) + ". " +
        (f"Volume tapers off steadily over the last {tail}+ months to {int(mcount.iloc[-1])} orders, which looks like an incomplete or "
         "late-loaded data extract rather than a real collapse in demand - confirm the data cut-off before drawing conclusions about the latest year."
         if tail else "There is no sign of an incomplete latest period."))
    ret = df[df.order_status == "Returned"]
    add("returns", "Returns analysis",
        f"{len(ret):,} orders were returned ({len(ret) / max(1, len(df)) * 100:.1f}%). Highest return rate by category: " +
        ", ".join(f"{n} {pct(r['ret'])}" for n, r in sorted(((n, _agg(g)) for n, g in df.groupby('category')), key=lambda x: -x[1]["ret"])[:3]) +
        ".")
    add("returns_money", "Revenue lost to returns and cancellations",
        f"Returned orders: {usd(ret.revenue.sum())} revenue. Cancelled orders: {usd(df[df.order_status == 'Cancelled'].revenue.sum())} revenue. "
        f"Together {(a['gross'] - a['rev']) / max(1, a['gross']) * 100:.1f}% of gross revenue is excluded from net revenue.",
        needs=("revenue",))

    # ---- customers
    cust = df.groupby("customer_id").size()
    add("customers", "Customer base and repeat purchasing",
        f"{df.customer_id.nunique():,} unique customers placed {len(df):,} orders. "
        f"{(cust > 1).sum():,} customers ordered more than once (repeat rate {(cust > 1).mean() * 100:.1f}%). "
        f"Customers by segment: " + ", ".join(f"{k} {v:,}" for k, v in df.groupby('customer_segment').customer_id.nunique().items()) + ".",
        needs=("customer_id",))
    return docs


DICTIONARY = [
    ("dictionary_orders", "Data dictionary - orders and time", (), "Each row is one order (Order_ID). Dates cover January 2021 to December 2024 and are broken out into Year, Quarter, Month and Season. Order_Status is Delivered, Processing, Returned or Cancelled."),
    ("dictionary_geo_product", "Data dictionary - geography and products", (), "Orders are placed in 4 regions (North America, Asia, Europe, Middle East) and 18 countries. Products belong to 5 categories (Electronics, Clothing, Home & Kitchen, Books & Media, Beauty & Health), 14 sub-categories and 70 products."),
    ("dictionary_money", "Data dictionary - financial metrics and definitions", ("revenue", "profit"), "Revenue = Unit_Price x Quantity x (1 - Discount). Profit = Revenue - Cost. Profit margin = Profit / Revenue. NET revenue and profit exclude orders with status Returned or Cancelled; GROSS includes all orders. Average order value = net revenue / net orders. Shipping cost is tracked separately and is not part of profit."),
    ("dictionary_shipping", "Data dictionary - shipping, payment and status", (), "Shipping methods: Economy, Standard, Express, Overnight with shipping cost and shipping days. Payment methods: Credit Card, Debit Card, PayPal, Apple Pay, Google Pay, Bank Transfer, Cash on Delivery. Return rate = returned orders / all orders. Cancellation rate = cancelled orders / all orders."),
    ("dictionary_customers", "Data dictionary - customers", ("customer_id",), "Customers have a Customer_ID, gender (Male/Female) and a segment: New, Regular, Premium or VIP. Data caveat: segment and gender are recorded per ORDER and are not stable per customer - about 41% of customers appear with more than one segment - so customer-segment analysis describes orders, not a fixed customer property."),
]


def build_all() -> list[dict]:
    df = read_df("SELECT * FROM orders")
    docs = build_docs(df, None, None)
    for r in sorted(df.region.unique()):
        docs += build_docs(df[df.region == r], r, None)
    for c in sorted(df.category.unique()):
        docs += build_docs(df[df.category == c], None, c)
    for topic, title, needs, text in DICTIONARY:
        docs.append({"id": f"dict::{topic}", "title": title, "topic": topic, "text": f"{title}\n{text}",
                     "scope_region": "*", "scope_category": "*", "needs": list(needs)})
    return docs
