"""AI analyst: question -> (guard) -> plan -> governed query + hybrid retrieval -> grounded answer.

Design principles
  * The LLM never sees data the user's role may not access: the planner's JSON schema only contains the
    metrics/dimensions the role is allowed, queries run through engine.run_query (scope injected in code), and
    retrieval filters documents by role BEFORE ranking.
  * Exact numbers come from SQL, never from the model's memory or arithmetic.
  * Entities (years, regions, categories...) are extracted deterministically; the LLM only chooses
    metric / grouping / intent via schema-constrained JSON.  Small local models are good at classification, poor at
    precision - so we use them for the former only.
  * If Ollama is unavailable the whole pipeline still answers (rule-based plan + templated answer).
"""
from __future__ import annotations

import json
import re
import time
from typing import Iterator

from . import analytics_extra, engine, llm
from .db import get_db
from .rag import retriever
from .security import User

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
MONTH_FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

# ---------------------------------------------------------------- catalogue
_CAT: dict | None = None


def catalogue() -> dict:
    global _CAT
    if _CAT is None:
        with get_db() as db:
            rows = db.execute("SELECT DISTINCT region, country, category, sub_category, product_name, customer_segment, "
                              "shipping_method, payment_method FROM orders").fetchall()
            years = [r[0] for r in db.execute("SELECT DISTINCT year FROM orders ORDER BY 1")]
        c = {"region": {}, "country": {}, "category": {}, "sub_category": {}, "product": {}, "years": years,
             "segment": set(), "shipping_method": set(), "payment_method": set()}
        for r in rows:
            c["region"][r["region"]] = r["region"]
            c["country"][r["country"]] = r["region"]
            c["category"][r["category"]] = r["category"]
            c["sub_category"][r["sub_category"]] = r["category"]
            c["product"][r["product_name"]] = r["category"]
            c["segment"].add(r["customer_segment"])
            c["shipping_method"].add(r["shipping_method"])
            c["payment_method"].add(r["payment_method"])
        _CAT = c
    return _CAT


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(word.lower())}(?![a-z0-9])", text) is not None


# -------------------------------------------------------------------- guard
BLOCKED_TERMS = {
    "revenue": r"revenue|sales|turnover|income|\bearn",
    "profit": r"profit|margin",
    "cost": r"\bcosts?\b|cogs",
    "unit_price": r"unit price|\bprices?\b|pricing",
    "discount": r"discount",
    "customer_id": r"customer ids?|customer id|who (bought|ordered)|which customers?|individual customers?",
}


def guard(user: User, question: str) -> str | None:
    """Deterministic pre-check. Returns a refusal message, or None if the question may proceed."""
    q = question.lower()
    if "customer_id" in user.hidden and re.search(r"\bcust-\d+", q):
        return (f"I can't help with that: as **{user.policy['label']}** you don't have access to customer identifiers. "
                "I can answer questions about orders, products, regions and customer segments instead.")
    q_noship = re.sub(r"shipping costs?|freight", "shipping", q)
    for col, pattern in BLOCKED_TERMS.items():
        if col in user.hidden and re.search(pattern, q_noship):
            return (f"I can't help with that: as **{user.policy['label']}** you don't have access to "
                    f"{col.replace('_', ' ')} information. I can answer questions about orders, shipping, delivery times, "
                    "returns and cancellations instead.")
    col, val = user.row_scope_col, user.scope_value
    if col:
        cat = catalogue()
        for r, _ in cat["region"].items():
            if col == "region" and r != val and _has_word(q, r):
                return _scope_msg(user)
        if col == "region":
            for c, reg in cat["country"].items():
                if reg != val and _has_word(q, c):
                    return _scope_msg(user)
        if col == "category":
            for kind in ("category", "sub_category", "product"):
                for name, parent in cat[kind].items():
                    if parent != val and _has_word(q, name):
                        return _scope_msg(user)
    return None


def _scope_msg(user: User) -> str:
    what = "region" if user.row_scope_col == "region" else "product category"
    return (f"That falls outside your access. As **{user.policy['label']}** you can only view data for the "
            f"**{user.scope_value}** {what}. Ask me about {user.scope_value} and I'll gladly help.")


