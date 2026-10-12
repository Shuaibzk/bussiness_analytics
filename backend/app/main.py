"""FastAPI application: auth + sessions, governed analytics API, AI chat (SSE), admin tools."""
from __future__ import annotations

import csv
import io
import json
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import pymysql
from pydantic import BaseModel, Field

from . import analytics_extra, audit as audit_log_mod, chat, engine, llm
from .config import (CHAT_MODEL, CORS_ORIGINS, COOKIE_SECURE, DEMO_MODE, EMBED_MODEL, JWT_TTL_HOURS, LOGIN_LOCK_SECONDS,
                     MAX_LOGIN_FAILS, SESSION_COOKIE, SESSION_IDLE_MINUTES)
from .db import DatabaseUnavailable, get_db, ping
from .migrate import ensure_database
from .rag import index_docs, retriever
from .security import (ROLE_POLICY, User, authenticate, create_session, current_user, hash_password, require, revoke_session,
                       revoke_user_sessions, validate_new_password, verify_password)


def audit(user: User | None, action: str, detail: dict | str = "", status: str = "ok", ms: float = 0.0, username: str | None = None):
    audit_log_mod.write(user, action, detail, status, ms, username)


def _ensure_ready():
    ensure_database()  # migrations + dataset + demo users if missing (raises DatabaseUnavailable with a clear message)
    r = retriever()
    r.reload()
    need_dense = llm.embed_ready() and not r.stats["dense"]
    if r.stats["documents"] == 0 or need_dense:
        threading.Thread(target=index_docs, kwargs={"verbose": False}, daemon=True).start()
    threading.Thread(target=llm.warm_up, daemon=True).start()  # first user question must not pay the model load time


@asynccontextmanager
async def lifespan(_: FastAPI):
    _ensure_ready()
    yield


# also runs when the app object is used without the lifespan (tests, scripts); idempotent and cheap once up to date
ensure_database()

app = FastAPI(title="Panorama Analytics API", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def timing(request: Request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t) * 1000
    response.headers["X-Process-Time-Ms"] = f"{ms:.1f}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


@app.exception_handler(engine.AccessError)
async def _access(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=403)


@app.exception_handler(engine.QueryError)
async def _query(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


@app.exception_handler(pymysql.err.IntegrityError)
async def _integrity(_, exc):
    # a database constraint (FK / CHECK / UNIQUE) refused the write - report it, never a 500
    return JSONResponse({"detail": "That change violates a database rule (duplicate or inconsistent data)."}, status_code=409)


@app.exception_handler(DatabaseUnavailable)
async def _db_down(_, exc):
    return JSONResponse({"detail": str(exc)}, status_code=503)


# ------------------------------------------------------------------- auth
class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict", secure=COOKIE_SECURE,
                        max_age=JWT_TTL_HOURS * 3600, path="/")


@app.post("/api/auth/login")
def login(body: LoginBody, response: Response):
    key = body.username.strip().lower()
    now = time.time()
    with get_db() as db:  # failed attempts are persisted, so a server restart does not reset the lockout
        db.execute("DELETE FROM login_attempts WHERE ts < ?", (now - 86400,))
        fails = db.execute("SELECT COUNT(*) FROM login_attempts WHERE username = ? AND ts > ?", (key, now - LOGIN_LOCK_SECONDS)).fetchone()[0]
    if fails >= MAX_LOGIN_FAILS:
        audit(None, "login", "locked out", "denied", username=key)
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    user = authenticate(body.username, body.password)
    if not user:
        with get_db() as db:
            db.execute("INSERT INTO login_attempts (username, ts) VALUES (?,?)", (key, now))
        audit(None, "login", "bad credentials", "denied", username=key)
        raise HTTPException(401, "Invalid username or password")
    with get_db() as db:
        db.execute("DELETE FROM login_attempts WHERE username = ?", (key,))
    token = create_session(user)
    _set_cookie(response, token)
    audit(user, "login")
    # `token` is returned for non-browser API clients; the web app ignores it and relies on the httpOnly cookie
    return {"token": token, "user": user.public()}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    try:
        user = current_user(request, None)
        revoke_session(user.jti)
        audit(user, "logout")
    except HTTPException:
        pass
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


class PasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


@app.post("/api/auth/change-password")
def change_password(body: PasswordBody, user: User = Depends(current_user)):
    with get_db() as db:
        row = db.execute("SELECT password_hash FROM users WHERE id = ?", (user.id,)).fetchone()
    if not verify_password(body.current_password, row["password_hash"]):
        audit(user, "change_password", "wrong current password", "denied")
        raise HTTPException(400, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(400, "New password must differ from the current one")
    validate_new_password(body.new_password, user.username)
    with get_db() as db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.new_password), user.id))
    revoke_user_sessions(user.id, except_jti=user.jti)  # every other device is signed out
    audit(user, "change_password")
    return {"ok": True}


