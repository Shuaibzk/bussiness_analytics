"""Authentication, sessions + role based access policy.

The policy is the single source of truth for what a role may see:
  * row_scope   - which column restricts rows (value comes from the user's `scope_value`)
  * hidden      - columns the role can never read, filter by, group by, or ask the chatbot about
  * features    - which UI/API areas are available
Every data access in the app goes through `engine.py`, which consumes this policy,
so neither the REST API nor the AI chat can return out-of-scope data.

Sessions: a signed JWT carrying a `jti` that is also stored server-side (table `sessions`).  The browser receives it as an
httpOnly + SameSite=Strict cookie (not readable by JavaScript, so XSS cannot steal it); API clients may send it as a
Bearer token.  Sessions are revocable (logout, password change, user disabled), expire after an idle timeout and after an
absolute lifetime.  Cookie-authenticated state-changing requests must carry a custom header (CSRF defence in depth).
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
import time
from dataclasses import dataclass, field

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_ALG, JWT_SECRET, JWT_TTL_HOURS, SESSION_COOKIE, SESSION_IDLE_MINUTES
from .db import get_db

MONEY_COLS = {"unit_price", "discount", "revenue", "cost", "profit", "profit_margin", "loss_flag"}

ROLE_POLICY = {
    "admin": {
        "label": "Administrator",
        "description": "Full access to all data, the audit log and user directory.",
        "row_scope": None,
        "hidden": set(),
        "features": {"dashboard", "orders", "chat", "export", "audit", "users"},
        "landing": "/",
    },
    "executive": {
        "label": "Executive",
        "description": "All regions and categories, aggregated view. Customer identifiers are hidden.",
        "row_scope": None,
        "hidden": {"customer_id"},
        "features": {"dashboard", "orders", "chat", "export"},
        "landing": "/",
    },
    "regional_manager": {
        "label": "Regional Manager",
        "description": "Only the manager's own region. Full financial and customer detail inside it.",
        "row_scope": "region",
        "hidden": set(),
        "features": {"dashboard", "orders", "chat", "export"},
        "landing": "/",
    },
    "category_manager": {
        "label": "Category Manager",
        "description": "Only the manager's own product category, across all regions. No customer identifiers.",
        "row_scope": "category",
        "hidden": {"customer_id"},
        "features": {"dashboard", "orders", "chat", "export"},
        "landing": "/products",
    },
    "operations": {
        "label": "Operations & Logistics",
        "description": "All orders for fulfilment, shipping and returns. Pricing, cost, profit and customer IDs are hidden.",
        "row_scope": None,
        "hidden": MONEY_COLS | {"customer_id"},
        "features": {"dashboard", "orders", "chat"},
        "landing": "/fulfilment",
    },
}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"


@dataclass
class User:
    id: int
    username: str
    name: str
    role: str
    scope_value: str | None = None
    policy: dict = field(default_factory=dict)
    jti: str | None = None

    @property
    def row_scope_col(self) -> str | None:
        return self.policy.get("row_scope")

    @property
    def hidden(self) -> set[str]:
        return self.policy.get("hidden", set())

    def can(self, feature: str) -> bool:
        return feature in self.policy.get("features", set())

    def public(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "role_label": self.policy["label"],
            "role_description": self.policy["description"],
            "scope": (
                {"column": self.row_scope_col, "value": self.scope_value} if self.row_scope_col else None
            ),
            "features": sorted(self.policy["features"]),
            "hidden_columns": sorted(self.hidden),
            "landing": self.policy.get("landing", "/"),
        }


# ---------------------------------------------------------------- passwords
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except ValueError:
        return False


def validate_new_password(pw: str, username: str = "") -> None:
    """Policy for passwords set through the app (seeded demo accounts predate it)."""
    if len(pw) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if len(pw) > 128:
        raise HTTPException(400, "Password is too long")
    if username and pw.lower() == username.lower():
        raise HTTPException(400, "Password must not equal the username")
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        raise HTTPException(400, "Password must contain letters and at least one digit")


# ----------------------------------------------------------------- sessions
def create_session(user: User) -> str:
    """Creates a server-side session and returns the signed JWT that identifies it."""
    now = dt.datetime.now(dt.timezone.utc)
    jti = secrets.token_hex(16)
    with get_db() as db:
        db.execute("INSERT INTO sessions (jti, user_id, created_at, last_seen) VALUES (?,?,?,?)",
                   (jti, user.id, time.time(), time.time()))
        # housekeeping: forget sessions that can no longer be valid
        db.execute("DELETE FROM sessions WHERE created_at < ?", (time.time() - JWT_TTL_HOURS * 3600 - 86400,))
    payload = {"sub": str(user.id), "role": user.role, "jti": jti, "iat": now, "exp": now + dt.timedelta(hours=JWT_TTL_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def revoke_session(jti: str | None) -> None:
    if jti:
        with get_db() as db:
            db.execute("UPDATE sessions SET revoked = 1 WHERE jti = ?", (jti,))


def revoke_user_sessions(user_id: int, except_jti: str | None = None) -> None:
    with get_db() as db:
        db.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ? AND jti != ?", (user_id, except_jti or ""))


def _row_to_user(row, jti: str | None = None) -> User:
    return User(
        id=row["id"],
        username=row["username"],
        name=row["name"],
        role=row["role"],
        scope_value=row["scope_value"],
        policy=ROLE_POLICY[row["role"]],
        jti=jti,
    )


def authenticate(username: str, password: str) -> User | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username.strip().lower(),)
        ).fetchone()
    if row and verify_password(password, row["password_hash"]):
        return _row_to_user(row)
    return None


_bearer = HTTPBearer(auto_error=False)


def current_user(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    cookie_auth = creds is None
    token = creds.credentials if creds else request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "Not authenticated")
    if cookie_auth and request.method not in SAFE_METHODS and CSRF_HEADER not in request.headers:
        raise HTTPException(403, "Missing CSRF header")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    jti = payload.get("jti")
    now = time.time()
    with get_db() as db:
        sess = db.execute("SELECT * FROM sessions WHERE jti = ?", (jti,)).fetchone()
        if not sess or sess["revoked"]:
            raise HTTPException(401, "Session ended - please sign in again")
        if now - sess["last_seen"] > SESSION_IDLE_MINUTES * 60:
            db.execute("UPDATE sessions SET revoked = 1 WHERE jti = ?", (jti,))
            db.commit()  # persist before raising (get_db only commits on a clean exit)
            raise HTTPException(401, "Session timed out after inactivity")
        if now - sess["last_seen"] > 20:  # sliding window, written at most every 20 s
            db.execute("UPDATE sessions SET last_seen = ? WHERE jti = ?", (now, jti))
        row = db.execute("SELECT * FROM users WHERE id = ? AND active = 1", (int(payload["sub"]),)).fetchone()
    if not row:
        raise HTTPException(401, "User no longer exists")
    return _row_to_user(row, jti)  # role is re-read from the DB: a stale token can't keep old privileges


def require(feature: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not user.can(feature):
            raise HTTPException(403, f"Your role ({user.policy['label']}) cannot access '{feature}'")
        return user

    return dep