# ------------------------------------------------------------------ planning
METRIC_PATTERNS = [
    ("loss_rate", r"loss[- ]making|lose money|losing money|unprofitable|negative profit"),
    ("avg_shipping_cost", r"(average|avg) shipping cost"),
    ("shipping_cost", r"shipping costs?|freight|postage"),
    ("avg_shipping_days", r"delivery (time|days|speed)|shipping (time|days)|how long|days to deliver|fastest|slowest|delivery performance"),
    ("aov", r"average order value|\baov\b|avg order|basket"),
    ("margin", r"margin"),
    ("profit", r"profit|earn"),
    ("revenue", r"revenue|sales|turnover|income"),
    ("return_rate", r"return"),
    ("cancel_rate", r"cancel"),
    ("customers", r"unique customers|how many customers|number of customers|customer count"),
    ("units", r"units|quantity|items sold|volume"),
    ("avg_discount", r"discount"),
    ("orders", r"orders?|transactions|purchases"),
]
DIM_PATTERNS = [
    ("sub_category", r"sub-?categor"),
    ("category", r"categor"),
    ("region", r"\bregions?\b"),
    ("country", r"countr(y|ies)"),
    ("product", r"\bproducts?\b|\bitems?\b|best[- ]sell"),
    ("segment", r"segments?"),
    ("gender", r"gender"),
    ("shipping_method", r"shipping (method|type|option)s?|carrier|delivery method"),
    ("payment_method", r"payment"),
    ("status", r"\bstatus"),
    ("quarter_of_year", r"\bquarters\b|quarterly|each quarter"),
    ("month", r"monthly|each month|by month|per month|month by month|trend|over time|growth"),
    ("month_of_year", r"seasonality|which month|best month|worst month|peak month"),
    ("year", r"\byearly\b|annual|by year|per year|each year|year[- ]over[- ]year|yoy|year by year"),
    ("season", r"season"),
    ("discount", r"discount (level|rate|tier|band)s?|by discount|per discount"),
]
GROUPING_CUE = r"\b(by|per|each|across|which|what|top|best|worst|highest|lowest|compare|breakdown|rank|most|least)\b"


def heuristic_plan(user: User, q: str) -> dict:
    ql = q.lower()
    allowed_m = {m.key for m in engine.visible_metrics(user)}
    allowed_d = {d.key for d in engine.visible_dims(user)}
    metrics = []
    for key, pat in METRIC_PATTERNS:
        if re.search(pat, ql) and key in allowed_m and key not in metrics:
            metrics.append(key)
    if re.fullmatch(r"\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks?|thank you|who are you|what can you do)\W*", ql):
        return {"intent": "greeting", "metrics": [], "group_by": [], "sort": "desc", "basis": "net"}
    if re.search(r"how many|number of|count of|total number", ql) and {"return_rate", "cancel_rate"} & set(metrics):
        metrics = ["orders"] + [m for m in metrics if m not in ("return_rate", "cancel_rate", "orders")]
    if "orders" in metrics and len(metrics) > 1 and not re.search(r"how many orders|number of orders|order count|orders? and", ql):
        metrics.remove("orders")
    group_by = []
    if re.search(GROUPING_CUE + r"|trend|monthly|quarterly|yearly|annual", ql):
        for key, pat in DIM_PATTERNS:
            if re.search(pat, ql) and key in allowed_d and key not in group_by:
                group_by.append(key)
    if "sub_category" in group_by and "category" in group_by:
        group_by.remove("category")
    if "month" in group_by and "year" in group_by:
        group_by.remove("year")
    if "discount" in group_by and "avg_discount" in metrics:
        metrics.remove("avg_discount")
    if group_by == ["discount"] and metrics == ["loss_rate"] and "margin" in allowed_m:
        metrics.append("margin")
    chosen = metrics[:2] or []
    return {"intent": "data" if chosen else "explain", "metrics": chosen, "group_by": group_by[:2],
            # "slowest delivery" = the highest number of days (desc); "fastest delivery" = the lowest (asc)
            "sort": "asc" if (re.search(r"\b(lowest|worst|bottom|least|fewest|smallest|weakest)\b", ql)
                              or (re.search(r"\b(fastest|quickest|shortest)\b", ql) and "avg_shipping_days" in chosen)) else "desc",
            "basis": "gross" if "gross" in ql else "net"}


