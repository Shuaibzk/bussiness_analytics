"""Higher-level analytics built on the governed engine: customer analytics, forecasting, targets, record lookups.

Everything here goes through `engine` (scope + hidden-column enforcement) or applies the same scope clause itself.
"""
from __future__ import annotations

import math
import statistics

from . import engine
from .db import get_db
from .engine import (METRICS, AccessError, QueryError, dim_allowed, metric_allowed, records, run_query, scope_clause,
                     visible_order_columns, _build_where)
from .security import User


# ------------------------------------------------------------------ customers
def customer_stats(user: User, filters: dict | None, basis: str) -> dict:
    def build():
        has_ids = "customer_id" not in user.hidden
        out: dict = {"customer_access": has_ids}
        seg_metrics = [k for k in ("orders", "revenue", "aov", "margin", "return_rate", "avg_discount") if metric_allowed(user, METRICS[k])]
        for key, dim, n in (("segments", "segment", None), ("gender", "gender", 4)):
            out[key] = run_query(user, seg_metrics[:n] if n else seg_metrics, [dim], filters, basis) if dim_allowed(user, engine.DIMS[dim]) else None
        if not has_ids:
            return out

        where, params = _build_where(user, filters)
        net = "net_flag = 1" if basis == "net" else "1=1"
        money = metric_allowed(user, METRICS["revenue"])
        with get_db() as db:
            rows = db.execute(
                f"SELECT customer_id, MAX(customer_segment) seg, COUNT(*) n, MIN(order_date) first_order, MAX(order_date) last_order, "
                f"SUM(CASE WHEN {net} THEN revenue ELSE 0 END) rev, SUM(CASE WHEN {net} THEN profit ELSE 0 END) prof "
                f"FROM orders WHERE {where} GROUP BY customer_id", params).fetchall()
            sw, sp = scope_clause(user)
            first_seen = db.execute(f"SELECT customer_id, MIN(year) fy FROM orders WHERE {sw} GROUP BY customer_id", sp).fetchall()
            active = db.execute(f"SELECT DISTINCT customer_id, year FROM orders WHERE {sw}", sp).fetchall()
        n_cust = len(rows)
        if not n_cust:
            out["customers"] = None
            return out
        orders_per = [r["n"] for r in rows]
        repeat = sum(1 for n in orders_per if n > 1)
        dist = {"1": 0, "2": 0, "3": 0, "4": 0, "5+": 0}
        for n in orders_per:
            dist[str(n) if n < 5 else "5+"] += 1
        ranked = sorted(rows, key=lambda r: -(r["rev"] or 0))

        def share(frac):
            k = max(1, int(round(n_cust * frac)))
            tot = sum(r["rev"] or 0 for r in rows) or 1
            return round(sum(r["rev"] or 0 for r in ranked[:k]) / tot * 100, 1)

        fy = {r["customer_id"]: r["fy"] for r in first_seen}
        years: dict[int, dict] = {}
        for r in active:
            y = years.setdefault(r["year"], {"year": r["year"], "new": 0, "returning": 0})
            y["new" if fy[r["customer_id"]] == r["year"] else "returning"] += 1

        out["customers"] = {
            "unique": n_cust,
            "repeat": repeat,
            "repeat_rate": round(repeat / n_cust * 100, 1),
            "orders_per_customer": round(sum(orders_per) / n_cust, 2),
            "max_orders": max(orders_per),
            "distribution": [{"orders": k, "customers": v} for k, v in dist.items()],
            "new_vs_returning": [years[y] for y in sorted(years)],
            "concentration": {"top_1pct": share(0.01), "top_10pct": share(0.10), "top_20pct": share(0.20)} if money else None,
            "top": [
                {"customer_id": r["customer_id"], "segment": r["seg"], "orders": r["n"], "first_order": r["first_order"],
                 "last_order": r["last_order"], **({"revenue": round(r["rev"] or 0, 2)} if money else {}),
                 **({"profit": round(r["prof"] or 0, 2)} if money and metric_allowed(user, METRICS["profit"]) else {})}
                for r in ranked[:10]
            ] if money else [],
        }
        return out

    return engine.cached(user, "customers", {"f": filters, "b": basis}, build)