@app.get("/api/auth/demo-accounts")
def demo_accounts():
    """Local-demo convenience (shows seeded credentials on the login screen). Disable with DEMO_MODE=0."""
    if not DEMO_MODE:
        return []
    from .ingest import DEMO_USERS
    return [{"username": u, "name": n, "password": p, "role": r, "role_label": ROLE_POLICY[r]["label"], "scope": s}
            for u, n, p, r, s in DEMO_USERS]


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user.public()


# -------------------------------------------------------------------- meta
@app.get("/api/meta")
def meta(user: User = Depends(current_user)):
    st = llm.status()
    opts = engine.filter_options(user)
    return {
        "user": user.public(),
        "options": opts,
        "metrics": [{"key": m.key, "label": m.label, "fmt": m.fmt, "desc": m.desc} for m in engine.visible_metrics(user)],
        "dimensions": [{"key": d.key, "label": d.label} for d in engine.visible_dims(user)],
        "suggestions": chat.suggestions(user),
        "ai": {"online": llm.chat_ready(), "warm": llm.is_warm(), "model": CHAT_MODEL, "embedding_model": EMBED_MODEL,
               "dense_retrieval": retriever().stats["dense"], "ollama_up": st["up"]},
        "session": {"idle_minutes": SESSION_IDLE_MINUTES, "demo_mode": DEMO_MODE},
    }


# --------------------------------------------------------------- analytics
class Filters(BaseModel):
    filters: dict = Field(default_factory=dict)
    basis: str = "net"


class QueryBody(Filters):
    metrics: list[str]
    group_by: list[str] = Field(default_factory=list)
    order_by: str | None = None
    desc: bool = True
    limit: int | None = Field(default=None, ge=1, le=500)


@app.post("/api/query")
def query(body: QueryBody, user: User = Depends(require("dashboard"))):
    return engine.run_query(user, body.metrics, body.group_by, body.filters, body.basis, body.order_by, body.desc, body.limit)


@app.post("/api/kpis")
def kpis(body: Filters, user: User = Depends(require("dashboard"))):
    return engine.cached(user, "kpis", body.model_dump(), lambda: engine.kpis(user, body.filters, body.basis))


@app.post("/api/insights")
def insights(body: Filters, user: User = Depends(require("dashboard"))):
    def build():
        items = engine.insights(user, body.filters, body.basis)
        if "customer_id" not in user.hidden:
            items += analytics_extra.customer_insights(user, body.filters, body.basis)
        return items

    return engine.cached(user, "insights", body.model_dump(), build)


@app.post("/api/customers")
def customers(body: Filters, user: User = Depends(require("dashboard"))):
    return analytics_extra.customer_stats(user, body.filters, body.basis)


class ForecastBody(Filters):
    metric: str = "revenue"
    horizon: int = Field(default=6, ge=1, le=12)
    baseline: str = Field(default="auto", pattern="^(auto|stable|recent)$")


@app.post("/api/forecast")
def forecast(body: ForecastBody, user: User = Depends(require("dashboard"))):
    if body.metric not in engine.METRICS or not engine.metric_allowed(user, engine.METRICS[body.metric]):
        raise engine.AccessError("Your role cannot forecast that metric")
    return analytics_extra.forecast(user, body.metric, body.filters, body.basis, body.horizon, body.baseline)


class TargetBody(BaseModel):
    metric: str
    year: int
    value: float


@app.get("/api/targets")
def get_targets(user: User = Depends(require("dashboard"))):
    return analytics_extra.targets_status(user)


@app.put("/api/targets")
def put_target(body: TargetBody, user: User = Depends(require("dashboard"))):
    analytics_extra.set_target(user, body.metric, body.year, body.value)
    audit(user, "set_target", body.model_dump())
    return analytics_extra.targets_status(user)


@app.delete("/api/targets/{metric}/{year}")
def del_target(metric: str, year: int, user: User = Depends(require("dashboard"))):
    analytics_extra.delete_target(user, metric, year)
    audit(user, "delete_target", {"metric": metric, "year": year})
    return analytics_extra.targets_status(user)