def extract_filters(user: User, q: str) -> dict:
    ql = q.lower()
    cat = catalogue()
    f: dict[str, list] = {}
    years = [int(y) for y in re.findall(r"\b(20[12]\d)\b", ql) if int(y) in cat["years"]]
    if re.search(r"last year|latest year|this year|most recent year", ql):
        years.append(max(cat["years"]))
    if years:
        f["year"] = sorted(set(years))
    m = re.search(r"\bq([1-4])\b", ql)
    if m:
        f["quarter_of_year"] = [f"Q{m.group(1)}"]
    for i, name in enumerate(MONTH_FULL):
        if _has_word(ql, name) and not (name == "may" and not re.search(r"\bin may\b|\bmay (sales|revenue|orders)", ql)):
            f["month_of_year"] = [i + 1]
    for s in ("winter", "spring", "summer", "fall", "autumn"):
        if _has_word(ql, s):
            f["season"] = ["Fall" if s == "autumn" else s.capitalize()]
    for dim, names in (("region", cat["region"]), ("country", cat["country"]), ("category", cat["category"]),
                       ("sub_category", cat["sub_category"]), ("product", cat["product"])):
        hits = [n for n in names if _has_word(ql, n)]
        if dim == "category" and "sub_category" in f:
            hits = [h for h in hits if h not in f.get("sub_category", [])]
        if hits:
            f[dim] = hits
    # "USA" / "UK" synonyms
    if _has_word(ql, "united states") or _has_word(ql, "america") and "region" not in f:
        f.setdefault("country", []).append("USA")
    if _has_word(ql, "united kingdom") or _has_word(ql, "britain"):
        f.setdefault("country", []).append("UK")
    seg = [s for s in cat["segment"] if _has_word(ql, s) and (re.search(r"segment|customers?", ql) or s in ("VIP", "Premium"))]
    if seg:
        f["segment"] = seg
    for dim, names in (("shipping_method", cat["shipping_method"]), ("payment_method", cat["payment_method"])):
        hits = [n for n in names if _has_word(ql, n)]
        if hits:
            f[dim] = hits
    if re.search(r"\bpaypal\b", ql):
        f["payment_method"] = ["PayPal"]
    for g in ("male", "female"):
        if _has_word(ql, g + " customers") or _has_word(ql, g + "s"):
            f["gender"] = [g.capitalize()]
    st = [s.capitalize() for s in ("delivered", "processing") if _has_word(ql, s)]
    if re.search(r"(returned|cancelled|canceled) orders|orders (that were |were )?(returned|cancelled|canceled)", ql):
        st += ["Returned"] if "return" in ql else []
        st += ["Cancelled"] if "cancel" in ql else []
    if st:
        f["status"] = st
    # drop filters the role cannot use (guard already rejected out-of-scope values)
    return {k: v for k, v in f.items() if k in {d.key for d in engine.visible_dims(user)}}


PLAN_SYSTEM = """You convert a business question about an e-commerce sales dataset into a JSON query plan.
Pick only from the allowed values in the schema. Rules:
- intent "data": the question wants numbers, rankings, comparisons or trends.
- intent "explain": the question wants meaning, reasons, recommendations, definitions or an overview.
- intent "greeting": hello/thanks/who are you. intent "off_topic": unrelated to this sales data.
- metrics: what to measure (max 2). group_by: how to split it (max 2). Use [] for a single total.
- "trend"/"over time" -> group_by ["month"]; "by year" -> ["year"]; "which region/category/country/product" -> that dimension.
- sort: "desc" for highest/top/best, "asc" for lowest/worst/bottom.
- basis: "net" unless the user explicitly asks for gross / including returns.
Metric guide:
{metric_guide}
Examples:
Q: Which region earns the most profit? -> {{"intent":"data","metrics":["profit"],"group_by":["region"],"sort":"desc","basis":"net"}}
Q: How has revenue changed month by month? -> {{"intent":"data","metrics":["revenue"],"group_by":["month"],"sort":"desc","basis":"net"}}
Q: Why are returns a problem? -> {{"intent":"explain","metrics":["return_rate"],"group_by":["category"],"sort":"desc","basis":"net"}}
Q: hi there -> {{"intent":"greeting","metrics":[],"group_by":[],"sort":"desc","basis":"net"}}"""