def customer_insights(user: User, filters: dict | None, basis: str) -> list[dict]:
    """Extra insights for roles allowed to see customer ids (admin, regional manager)."""
    s = customer_stats(user, filters, basis)
    c = s.get("customers")
    if not c:
        return []
    out = [{
        "tone": "good" if c["repeat_rate"] >= 40 else "warn",
        "title": f"{c['repeat_rate']:.0f}% of customers have ordered more than once",
        "text": f"{c['repeat']:,} of {c['unique']:,} customers are repeat buyers, averaging {c['orders_per_customer']:.1f} orders each "
                f"(best customer: {c['max_orders']} orders). Repeat buyers are the cheapest revenue to grow.",
    }]
    conc = c.get("concentration")
    if conc:
        out.append({
            "tone": "neutral",
            "title": f"The top 1% of customers generate {conc['top_1pct']:.0f}% of revenue",
            "text": f"The top 10% account for {conc['top_10pct']:.0f}% and the top 20% for {conc['top_20pct']:.0f}% - revenue is fairly "
                    "spread out, so there is little single-customer dependency.",
        })
    return out


# ----------------------------------------------------------------- record lookups
def get_order(user: User, order_id: str) -> dict | None:
    """One order, only if it is inside the user's row scope, restricted to the columns their role may see."""
    cols = visible_order_columns(user)
    where, params = scope_clause(user)
    with get_db() as db:
        row = db.execute(f"SELECT {', '.join(c[0] for c in cols)} FROM orders WHERE order_id = ? AND {where}", [order_id.upper()] + params).fetchone()
    if not row:
        return None
    return {"columns": [{"key": c[0], "label": c[1], "fmt": c[2]} for c in cols], "row": list(row)}


def get_customer(user: User, customer_id: str) -> dict | None:
    if "customer_id" in user.hidden:
        raise AccessError("Your role cannot look up individual customers")
    where, params = scope_clause(user)
    money = metric_allowed(user, METRICS["revenue"])
    with get_db() as db:
        rows = db.execute(
            f"SELECT order_id, order_date, product_name, category, region, order_status, customer_segment, customer_gender, "
            f"net_flag, {'revenue, profit' if money else '0 revenue, 0 profit'} FROM orders WHERE customer_id = ? AND {where} ORDER BY order_date",
            [customer_id.upper()] + params).fetchall()
    if not rows:
        return None
    net = [r for r in rows if r["net_flag"]]
    return {
        "customer_id": customer_id.upper(), "segment": rows[0]["customer_segment"], "gender": rows[0]["customer_gender"],
        "orders": len(rows), "first": rows[0]["order_date"], "last": rows[-1]["order_date"],
        "net_revenue": round(sum(r["revenue"] for r in net), 2) if money else None,
        "categories": sorted({r["category"] for r in rows}),
        "list": [{"order_id": r["order_id"], "date": r["order_date"], "product": r["product_name"], "status": r["order_status"],
                  **({"revenue": r["revenue"]} if money else {})} for r in rows[-10:][::-1]],
    }


# --------------------------------------------------------------------- forecast
def _add_months(ym: str, k: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12}-{t % 12 + 1:02d}"