class OrdersBody(BaseModel):
    filters: dict = Field(default_factory=dict)
    search: str | None = None
    sort: str | None = None
    desc: bool = True
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=200)


@app.post("/api/orders")
def orders(body: OrdersBody, user: User = Depends(require("orders"))):
    return engine.list_orders(user, body.filters, body.search, body.sort, body.desc, body.page, body.page_size)


@app.post("/api/orders/export")
def export(body: OrdersBody, user: User = Depends(require("export"))):
    t = time.perf_counter()
    res = engine.list_orders(user, body.filters, body.search, body.sort, body.desc, 1, 200, export=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c["label"] for c in res["columns"]])
    w.writerows(res["rows"])
    audit(user, "export", {"rows": len(res["rows"]), "filters": body.filters}, ms=(time.perf_counter() - t) * 1000)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=panorama_orders.csv"})


class ExportEvent(BaseModel):
    what: str = Field(max_length=80)
    rows: int = 0


@app.post("/api/export-event")
def export_event(body: ExportEvent, user: User = Depends(require("dashboard"))):
    """Chart/report downloads happen in the browser from data the user already loaded; this only records that they happened."""
    audit(user, "download", {"what": body.what, "rows": body.rows})
    return {"ok": True}


# -------------------------------------------------------------------- chat
class ChatBody(BaseModel):
    question: str = Field(min_length=1, max_length=600)
    history: list[dict] = Field(default_factory=list)


def _save_chat(user: User, question: str, answer: str, meta: dict | None, done: dict) -> int:
    payload = {**(meta or {}), "done": {k: done.get(k) for k in ("mode", "ms", "timings", "status")}}
    now = time.time()
    with get_db() as db:
        db.execute("INSERT INTO chat_messages (user_id, role, content, ts) VALUES (?,?,?,?)", (user.id, "user", question, now))
        cur = db.execute("INSERT INTO chat_messages (user_id, role, content, meta, ts) VALUES (?,?,?,?,?)",
                         (user.id, "assistant", answer, json.dumps(payload, default=str), now))
        # keep each user's stored history bounded (newest 200 messages)
        cut = db.execute("SELECT id FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 1 OFFSET 200", (user.id,)).fetchone()
        if cut:
            db.execute("DELETE FROM chat_messages WHERE user_id = ? AND id <= ?", (user.id, cut["id"]))
        return cur.lastrowid


@app.post("/api/chat/stream")
def chat_stream(body: ChatBody, user: User = Depends(require("chat"))):
    history = [{"role": h.get("role"), "content": str(h.get("content", "")), "plan": h.get("plan")} for h in body.history[-6:]
               if h.get("role") in ("user", "assistant")]

    def gen():
        last, meta_evt, answer = {}, None, []
        for kind, payload in chat.chat_events(user, body.question, history):
            if kind == "done":
                last = payload
            elif kind == "meta":
                meta_evt = payload
            elif kind == "token":
                answer.append(payload)
            yield f"event: {kind}\ndata: {json.dumps(payload, default=str)}\n\n"
        audit(user, "chat", {"q": body.question, "plan": last.get("plan"), "mode": last.get("mode")},
              status=last.get("status", "ok"), ms=last.get("ms", 0))
        try:
            mid = _save_chat(user, body.question, "".join(answer), meta_evt, last)
            yield f"event: saved\ndata: {json.dumps({'id': mid})}\n\n"
        except Exception:  # persistence must never break the answer
            pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/chat/history")
def chat_history(user: User = Depends(require("chat"))):
    with get_db() as db:
        rows = db.execute("SELECT id, role, content, meta, rating FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT 60", (user.id,)).fetchall()
    return [{"id": r["id"], "role": r["role"], "content": r["content"], "rating": r["rating"],
             "meta": json.loads(r["meta"]) if r["meta"] else None} for r in rows][::-1]


@app.delete("/api/chat/history")
def clear_history(user: User = Depends(require("chat"))):
    with get_db() as db:
        n = db.execute("DELETE FROM chat_messages WHERE user_id = ?", (user.id,)).rowcount
    audit(user, "chat_clear", {"messages": n})
    return {"deleted": n}


class FeedbackBody(BaseModel):
    message_id: int
    rating: int = Field(ge=-1, le=1)  # 1 helpful, -1 not helpful, 0 clears
    comment: str | None = Field(default=None, max_length=300)


