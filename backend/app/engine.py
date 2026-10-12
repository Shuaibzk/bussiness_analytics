"""Governed analytics engine.

All numbers shown anywhere in the product (dashboard, tables, exports, AI chat) are produced here.
The caller never writes SQL: it names whitelisted metrics / dimensions / filters, and this module
  1. rejects anything the user's role may not see (hidden columns),
  2. ALWAYS injects the user's row scope (e.g. region = 'Asia') into the WHERE clause,
  3. binds every value as a SQL parameter (no string interpolation of user input),
  4. caches identical queries (keyed by scope, so one user's cache can never serve another).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable

from .config import CACHE_TTL_SECONDS
from .db import get_db
from .security import User


class QueryError(ValueError):
    """Malformed request."""


class AccessError(PermissionError):
    """Request touches data the role may not access."""


# ----------------------------------------------------------------- catalogue
@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    fmt: str  # currency | number | percent | days
    needs: frozenset
    sql: Callable[[str], str]  # receives the "is counted" condition
    desc: str


def _m(key, label, fmt, needs, sql, desc):
    return Metric(key, label, fmt, frozenset(needs), sql, desc)


METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        _m("revenue", "Net revenue", "currency", {"revenue"},
           lambda c: f"SUM(CASE WHEN {c} THEN revenue ELSE 0 END)",
           "Revenue from orders that were not returned or cancelled (or all orders on gross basis)"),
        _m("profit", "Profit", "currency", {"profit"},
           lambda c: f"SUM(CASE WHEN {c} THEN profit ELSE 0 END)", "Revenue minus product cost"),
        _m("cost", "Cost", "currency", {"cost"},
           lambda c: f"SUM(CASE WHEN {c} THEN cost ELSE 0 END)", "Product cost of goods"),
        _m("margin", "Profit margin", "percent", {"profit", "revenue"},
           lambda c: f"100.0 * SUM(CASE WHEN {c} THEN profit ELSE 0 END) / NULLIF(SUM(CASE WHEN {c} THEN revenue ELSE 0 END), 0)",
           "Profit divided by revenue"),
        _m("orders", "Orders", "number", set(),
           lambda c: f"SUM(CASE WHEN {c} THEN 1 ELSE 0 END)", "Number of orders"),
        _m("units", "Units sold", "number", {"quantity"},
           lambda c: f"SUM(CASE WHEN {c} THEN quantity ELSE 0 END)", "Total quantity sold"),
        _m("aov", "Avg order value", "currency", {"revenue"},
           lambda c: f"1.0 * SUM(CASE WHEN {c} THEN revenue ELSE 0 END) / NULLIF(SUM(CASE WHEN {c} THEN 1 ELSE 0 END), 0)",
           "Revenue per order"),
        _m("avg_discount", "Avg discount", "percent", {"discount"},
           lambda c: f"100.0 * AVG(CASE WHEN {c} THEN discount END)", "Average discount given"),
        _m("loss_rate", "Loss-making orders", "percent", {"profit"},
           lambda c: f"100.0 * AVG(CASE WHEN {c} THEN loss_flag END)", "Share of orders with negative profit"),
        _m("gross_revenue", "Gross revenue", "currency", {"revenue"},
           lambda c: "SUM(revenue)", "Revenue of ALL orders including returned and cancelled"),
        _m("returned_revenue", "Revenue lost to returns", "currency", {"revenue"},
           lambda c: "SUM(CASE WHEN order_status = 'Returned' THEN revenue ELSE 0 END)", "Revenue of returned orders"),
        _m("cancelled_revenue", "Revenue lost to cancellations", "currency", {"revenue"},
           lambda c: "SUM(CASE WHEN order_status = 'Cancelled' THEN revenue ELSE 0 END)", "Revenue of cancelled orders"),
        _m("return_rate", "Return rate", "percent", set(),
           lambda c: "100.0 * AVG(order_status = 'Returned')", "Share of all orders that were returned"),
        _m("cancel_rate", "Cancellation rate", "percent", set(),
           lambda c: "100.0 * AVG(order_status = 'Cancelled')", "Share of all orders that were cancelled"),
        _m("shipping_cost", "Shipping cost", "currency", set(),
           lambda c: f"SUM(CASE WHEN {c} THEN shipping_cost ELSE 0 END)", "Total shipping cost"),
        _m("avg_shipping_cost", "Avg shipping cost", "currency", set(),
           lambda c: f"AVG(CASE WHEN {c} THEN shipping_cost END)", "Average shipping cost per order"),
        _m("avg_shipping_days", "Avg delivery days", "days", set(),
           lambda c: f"AVG(CASE WHEN {c} THEN shipping_days END)", "Average days to deliver"),
        _m("slow_rate", "Slow deliveries (over 15 days)", "percent", set(),
           lambda c: f"100.0 * AVG(CASE WHEN {c} THEN (shipping_days > 15) END)", "Share of orders that took more than 15 days to deliver"),
        _m("fast_rate", "Fast deliveries (7 days or less)", "percent", set(),
           lambda c: f"100.0 * AVG(CASE WHEN {c} THEN (shipping_days <= 7) END)", "Share of orders delivered within 7 days"),
        _m("customers", "Unique customers", "number", {"customer_id"},
           lambda c: f"COUNT(DISTINCT CASE WHEN {c} THEN customer_id END)", "Distinct customer ids"),
    ]
}


@dataclass(frozen=True)
class Dim:
    key: str
    label: str
    col: str
    kind: str  # category | time | number


DIMS: dict[str, Dim] = {
    d.key: d
    for d in [
        Dim("year", "Year", "year", "time"),
        Dim("quarter", "Quarter", "yr_quarter", "time"),
        Dim("month", "Month", "yr_month", "time"),
        Dim("quarter_of_year", "Quarter", "quarter", "time"),
        Dim("month_of_year", "Month of year", "month", "time"),
        Dim("season", "Season", "season", "category"),
        Dim("region", "Region", "region", "category"),
        Dim("country", "Country", "country", "category"),
        Dim("category", "Category", "category", "category"),
        Dim("sub_category", "Sub-category", "sub_category", "category"),
        Dim("product", "Product", "product_name", "category"),
        Dim("segment", "Customer segment", "customer_segment", "category"),
        Dim("gender", "Customer gender", "customer_gender", "category"),
        Dim("shipping_method", "Shipping method", "shipping_method", "category"),
        Dim("payment_method", "Payment method", "payment_method", "category"),
        Dim("status", "Order status", "order_status", "category"),
        Dim("discount", "Discount level", "discount", "number"),
        Dim("delivery_band", "Delivery time", "CASE WHEN shipping_days <= 5 THEN '01-05 days' WHEN shipping_days <= 10 THEN '06-10 days' WHEN shipping_days <= 15 THEN '11-15 days' WHEN shipping_days <= 20 THEN '16-20 days' ELSE '21-25 days' END", "time"),        Dim("customer_id", "Customer", "customer_id", "category"),
    ]
}

# filters that are not group-by dimensions
DATE_FILTERS = {"date_from", "date_to"}

ORDER_COLUMNS = [
    ("order_id", "Order", "text"), ("order_date", "Date", "text"), ("region", "Region", "text"),
    ("country", "Country", "text"), ("category", "Category", "text"), ("sub_category", "Sub-category", "text"),
    ("product_name", "Product", "text"), ("customer_id", "Customer", "text"),
    ("customer_segment", "Segment", "text"), ("quantity", "Qty", "number"), ("unit_price", "Unit price", "currency"),
    ("discount", "Discount", "percent_frac"), ("revenue", "Revenue", "currency"), ("cost", "Cost", "currency"),
    ("profit", "Profit", "currency"), ("shipping_method", "Shipping", "text"), ("shipping_days", "Days", "number"),
    ("shipping_cost", "Ship cost", "currency"), ("payment_method", "Payment", "text"), ("order_status", "Status", "text"),
]

_METRIC_CATALOGUE_ORDER = list(METRICS)


# --------------------------------------------------------------- permissions
def metric_allowed(user: User, m: Metric) -> bool:
    return not (m.needs & user.hidden)


def dim_allowed(user: User, d: Dim) -> bool:
    return d.col not in user.hidden and d.key not in user.hidden


def visible_metrics(user: User) -> list[Metric]:
    return [m for m in METRICS.values() if metric_allowed(user, m)]


def visible_dims(user: User) -> list[Dim]:
    return [d for d in DIMS.values() if dim_allowed(user, d)]


def scope_clause(user: User) -> tuple[str, list]:
    col = user.row_scope_col
    if col:
        if not user.scope_value:
            raise AccessError("Scoped role without a scope value")
        return f"{col} = ?", [user.scope_value]
    return "1=1", []


def _scope_key(user: User) -> str:
    return f"{user.role}|{user.row_scope_col}|{user.scope_value}"


# ---------------------------------------------------------------------- cache
_CACHE: dict[str, tuple[float, object]] = {}
CACHE_STATS = {"hits": 0, "misses": 0}


def cached(user: User, name: str, payload: dict, fn: Callable[[], object]):
    key = f"{_scope_key(user)}::{name}::{json.dumps(payload, sort_keys=True, default=str)}"
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < CACHE_TTL_SECONDS:
        CACHE_STATS["hits"] += 1
        return hit[1]
    CACHE_STATS["misses"] += 1
    val = fn()
    _CACHE[key] = (now, val)
    if len(_CACHE) > 2000:
        for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:500]:
            _CACHE.pop(k, None)
    return val


# ---------------------------------------------------------------- filter parse
def _build_where(user: User, filters: dict | None) -> tuple[str, list]:
    clause, params = scope_clause(user)
    parts = [clause]
    for key, val in (filters or {}).items():
        if val in (None, "", []):
            continue
        if key in DATE_FILTERS:
            parts.append("order_date >= ?" if key == "date_from" else "order_date <= ?")
            params.append(str(val))
            continue
        dim = DIMS.get(key)
        if not dim:
            raise QueryError(f"Unknown filter '{key}'")
        if not dim_allowed(user, dim):
            raise AccessError(f"Your role cannot filter by {dim.label}")
        vals = val if isinstance(val, (list, tuple)) else [val]
        if dim.key in ("year", "month_of_year"):
            vals = [int(v) for v in vals]
        elif dim.key == "discount":
            vals = [float(v) for v in vals]
        parts.append(f"{dim.col} IN ({','.join('?' * len(vals))})")
        params.extend(vals)
    return " AND ".join(parts), params


def _round(v):
    if isinstance(v, float):
        return round(v, 2)
    return v


# ---------------------------------------------------------------------- query
def run_query(
    user: User,
    metrics: list[str],
    group_by: list[str] | None = None,
    filters: dict | None = None,
    basis: str = "net",
    order_by: str | None = None,
    desc: bool = True,
    limit: int | None = None,
) -> dict:
    group_by = list(group_by or [])
    if not metrics:
        raise QueryError("At least one metric is required")
    if len(group_by) > 2:
        raise QueryError("At most two group-by dimensions")
    if basis not in ("net", "gross"):
        raise QueryError("basis must be 'net' or 'gross'")

    ms = []
    for k in metrics:
        m = METRICS.get(k)
        if not m:
            raise QueryError(f"Unknown metric '{k}'")
        if not metric_allowed(user, m):
            raise AccessError(f"Your role cannot access the metric '{m.label}'")
        ms.append(m)
    ds = []
    for k in group_by:
        d = DIMS.get(k)
        if not d:
            raise QueryError(f"Unknown dimension '{k}'")
        if not dim_allowed(user, d):
            raise AccessError(f"Your role cannot group by '{d.label}'")
        ds.append(d)

    payload = dict(metrics=metrics, group_by=group_by, filters=filters, basis=basis,
                   order_by=order_by, desc=desc, limit=limit)
    return cached(user, "query", payload, lambda: _execute(user, ms, ds, filters, basis, order_by, desc, limit))


def _execute(user, ms, ds, filters, basis, order_by, desc, limit):
    cond = "net_flag = 1" if basis == "net" else "1=1"
    where, params = _build_where(user, filters)
    # internal aliases (d_/m_) so they can never collide with real column names such as month/quarter/revenue
    select = [f"{d.col} AS d_{d.key}" for d in ds] + [f"{m.sql(cond)} AS m_{m.key}" for m in ms]
    sql = f"SELECT {', '.join(select)} FROM orders WHERE {where}"
    if ds:
        sql += " GROUP BY " + ", ".join(d.col for d in ds)
        all_time = all(d.kind in ("time", "number") for d in ds)
        if order_by:
            if order_by in {m.key for m in ms}:
                sql += f" ORDER BY m_{order_by} {'DESC' if desc else 'ASC'}"
            elif order_by in {d.key for d in ds}:
                sql += f" ORDER BY d_{order_by} {'DESC' if desc else 'ASC'}"
            else:
                raise QueryError("order_by must be one of the selected columns")
        elif all_time:
            sql += " ORDER BY " + ", ".join(f"d_{d.key}" for d in ds)
        else:
            sql += f" ORDER BY m_{ms[0].key} DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    t0 = time.perf_counter()
    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    ms_taken = (time.perf_counter() - t0) * 1000
    cols = [f"d_{d.key}" for d in ds] + [f"m_{m.key}" for m in ms]
    return {
        "columns": [
            {"key": d.key, "label": d.label, "role": "dimension", "kind": d.kind} for d in ds
        ] + [{"key": m.key, "label": m.label, "role": "metric", "fmt": m.fmt} for m in ms],
        "rows": [[_round(r[c]) for c in cols] for r in rows],
        "basis": basis,
        "sql": _inline(sql, params),
        "ms": round(ms_taken, 2),
    }


def _inline(sql: str, params: list) -> str:
    out = sql
    for p in params:
        out = out.replace("?", repr(p), 1)
    return out


def records(result: dict) -> list[dict]:
    keys = [c["key"] for c in result["columns"]]
    return [dict(zip(keys, r)) for r in result["rows"]]


# ----------------------------------------------------------------------- KPIs
KPI_ORDER = ["revenue", "profit", "margin", "orders", "aov", "return_rate", "cancel_rate",
             "avg_shipping_days", "shipping_cost", "units", "customers"]


def kpis(user: User, filters: dict | None, basis: str) -> dict:
    keys = [k for k in KPI_ORDER if metric_allowed(user, METRICS[k])][:8]
    cur = records(run_query(user, keys, [], filters, basis))[0]
    spark = run_query(user, keys, ["month"], filters, basis)
    spark_rows = records(spark)

    prev = None
    years = (filters or {}).get("year")
    if years and len(years) == 1:
        pf = {**filters, "year": [int(years[0]) - 1]}
        res = records(run_query(user, keys, [], pf, basis))
        prev = res[0] if res and res[0].get(keys[0]) is not None else None

    cards = []
    for k in keys:
        m = METRICS[k]
        delta = None
        if prev and prev.get(k) not in (None, 0) and cur.get(k) is not None:
            if m.fmt == "percent":
                delta = {"abs": round(cur[k] - prev[k], 2), "unit": "pp"}
            else:
                delta = {"pct": round((cur[k] - prev[k]) / abs(prev[k]) * 100, 1)}
        cards.append({
            "key": k, "label": m.label, "fmt": m.fmt, "value": cur.get(k), "delta": delta,
            "spark": [r[k] for r in spark_rows],
            "good_direction": "down" if k in ("return_rate", "cancel_rate", "avg_shipping_days", "shipping_cost") else "up",
        })
    return {"cards": cards, "compared_to": int(years[0]) - 1 if prev else None, "basis": basis}


# -------------------------------------------------------------- filter options
OPTION_DIMS = ["year", "quarter_of_year", "season", "region", "country", "category", "sub_category", "segment", "gender",
               "shipping_method", "payment_method", "status"]


def filter_options(user: User) -> dict:
    def build():
        out = {}
        where, params = scope_clause(user)
        with get_db() as db:
            for k in OPTION_DIMS:
                d = DIMS[k]
                if not dim_allowed(user, d):
                    continue
                vals = [r[0] for r in db.execute(
                    f"SELECT DISTINCT {d.col} FROM orders WHERE {where} ORDER BY 1", params)]
                out[k] = {"label": d.label, "values": vals}
            lo, hi = db.execute(f"SELECT MIN(order_date), MAX(order_date) FROM orders WHERE {where}", params).fetchone()
        return {"dims": out, "date_range": [lo, hi]}

    return cached(user, "options", {}, build)


# --------------------------------------------------------------------- orders
def visible_order_columns(user: User):
    return [c for c in ORDER_COLUMNS if c[0] not in user.hidden]


def list_orders(user: User, filters: dict | None, search: str | None, sort: str | None,
                desc: bool, page: int, page_size: int, export: bool = False) -> dict:
    cols = visible_order_columns(user)
    allowed = {c[0] for c in cols}
    where, params = _build_where(user, filters)
    if search:
        like = f"%{search.strip()}%"
        fields = [f for f in ("order_id", "product_name", "customer_id") if f in allowed]
        where += " AND (" + " OR ".join(f"{f} LIKE ?" for f in fields) + ")"
        params += [like] * len(fields)
    sort_col = sort if sort in allowed else "order_date"
    page_size = max(1, min(page_size, 200))
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM orders WHERE {where}", params).fetchone()[0]
        select = ", ".join(c[0] for c in cols)
        sql = f"SELECT {select} FROM orders WHERE {where} ORDER BY {sort_col} {'DESC' if desc else 'ASC'}, order_id"
        if export:
            sql += " LIMIT 50000"
            rows = db.execute(sql, params).fetchall()
        else:
            rows = db.execute(sql + " LIMIT ? OFFSET ?", params + [page_size, max(0, page - 1) * page_size]).fetchall()
    return {
        "columns": [{"key": c[0], "label": c[1], "fmt": c[2]} for c in cols],
        "rows": [list(r) for r in rows],
        "total": total, "page": page, "page_size": page_size,
    }


def detect_tail_off(values: list[float], max_tail: int = 8) -> int:
    """Number of trailing periods that collapse below half of the best 12-period average (0 if none).

    A smooth decay to near zero at the end of a series usually means an incomplete / late-loaded data extract
    rather than a genuine business collapse, so analyses should flag it instead of extrapolating it.
    """
    if len(values) < 18:
        return 0
    peak = max(sum(values[i:i + 12]) / 12 for i in range(len(values) - 11))
    n = 0
    for v in reversed(values[-max_tail:]):
        if v is not None and v < 0.5 * peak:
            n += 1
        else:
            break
    return n if n >= 2 else 0

# ------------------------------------------------------------------- insights
def _money(metric: str, v: float) -> str:
    return f"${v:,.0f}" if METRICS[metric].fmt == "currency" else f"{v:,.0f}"


def insights(user: User, filters: dict | None, basis: str) -> list[dict]:
    """Rule-based findings computed live from the user's own scope (every query is role-scoped)."""
    out: list[dict] = []

    def q(metrics, by, **kw):
        try:
            return records(run_query(user, metrics, by, filters, basis, **kw))
        except (AccessError, QueryError):
            return []

    money = metric_allowed(user, METRICS["revenue"])

    # 0. data completeness: does the series taper off at the end?
    monthly = q(["orders"], ["month"])
    tail = detect_tail_off([r["orders"] for r in monthly]) if monthly else 0
    if tail:
        peak_row = max(monthly, key=lambda r: r["orders"])
        out.append({
            "tone": "warn",
            "title": f"Orders taper off to {monthly[-1]['orders']:,.0f} a month by {monthly[-1]['month']} - check data completeness",
            "text": f"Monthly orders peak at {peak_row['orders']:,.0f} ({peak_row['month']}) and then decline steadily for the last {tail}+ months "
                    f"down to {monthly[-1]['orders']:,.0f}. A smooth slide to near zero looks like an incomplete or late-loaded data extract rather "
                    "than a real collapse in demand - confirm the cut-off date before drawing conclusions about the latest year.",
        })

    # 1. year-over-year momentum (+ is the change uniform across regions?)
    rows = q(["orders", "revenue"] if money else ["orders"], ["year"])
    if len(rows) >= 2:
        a, b = rows[-2], rows[-1]
        key = "revenue" if "revenue" in b else "orders"
        if a[key]:
            ch = (b[key] - a[key]) / a[key] * 100
            extra = ""
            by_region = q(["orders"], ["year", "region"])
            changes = {}
            for r in by_region:
                changes.setdefault(r["region"], {})[r["year"]] = r["orders"]
            pct = {reg: (v[b["year"]] - v[a["year"]]) / v[a["year"]] * 100 for reg, v in changes.items()
                   if v.get(a["year"]) and b["year"] in v}
            if tail:
                extra = " Most of the shortfall sits in the final months, where volume tapers to almost nothing - see the data-completeness note above before acting on this."
            elif len(pct) >= 3 and abs(ch) >= 15:
                lo, hi = min(pct.values()), max(pct.values())
                if hi - lo < 8:
                    extra = (f" Order volume moved by {lo:.0f}% to {hi:.0f}% in every region - a drop this uniform points to a company-wide "
                             "or data-completeness cause rather than a regional problem. Check whether the latest year is fully loaded.")
                else:
                    worst = min(pct, key=pct.get)
                    extra = f" {worst} moved the most ({pct[worst]:.0f}%)."
            out.append({
                "tone": "bad" if ch < -10 else "good" if ch > 10 else "neutral",
                "title": f"{b['year']} {METRICS[key].label.lower()} {'fell' if ch < 0 else 'grew'} {abs(ch):.0f}% vs {a['year']}",
                "text": f"{b['year']}: {_money(key, b[key])} vs {a['year']}: {_money(key, a[key])}. "
                        + (f"Order volume moved from {a['orders']:,.0f} to {b['orders']:,.0f}." if key != "orders" else "")
                        + (extra or " Worth a root-cause review."),
            })
    # 2. concentration by category
    if money and len(visible := q(["revenue"], ["category"])) > 1:
        tot = sum(r["revenue"] for r in visible)
        top = visible[0]
        out.append({
            "tone": "warn" if top["revenue"] / tot > 0.5 else "neutral",
            "title": f"{top['category']} generates {top['revenue'] / tot * 100:.0f}% of revenue",
            "text": f"{top['category']} contributes ${top['revenue']:,.0f} of ${tot:,.0f}. "
                    + ("High dependence on a single category is a concentration risk." if top["revenue"] / tot > 0.5 else ""),
        })
    # 3. deep discounts destroy margin
    if metric_allowed(user, METRICS["loss_rate"]):
        rows = q(["orders", "margin", "loss_rate"], ["discount"])
        deep = [r for r in rows if r["discount"] >= 0.3]
        light = [r for r in rows if r["discount"] < 0.3]
        if deep and light:
            dn = sum(r["orders"] for r in deep)
            dloss = sum(r["orders"] * r["loss_rate"] for r in deep) / dn if dn else 0
            lm = sum(r["orders"] * r["margin"] for r in light) / max(1, sum(r["orders"] for r in light))
            out.append({
                "tone": "bad",
                "title": f"Discounts of 30%+ make {dloss:.0f}% of those orders loss-making",
                "text": f"{dn:,.0f} orders carry a discount of 30% or more. Orders below 30% average a {lm:.0f}% margin; "
                        "above it, margin collapses and many orders lose money. Capping discounts at 25% protects profit.",
            })
    # 4. delivery time: what actually drives it? (region vs shipping method)
    method = q(["avg_shipping_days", "avg_shipping_cost", "orders"], ["shipping_method"])
    method_spread = (max(r["avg_shipping_days"] for r in method) - min(r["avg_shipping_days"] for r in method)) if len(method) > 1 else 0
    for dim in ("region", "country"):
        geo = q(["avg_shipping_days", "orders"], [dim])
        if len(geo) >= 2:
            slow, fast = max(geo, key=lambda r: r["avg_shipping_days"]), min(geo, key=lambda r: r["avg_shipping_days"])
            spread = slow["avg_shipping_days"] - fast["avg_shipping_days"]
            if spread >= 2 and spread > 2 * method_spread:
                out.append({
                    "tone": "warn",
                    "title": f"Delivery time is driven by {dim}, not by shipping speed",
                    "text": f"{slow[dim]} averages {slow['avg_shipping_days']:.1f} days versus {fast['avg_shipping_days']:.1f} days for {fast[dim]} "
                            f"- a {spread:.1f}-day gap - while the four shipping methods differ by only {method_spread:.1f} days. "
                            "Fix lead times by lane (carriers, warehouses) rather than by upselling faster methods.",
                })
            break
    # 5. premium shipping is not faster
    d = {r["shipping_method"]: r for r in method}
    if "Economy" in d and "Overnight" in d and method_spread < 1:
        out.append({
            "tone": "warn",
            "title": "Premium shipping is not delivering faster",
            "text": f"Overnight averages {d['Overnight']['avg_shipping_days']:.1f} days at ${d['Overnight']['avg_shipping_cost']:.0f} per order, "
                    f"while Economy takes {d['Economy']['avg_shipping_days']:.1f} days at ${d['Economy']['avg_shipping_cost']:.0f}. "
                    "Customers pay for speed they do not receive - check carrier SLAs.",
        })
    # 6. returns hotspot
    rows = q(["return_rate", "orders"], ["category"])
    if len(rows) > 1:
        hi = max(rows, key=lambda r: r["return_rate"])
        lo = min(rows, key=lambda r: r["return_rate"])
        out.append({
            "tone": "warn",
            "title": f"{hi['category']} has the highest return rate ({hi['return_rate']:.1f}%)",
            "text": f"Lowest is {lo['category']} at {lo['return_rate']:.1f}%."
                    + (" Returned and cancelled orders are excluded from net revenue." if money else ""),
        })
    # 7. best month of year
    metric = "revenue" if money else "orders"
    rows = q([metric], ["month_of_year"])
    if rows:
        best = max(rows, key=lambda r: r[metric])
        names = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        out.append({
            "tone": "neutral",
            "title": f"{names[best['month_of_year'] - 1]} is the strongest month",
            "text": f"Peak {METRICS[metric].label.lower()} of {_money(metric, best[metric])} across all years - plan inventory and campaigns around it.",
        })
    # 8. segment value: spend vs profitability
    if money:
        rows = q(["revenue", "orders", "aov", "margin"], ["segment"])
        if len(rows) > 1:
            top = max(rows, key=lambda r: r["aov"])
            margins = [r["margin"] for r in rows if r["margin"] is not None]
            flat = margins and (max(margins) - min(margins)) < 3
            vip = next((r for r in rows if r["segment"] == "VIP"), None)
            new = next((r for r in rows if r["segment"] == "New"), None)
            out.append({
                "tone": "good",
                "title": f"{top['segment']} customers spend the most per order (${top['aov']:,.0f})",
                "text": " ".join(f"{r['segment']}: {r['orders']:,.0f} orders, AOV ${r['aov']:,.0f}." for r in rows)
                        + (f" Margins are nearly identical across segments ({min(margins):.0f}-{max(margins):.0f}%), so loyalty tiers "
                           "do not translate into higher profitability." if flat and vip and new else ""),
            })
    return out