def forecast(user: User, metric: str, filters: dict | None, basis: str, horizon: int = 6, baseline: str = "auto") -> dict:
    """Seasonal-baseline projection: recent level x historical month-of-year seasonality (+ a damped trend).

    Deliberately simple and explainable - it is a planning aid, not a statistical model, and the response says so.
    If the series tapers off at the end (likely an incomplete data extract) the level is taken from the last stable
    12 months instead ("stable"), unless the caller insists on "recent".
    """
    def build():
        res = run_query(user, [metric], ["month"], filters, basis)
        series = [(r[0], r[1]) for r in res["rows"] if r[1] is not None]
        if len(series) < 24:
            return {"available": False, "reason": "Needs at least 24 months of history for the current filters."}
        tail = engine.detect_tail_off([v for _, v in series])
        use = "stable" if (baseline == "stable" or (baseline == "auto" and tail)) else "recent"
        base_series = series[:-tail] if (use == "stable" and tail) else series
        if len(base_series) < 18:
            base_series, use = series, "recent"
        vals = {m: v for m, v in series}
        # seasonal indices: month value relative to its own year's average, averaged over complete years
        by_year: dict[str, list[tuple[int, float]]] = {}
        for m, v in series:
            by_year.setdefault(m[:4], []).append((int(m[5:7]), v))
        idx: dict[int, list[float]] = {}
        for y, items in by_year.items():
            if len(items) < 12:
                continue
            avg = sum(v for _, v in items) / len(items) or 1
            for mo, v in items:
                idx.setdefault(mo, []).append(v / avg)
        season = {mo: sum(x) / len(x) for mo, x in idx.items()}
        if len(season) < 12:
            return {"available": False, "reason": "Needs at least one full calendar year to estimate seasonality."}
        last = series[-1][0]
        desea = [v / season[int(m[5:7])] for m, v in base_series[-12:]]
        level = sum(desea[-6:]) / 6
        slope = (sum(desea[-6:]) / 6 - sum(desea[:6]) / 6) / 6
        resid = [abs(d - sum(desea) / 12) / (sum(desea) / 12 or 1) for d in desea]
        band = max(0.08, min(0.35, statistics.mean(resid) * 1.6))
        out = []
        for k in range(1, horizon + 1):
            m = _add_months(last, k)
            base = level + slope * sum(0.8 ** i for i in range(1, k + 1))  # damped trend
            v = max(0.0, base * season[int(m[5:7])])
            out.append({"month": m, "value": round(v, 2), "low": round(v * (1 - band), 2), "high": round(v * (1 + band), 2)})
        hist = [{"month": m, "value": round(vals[m], 2)} for m, _ in series[-24:]]
        return {"available": True, "history": hist, "forecast": out, "band_pct": round(band * 100),
                "baseline": use, "tail_months": tail, "baseline_ends": base_series[-1][0],
                "method": "Recent 6-month level x historical seasonality, with a damped trend. A planning aid, not a statistical guarantee.",
                "warning": (f"The last {tail} months taper off sharply (likely an incomplete data extract). "
                            + ("The projection uses the last stable 12 months (to " + base_series[-1][0] + ") as its level - read it as 'if demand returned to normal'."
                               if use == "stable" else "You chose to project from those low recent months, so the forecast is very low."))
                if tail else None}

    return engine.cached(user, "forecast", {"m": metric, "f": filters, "b": basis, "h": horizon, "base": baseline}, build)


# ---------------------------------------------------------------------- targets
TARGET_METRICS = ("revenue", "profit", "orders")


def targets_status(user: User) -> list[dict]:
    with get_db() as db:
        rows = db.execute("SELECT metric, year, value FROM targets WHERE user_id = ? ORDER BY year DESC, metric", (user.id,)).fetchall()
    out = []
    for r in rows:
        if r["metric"] not in TARGET_METRICS or not metric_allowed(user, METRICS[r["metric"]]):
            continue
        res = records(run_query(user, [r["metric"]], [], {"year": [r["year"]]}, "net"))
        actual = (res[0][r["metric"]] if res else 0) or 0
        out.append({"metric": r["metric"], "label": METRICS[r["metric"]].label, "fmt": METRICS[r["metric"]].fmt, "year": r["year"],
                    "target": r["value"], "actual": round(actual, 2), "pct": round(actual / r["value"] * 100, 1) if r["value"] else None,
                    "gap": round(r["value"] - actual, 2)})
    return out


def set_target(user: User, metric: str, year: int, value: float) -> None:
    if metric not in TARGET_METRICS:
        raise QueryError("Targets can be set for revenue, profit or orders")
    if not metric_allowed(user, METRICS[metric]):
        raise AccessError(f"Your role cannot access '{METRICS[metric].label}'")
    if not (2000 <= year <= 2100):
        raise QueryError("Invalid year")
    if not (isinstance(value, (int, float)) and math.isfinite(value) and 0 < value < 1e12):
        raise QueryError("Target must be a positive number")
    with get_db() as db:
        db.execute("INSERT INTO targets (user_id, metric, year, value) VALUES (?,?,?,?) "
                   "ON DUPLICATE KEY UPDATE value = VALUES(value)", (user.id, metric, year, float(value)))


def delete_target(user: User, metric: str, year: int) -> None:
    with get_db() as db:
        db.execute("DELETE FROM targets WHERE user_id = ? AND metric = ? AND year = ?", (user.id, metric, year))
