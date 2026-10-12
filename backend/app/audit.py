"""Append-only, hash-chained audit log (MariaDB).

Each row stores sha256(previous_hash + this row's fields).  Editing, deleting or re-ordering any past row breaks every hash
after it, which `verify()` detects.  On top of that the web app's database account is granted only INSERT + SELECT on
`audit_log` (migration 004): the application itself cannot UPDATE or DELETE audit history.  (A determined attacker with the
schema owner's password could still rewrite the whole chain - production would anchor the head hash in an external write-once
store.)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

from .db import connect

GENESIS = "0" * 64
_LOCK = "panorama_audit_chain"


def _digest(prev: str, ts, username, role, scope, action, detail, status, ms) -> str:
    raw = "\x1f".join(str(x) for x in (prev, ts, username, role, scope, action, detail, status, ms))
    return hashlib.sha256(raw.encode()).hexdigest()


def write(user, action: str, detail: dict | str = "", status: str = "ok", ms: float = 0.0, username: str | None = None) -> None:
    scope = (f"{user.row_scope_col}={user.scope_value}" if user.row_scope_col else "all") if user else None
    uname = user.username if user else username
    role = user.role if user else None
    text = detail if isinstance(detail, str) else json.dumps(detail, default=str)[:1500]
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ms = round(float(ms), 1)  # always a float: the column is DOUBLE, so int 65 vs 65.0 would otherwise change the hash
    conn = connect()
    try:
        # a named lock serialises writers across every worker/process, so the chain can never fork
        conn.execute("SELECT GET_LOCK(?, 10)", (_LOCK,)).fetchone()
        try:
            row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev = row["hash"] if row else GENESIS
            h = _digest(prev, ts, uname, role, scope, action, text, status, ms)
            conn.execute(
                "INSERT INTO audit_log (ts, username, role, scope, action, detail, status, ms, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, uname, role, scope, action, text, status, ms, prev, h),
            )
            conn.commit()
        finally:
            conn.execute("SELECT RELEASE_LOCK(?)", (_LOCK,)).fetchone()
    finally:
        conn.close()


def verify() -> dict:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, ts, username, role, scope, action, detail, status, ms, prev_hash, hash FROM audit_log ORDER BY id").fetchall()
    finally:
        conn.close()
    prev = GENESIS
    for r in rows:
        expected = _digest(prev, r["ts"], r["username"], r["role"], r["scope"], r["action"], r["detail"], r["status"], r["ms"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "entries": len(rows), "broken_at": r["id"]}
        prev = r["hash"]
    return {"ok": True, "entries": len(rows), "head": prev[:16]}