def llm_plan(user: User, q: str) -> dict | None:
    ms = engine.visible_metrics(user)
    ds = engine.visible_dims(user)
    schema = {
        "type": "object",
        "properties": {
            "intent": {"enum": ["data", "explain", "greeting", "off_topic"]},
            "metrics": {"type": "array", "items": {"enum": [m.key for m in ms]}, "maxItems": 2},
            "group_by": {"type": "array", "items": {"enum": [d.key for d in ds]}, "maxItems": 2},
            "sort": {"enum": ["desc", "asc"]},
            "basis": {"enum": ["net", "gross"]},
        },
        "required": ["intent", "metrics", "group_by", "sort", "basis"],
    }
    guide = "\n".join(f"- {m.key}: {m.desc}" for m in ms)
    try:
        raw = llm.chat([{"role": "system", "content": PLAN_SYSTEM.format(metric_guide=guide)},
                        {"role": "user", "content": q}], schema=schema, temperature=0, num_predict=120)
        return json.loads(raw)
    except Exception:
        return None


FOLLOWUP_RE = r"^(and|what about|how about|now|same|also|only|just|but|then|compare|versus|vs|by|per|break|split|show|for|in|why)\b"


def _last_plan(history: list[dict] | None) -> dict | None:
    for h in reversed(history or []):
        p = h.get("plan")
        if h.get("role") == "assistant" and isinstance(p, dict) and p.get("metrics") and p.get("intent") == "data":
            return p
    return None


def build_plan(user: User, question: str, history: list[dict] | None) -> tuple[dict, str]:
    """Returns (plan, source)."""
    heur = heuristic_plan(user, question)
    text = question
    ql0 = question.lower().strip()
    filters = extract_filters(user, text)
    plan, source = heur, "rules"

    # follow-ups ("and in Europe?", "now by category", "what about profit") inherit the previous query's plan and
    # change only what the new sentence changes - no model call needed, so they are also fast
    prev = _last_plan(history)
    short = len(question.split()) <= 10
    detected = heur["metrics"] or heur["group_by"] or filters  # an off-topic one-liner must not inherit the last query
    if prev and short and heur["intent"] != "greeting" and detected and (re.match(FOLLOWUP_RE, ql0) or not heur["metrics"]):
        plan = {
            "intent": "data",
            "metrics": heur["metrics"] or prev["metrics"],
            "group_by": heur["group_by"] or prev.get("group_by", []),
            "sort": "asc" if heur["sort"] == "asc" else prev.get("sort", "desc"),
            "basis": "gross" if "gross" in ql0 else prev.get("basis", "net"),
        }
        source = "follow-up"
        filters = {**prev.get("filters", {}), **filters}  # a new value for the same dimension replaces the old one
    elif llm.chat_ready():
        lp = llm_plan(user, text)
        if lp:
            plan, source = lp, "llm"
            # explicit keywords (deterministic) win over the model for metric / grouping / basis / sort
            if heur["metrics"]:
                plan["metrics"] = heur["metrics"]
                if plan["intent"] in ("off_topic", "greeting"):
                    plan["intent"] = "data"
            if heur["group_by"]:
                plan["group_by"] = heur["group_by"]
            plan["basis"] = heur["basis"]
            plan["sort"] = heur["sort"]  # direction words are deterministic ("slowest" means the most days)
    # the model may only add a grouping the wording actually asks for (it once invented group-by customer for "VIP AOV")
    ql = text.lower()
    if source == "llm" and not heur["group_by"] and not re.search(
            r"\b(by|per|each|across|which|compare|breakdown|rank|top|best|worst|highest|lowest|trend|over time)\b", ql):
        plan["group_by"] = []
    if "customer_id" in plan.get("group_by", []) and not re.search(r"customer ids?|each customer|best customers|top \d* ?customers|by customer", ql):
        plan["group_by"] = [d for d in plan["group_by"] if d != "customer_id"]
    if set(filters.get("status", [])) & {"Returned", "Cancelled"}:
        plan["basis"] = "gross"  # net basis excludes those statuses by definition
    if plan.get("metrics") == ["orders"] and not re.search(r"\bnet\b|delivered", question.lower()):
        plan["basis"] = "gross"  # "how many orders" means orders placed, not only fulfilled ones
    # comparison: a filter with several values of a dimension implies grouping by it
    for dim, vals in filters.items():
        if len(vals) > 1 and dim not in plan["group_by"] and len(plan["group_by"]) < 2 and dim != "year":
            plan["group_by"].append(dim)
    if len(filters.get("year", [])) > 1 and "year" not in plan["group_by"] and len(plan["group_by"]) < 2:
        plan["group_by"].append("year")
    allowed_m = {m.key for m in engine.visible_metrics(user)}
    allowed_d = {d.key for d in engine.visible_dims(user)}
    plan["metrics"] = [m for m in plan.get("metrics", []) if m in allowed_m][:2]
    plan["group_by"] = [d for d in plan.get("group_by", []) if d in allowed_d][:2]
    # drop a group_by that the filters already pin to a single value (e.g. "Asia revenue by region")
    plan["filters"] = filters
    top = re.search(r"\b(?:top|bottom|best|worst)\s+(\d{1,2})\b", question.lower())
    plan["limit"] = int(top.group(1)) if top else (10 if "product" in plan["group_by"] or "customer_id" in plan["group_by"] else None)
    if plan["intent"] == "data" and not plan["metrics"]:
        plan["metrics"] = ["orders"] if "orders" in allowed_m else []
    if plan["intent"] == "data" and not plan["metrics"]:
        plan["intent"] = "explain"
    return plan, source