@app.post("/api/chat/feedback")
def chat_feedback(body: FeedbackBody, user: User = Depends(require("chat"))):
    with get_db() as db:
        n = db.execute("UPDATE chat_messages SET rating = ?, comment = ? WHERE id = ? AND user_id = ? AND role = 'assistant'",
                       (body.rating or None, body.comment, body.message_id, user.id)).rowcount
    if not n:
        raise HTTPException(404, "Message not found")
    audit(user, "chat_feedback", {"message_id": body.message_id, "rating": body.rating})
    return {"ok": True}


# ------------------------------------------------------------------- admin
@app.get("/api/admin/audit")
def audit_list(limit: int = 200, user: User = Depends(require("audit"))):
    with get_db() as db:
        rows = db.execute("SELECT id, ts, username, role, scope, action, detail, status, ms FROM audit_log ORDER BY id DESC LIMIT ?",
                          (min(limit, 1000),)).fetchall()
        summary = db.execute("SELECT status, COUNT(*) n FROM audit_log GROUP BY status").fetchall()
    return {"rows": [{**dict(r), "ts": str(r["ts"])} for r in rows], "summary": {r["status"]: r["n"] for r in summary}}


@app.get("/api/admin/audit/verify")
def audit_verify(user: User = Depends(require("audit"))):
    return audit_log_mod.verify()


def _user_row(r) -> dict:
    return {**dict(r), "role_label": ROLE_POLICY[r["role"]]["label"], "hidden_columns": sorted(ROLE_POLICY[r["role"]]["hidden"]),
            "features": sorted(ROLE_POLICY[r["role"]]["features"])}


@app.get("/api/admin/users")
def users(user: User = Depends(require("users"))):
    with get_db() as db:
        rows = db.execute("SELECT id, username, name, role, scope_value, active FROM users ORDER BY id").fetchall()
    return [_user_row(r) for r in rows]


def _check_role_scope(role: str, scope: str | None) -> str | None:
    policy = ROLE_POLICY.get(role)
    if not policy:
        raise HTTPException(400, f"Unknown role '{role}'")
    col = policy["row_scope"]
    cat = chat.catalogue()
    if col:
        valid = set(cat["region"]) if col == "region" else set(cat["category"])
        if scope not in valid:
            raise HTTPException(400, f"{policy['label']} needs a {col}: one of {', '.join(sorted(valid))}")
        return scope
    if scope:
        raise HTTPException(400, f"{policy['label']} has no row scope; leave scope empty")
    return None


class NewUser(BaseModel):
    username: str = Field(max_length=32)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(max_length=128)
    role: str
    scope_value: str | None = None


@app.post("/api/admin/users")
def create_user(body: NewUser, user: User = Depends(require("users"))):
    username = body.username.strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{3,32}", username):
        raise HTTPException(400, "Username: 3-32 characters, letters, digits, dot, dash or underscore")
    scope = _check_role_scope(body.role, body.scope_value)
    validate_new_password(body.password, username)
    with get_db() as db:
        if db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            raise HTTPException(409, "That username already exists")
        cur = db.execute("INSERT INTO users (username, name, password_hash, role, scope_value) VALUES (?,?,?,?,?)",
                         (username, body.name.strip(), hash_password(body.password), body.role, scope))
        row = db.execute("SELECT id, username, name, role, scope_value, active FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    audit(user, "user_create", {"username": username, "role": body.role, "scope": scope})
    return _user_row(row)


class PatchUser(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    role: str | None = None
    scope_value: str | None = None
    active: bool | None = None


def _admin_count(db, excluding: int) -> int:
    return db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1 AND id != ?", (excluding,)).fetchone()[0]


@app.patch("/api/admin/users/{uid}")
def patch_user(uid: int, body: PatchUser, user: User = Depends(require("users"))):
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        role = body.role or row["role"]
        scope = row["scope_value"]
        if body.role is not None or body.scope_value is not None:
            keep = row["scope_value"] if role == row["role"] else None  # a new role does not inherit the old scope
            scope = _check_role_scope(role, body.scope_value if body.scope_value is not None else keep)
        active = row["active"] if body.active is None else int(body.active)
        if uid == user.id and (not active or role != row["role"]):
            raise HTTPException(400, "You cannot disable or change the role of your own account")
        if row["role"] == "admin" and (role != "admin" or not active) and _admin_count(db, uid) == 0:
            raise HTTPException(400, "At least one active administrator must remain")
        db.execute("UPDATE users SET name = ?, role = ?, scope_value = ?, active = ? WHERE id = ?",
                   ((body.name or row["name"]).strip(), role, scope, active, uid))
        new = db.execute("SELECT id, username, name, role, scope_value, active FROM users WHERE id = ?", (uid,)).fetchone()
    if (role, scope, active) != (row["role"], row["scope_value"], row["active"]):
        revoke_user_sessions(uid)  # new permissions apply immediately; old sessions end
    audit(user, "user_update", {"target": row["username"], **body.model_dump(exclude_none=True)})
    return _user_row(new)


class ResetBody(BaseModel):
    password: str = Field(max_length=128)


@app.post("/api/admin/users/{uid}/reset-password")
def reset_password(uid: int, body: ResetBody, user: User = Depends(require("users"))):
    with get_db() as db:
        row = db.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    validate_new_password(body.password, row["username"])
    with get_db() as db:
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(body.password), uid))
    revoke_user_sessions(uid)
    audit(user, "user_reset_password", {"target": row["username"]})
    return {"ok": True}