# ------------------------------------------------------------------ formatting
def fmt(kind: str, v) -> str:
    if v is None:
        return "-"
    if kind == "currency":
        return f"${v:,.0f}" if abs(v) >= 1000 else f"${v:,.2f}"
    if kind == "percent":
        return f"{v:.1f}%"
    if kind == "days":
        return f"{v:.1f} days"
    if kind == "number":
        return f"{v:,.0f}"
    return str(v)


def dim_label(dim: str, v) -> str:
    if dim == "discount":
        return f"{float(v) * 100:.0f}%"
    if dim == "month_of_year":
        return MONTHS[int(v) - 1]
    return str(v)


def result_markdown(res: dict, max_rows: int = 20) -> str:
    cols = res["columns"]
    head = "| " + " | ".join(c["label"] for c in cols) + " |\n|" + "---|" * len(cols) + "\n"
    body = ""
    for r in res["rows"][:max_rows]:
        cells = [dim_label(c["key"], v) if c["role"] == "dimension" else fmt(c["fmt"], v) for c, v in zip(cols, r)]
        body += "| " + " | ".join(cells) + " |\n"
    if len(res["rows"]) > max_rows:
        body += f"(... {len(res['rows']) - max_rows} more rows)\n"
    return head + body


def build_chart(res: dict) -> dict | None:
    cols = res["columns"]
    dims = [c for c in cols if c["role"] == "dimension"]
    mets = [c for c in cols if c["role"] == "metric"]
    rows = res["rows"]
    if not dims or len(rows) < 2:
        return None
    nd = len(dims)
    if nd == 1:
        fmts = {m["fmt"] for m in mets}
        use = mets if len(fmts) == 1 else mets[:1]
        labels = [dim_label(dims[0]["key"], r[0]) for r in rows]
        series = [{"name": m["label"], "fmt": m["fmt"], "data": [r[1 + mets.index(m)] for r in rows]} for m in use]
    else:
        m = mets[0]
        xs = list(dict.fromkeys(r[0] for r in rows))
        ss = list(dict.fromkeys(r[1] for r in rows))
        lookup = {(r[0], r[1]): r[2] for r in rows}
        labels = [dim_label(dims[0]["key"], x) for x in xs]
        series = [{"name": dim_label(dims[1]["key"], s), "fmt": m["fmt"], "data": [lookup.get((x, s)) for x in xs]} for s in ss]
    kind = "line" if dims[0]["kind"] == "time" and dims[0]["key"] in ("month", "quarter", "year") and len(rows) > 3 else "bar"
    return {"type": kind, "labels": labels, "series": series}


# ---------------------------------------------------------------------- answer
ANSWER_SYSTEM = """You are Panorama Analyst, an assistant that answers questions about an e-commerce sales dataset (orders 2021-2024).
Rules:
1. Use ONLY the DATA RESULT and CONTEXT provided. Never invent numbers or facts.
2. Quote numbers exactly as written; do not do your own arithmetic or rounding beyond what is shown.
3. Lead with the direct answer in one sentence. Add at most two short supporting points, each of which must appear explicitly in the material (never infer rankings, causes or comparisons that are not stated). If asked "why", explain only from the CONTEXT.
4. State the basis (net = excluding returned and cancelled orders) when quoting revenue or profit.
5. If the answer is not in the provided material, say you cannot find it in the data you have access to.
6. Keep it under 120 words. Plain language for a business reader. Use **bold** for key figures. Currency is USD."""


def scope_note(user: User) -> str:
    if user.row_scope_col:
        return f"The user's access is limited to {user.row_scope_col} = {user.scope_value}; all figures already reflect only that slice."
    return "The user can see all regions and categories."


def filters_text(f: dict) -> str:
    return "; ".join(f"{k}={','.join(map(str, v))}" for k, v in f.items()) or "none"


def fallback_answer(plan: dict, res: dict | None, docs: list[dict]) -> str:
    if res and res["rows"]:
        cols = res["columns"]
        lines = []
        for r in res["rows"][:8]:
            parts = []
            for c, v in zip(cols, r):
                parts.append(dim_label(c["key"], v) if c["role"] == "dimension" else f"{c['label']}: {fmt(c['fmt'], v)}")
            lines.append("- " + (parts[0] + " - " + ", ".join(parts[1:]) if len(parts) > 1 and cols[0]["role"] == "dimension" else ", ".join(parts)))
        return ("Here is what the data shows" + (f" (filters: {filters_text(plan['filters'])})" if plan["filters"] else "") +
                ":\n" + "\n".join(lines) + "\n\n_The local language model is offline, so this is a direct data readout._")
    if docs:
        return docs[0]["text"] + "\n\n_The local language model is offline, so this is the most relevant knowledge-base entry._"
    return "I couldn't find anything relevant in the data you have access to."


def _kv_table(pairs: list[tuple[str, str]]) -> dict:
    return {"columns": [{"key": "field", "label": "Field", "role": "dimension", "kind": "category"},
                        {"key": "value", "label": "Value", "role": "dimension", "kind": "category"}],
            "rows": [[k, v] for k, v in pairs]}


def _lookup_events(user: User, ident: str, t0: float) -> Iterator[tuple[str, dict | str]]:
    """Exact record lookup (ORD-xxxxxx / CUST-xxxxx). Row scope and hidden columns apply exactly as everywhere else."""
    plan = {"intent": "lookup", "metrics": [], "group_by": [], "filters": {}, "basis": "net", "lookup": ident}
    src = [{"type": "query", "title": "Record lookup", "detail": f"{ident} (role-scoped: row scope and hidden columns applied)"}]
    table, text = None, ""
    if ident.startswith("ORD-"):
        rec = analytics_extra.get_order(user, ident)
        if rec:
            d = {c["key"]: v for c, v in zip(rec["columns"], rec["row"])}
            table = _kv_table([(c["label"], fmt(c["fmt"], v) if c["fmt"] != "percent_frac" else f"{v * 100:.0f}%")
                               for c, v in zip(rec["columns"], rec["row"])])
            text = (f"**{ident}** was placed on {d['order_date']} in {d['country']} ({d['region']}): {d['quantity']} x **{d['product_name']}** "
                    f"({d['category']} / {d['sub_category']}).")
            if "revenue" in d:
                text += f" Revenue **${d['revenue']:,.2f}**" + (f", profit **${d['profit']:,.2f}**" if "profit" in d else "") + "."
            text += (f" Shipped by {d['shipping_method']} in {d['shipping_days']} days (shipping cost ${d['shipping_cost']:,.2f}); "
                     f"paid with {d['payment_method']}; status **{d['order_status']}**.")
    else:
        rec = analytics_extra.get_customer(user, ident)
        if rec:
            cols = [{"key": "order_id", "label": "Order", "role": "dimension", "kind": "category"},
                    {"key": "date", "label": "Date", "role": "dimension", "kind": "category"},
                    {"key": "product", "label": "Product", "role": "dimension", "kind": "category"},
                    {"key": "status", "label": "Status", "role": "dimension", "kind": "category"}]
            if rec["list"] and "revenue" in rec["list"][0]:
                cols.append({"key": "revenue", "label": "Revenue", "role": "dimension", "kind": "category"})
            table = {"columns": cols, "rows": [[o["order_id"], o["date"], o["product"], o["status"]] + ([f"${o['revenue']:,.2f}"] if "revenue" in o else [])
                                               for o in rec["list"]]}
            text = (f"**{ident}** is a **{rec['segment']}** {rec['gender'].lower()} customer with **{rec['orders']}** order(s) in your data "
                    f"between {rec['first']} and {rec['last']}, buying from {', '.join(rec['categories'])}.")
            if rec["net_revenue"] is not None:
                text += f" Their net revenue is **${rec['net_revenue']:,.2f}**."
    if not text:
        text = f"I couldn't find **{ident}** in the data you have access to."
    yield "meta", {"denied": False, "plan": plan, "plan_source": "lookup", "sources": src if table else [], "table": table, "chart": None, "sql": None}
    yield "token", text
    yield "done", {"status": "ok" if table else "not_found", "mode": "lookup", "plan": plan, "rows": len(table["rows"]) if table else 0,
                   "ms": round((time.perf_counter() - t0) * 1000), "timings": {}}