@app.get("/api/admin/system")
def system(user: User = Depends(require("audit"))):
    dbinfo = ping()
    with get_db() as db:
        n = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        fb = {r["rating"]: r["n"] for r in db.execute("SELECT rating, COUNT(*) n FROM chat_messages WHERE rating IS NOT NULL GROUP BY rating")}
        sessions = db.execute("SELECT COUNT(*) FROM sessions WHERE revoked = 0 AND last_seen > ?", (time.time() - SESSION_IDLE_MINUTES * 60,)).fetchone()[0]
        answers = db.execute("SELECT COUNT(*) FROM chat_messages WHERE role = 'assistant'").fetchone()[0]
    h, m = engine.CACHE_STATS["hits"], engine.CACHE_STATS["misses"]
    return {"orders": n, "db_mb": dbinfo["size_mb"], "db_engine": dbinfo["engine"], "cache": {"hits": h, "misses": m,
            "hit_rate": round(h / (h + m) * 100, 1) if h + m else 0}, "rag": retriever().stats,
            "feedback": {"helpful": fb.get(1, 0), "not_helpful": fb.get(-1, 0), "answers": answers},
            "active_sessions": sessions,
            "llm": {**{k: v for k, v in llm.status().items() if k != "ts"}, "chat_model": CHAT_MODEL, "embed_model": EMBED_MODEL, "warm": llm.is_warm()}}


@app.get("/api/admin/database")
def database_overview(user: User = Depends(require("audit"))):
    """Schema overview for the Admin > Database page (tables, sizes, integrity rules, migrations, privileges of the app account)."""
    info = ping()
    with get_db() as db:
        tables = [dict(r) for r in db.execute("SELECT table_name, table_type, engine, approx_rows, size_mb FROM db_tables ORDER BY table_type, table_name").fetchall()]
        cons = db.execute("SELECT table_name, constraint_type, COUNT(*) n FROM db_constraints GROUP BY table_name, constraint_type").fetchall()
        migrations = [dict(r) | {"applied_at": str(r["applied_at"])} for r in db.execute("SELECT version, name, applied_at FROM schema_migrations ORDER BY version").fetchall()]
        grants = [re.sub(r" IDENTIFIED BY PASSWORD '[^']*'", "", r[0]) for r in db.execute("SHOW GRANTS FOR CURRENT_USER()").fetchall()]  # never expose the password hash
    by_table: dict[str, dict] = {}
    for r in cons:
        by_table.setdefault(r["table_name"], {})[r["constraint_type"]] = r["n"]
    for t in tables:
        t["constraints"] = by_table.get(t["table_name"], {})
        t["size_mb"] = float(t["size_mb"] or 0)
        t["approx_rows"] = int(t["approx_rows"] or 0)
    totals = {k: sum(v.get(k, 0) for v in by_table.values()) for k in ("FOREIGN KEY", "CHECK", "UNIQUE")}
    return {**info, "tables": tables, "constraint_totals": totals, "migrations": migrations, "app_account_grants": grants}


@app.get("/api/health")
def health():
    try:
        return {"ok": True, "db": ping()}
    except DatabaseUnavailable as e:
        return JSONResponse({"ok": False, "detail": str(e)}, status_code=503)


# ------------------------------------------------- production build of the React app (single-process demo)
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (DIST / path).resolve()
        if path and f.is_file() and DIST in f.parents:
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