def chat_events(user: User, question: str, history: list[dict] | None = None) -> Iterator[tuple[str, dict | str]]:
    """Yields ('meta', dict) once, then ('token', str)*, then ('done', dict)."""
    t0 = time.perf_counter()
    question = question.strip()[:600]
    denied = guard(user, question)
    if denied:
        yield "meta", {"denied": True, "plan": None, "sources": [], "table": None, "chart": None, "sql": None}
        yield "token", denied
        yield "done", {"status": "denied", "ms": round((time.perf_counter() - t0) * 1000), "mode": "guard", "plan": None}
        return

    lookup = re.search(r"\b(ORD|CUST)-\d{3,8}\b", question, re.I)
    if lookup:  # record lookups bypass the planner: exact id -> exact (role-scoped) record
        yield from _lookup_events(user, lookup.group(0).upper(), t0)
        return

    t = time.perf_counter()
    plan, plan_src = build_plan(user, question, history)
    plan_ms = (time.perf_counter() - t) * 1000

    if plan["intent"] in ("greeting", "off_topic") and not plan["metrics"]:
        msg = ("Hello! I'm Panorama Analyst. Ask me about revenue, profit, orders, shipping, returns, customers or trends in the "
               "data you have access to." if plan["intent"] == "greeting" else
               "I can only answer questions about the e-commerce sales data in this workspace - revenue, orders, products, shipping, "
               "returns and customers. Try one of the suggested questions.")
        yield "meta", {"denied": False, "plan": plan, "sources": [], "table": None, "chart": None, "sql": None}
        yield "token", msg
        yield "done", {"status": "ok", "ms": round((time.perf_counter() - t0) * 1000), "mode": "canned", "plan": plan}
        return

    res = None
    query_ms = 0.0
    if plan["metrics"] and plan["intent"] in ("data", "explain"):
        t = time.perf_counter()
        try:
            res = engine.run_query(user, plan["metrics"], plan["group_by"], plan["filters"], plan["basis"],
                                   order_by=plan["metrics"][0] if plan["group_by"] and plan["group_by"][0] not in
                                   ("year", "month", "quarter", "month_of_year", "quarter_of_year", "discount") else None,
                                   desc=plan["sort"] != "asc", limit=plan["limit"])
        except (engine.QueryError, engine.AccessError) as e:
            res = None
            plan["error"] = str(e)
        query_ms = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    docs = retriever().search(user, question + " " + " ".join(plan["group_by"] + plan["metrics"]), k=3 if res else 4)
    retr_ms = (time.perf_counter() - t) * 1000

    sources = []
    if res:
        sources.append({"type": "query", "title": "Live governed query", "detail": f"{', '.join(plan['metrics'])} by {', '.join(plan['group_by']) or 'total'} "
                                                                                  f"(filters: {filters_text(plan['filters'])}; basis: {plan['basis']})"})
    sources += [{"type": "doc", "id": d["id"], "title": d["title"], "score": d["score"], "text": d["text"][:600]} for d in docs]
    table = None
    if res:
        table = {"columns": res["columns"], "rows": res["rows"][:50]}
    yield "meta", {"denied": False, "plan": plan, "plan_source": plan_src, "sources": sources, "table": table,
                   "chart": build_chart(res) if res else None, "sql": res["sql"] if res else None}

    mode = "llm"
    llm_t = time.perf_counter()
    if llm.chat_ready():
        ctx = ""
        if res:
            ctx += (f"DATA RESULT (basis: {plan['basis']}; filters: {filters_text(plan['filters'])}; ordered "
                    f"{'ascending' if plan['sort'] == 'asc' else 'descending'} by {plan['metrics'][0]}):\n{result_markdown(res)}\n")
            if len(res["rows"]) > 1 and plan["group_by"] and plan["group_by"][0] not in ("year", "month", "quarter", "month_of_year", "quarter_of_year", "discount"):
                ctx += "NOTE: the FIRST row is the extreme the user asked about (the highest, or the lowest if they asked for lowest/fastest). Name that row as the answer.\n"
            if len(res["rows"]) == 1:
                ctx += ("NOTE: the result is a single value. Do NOT say it is the highest, lowest, best, worst or compare it with other "
                        "groups - nothing to compare against is provided.\n")
        if docs:
            ctx += "CONTEXT:\n" + "\n\n".join(d["text"][:900] for d in docs)
        messages = [{"role": "system", "content": ANSWER_SYSTEM + "\n" + scope_note(user)}]
        for h in (history or [])[-4:]:
            messages.append({"role": h["role"], "content": h["content"][:500]})
        messages.append({"role": "user", "content": f"{ctx}\n\nQUESTION: {question}"})
        try:
            for tok in llm.chat_stream(messages):
                yield "token", tok
        except Exception:
            mode = "fallback"
            yield "token", "\n\n" + fallback_answer(plan, res, docs)
    else:
        mode = "fallback"
        yield "token", fallback_answer(plan, res, docs)
    yield "done", {"status": "ok", "mode": mode, "plan": plan, "rows": len(res["rows"]) if res else 0,
                   "ms": round((time.perf_counter() - t0) * 1000),
                   "timings": {"plan_ms": round(plan_ms), "query_ms": round(query_ms, 1), "retrieve_ms": round(retr_ms),
                               "generate_ms": round((time.perf_counter() - llm_t) * 1000)}}


def answer_sync(user: User, question: str, history: list[dict] | None = None) -> dict:
    """Blocking helper used by the evaluation harness and tests."""
    out = {"text": "", "meta": None, "done": None}
    for kind, payload in chat_events(user, question, history):
        if kind == "meta":
            out["meta"] = payload
        elif kind == "token":
            out["text"] += payload
        else:
            out["done"] = payload
    return out


SUGGESTIONS = {
    "default": ["Which category generates the most revenue?", "How has revenue changed month by month?",
                "Which discount levels cause loss-making orders?", "What is the return rate by category?",
                "Who are our best customers by segment?", "Look up order ORD-000002"],
    "operations": ["What is the return rate by shipping method?", "Which region has the slowest delivery?",
                   "How many orders were cancelled in 2023?", "Compare average delivery days by shipping method",
                   "Which category has the most returns?"],
}


def suggestions(user: User) -> list[str]:
    scope = f" in {user.scope_value}" if user.scope_value else ""
    if user.role == "operations":
        return SUGGESTIONS["operations"]
    if user.role == "regional_manager":
        return [f"What is the total revenue{scope} by year?", f"Which country{scope} is most profitable?",
                f"Which categories sell best{scope}?", "What is the return rate by shipping method?",
                "Which discount levels cause loss-making orders?"]
    if user.role == "category_manager":
        return [f"How has {user.scope_value} revenue changed month by month?", f"Which {user.scope_value} products are most profitable?",
                f"Which region buys the most {user.scope_value}?", f"What is the return rate for {user.scope_value} by region?",
                "Which discount levels cause loss-making orders?"]
    return SUGGESTIONS["default"]
