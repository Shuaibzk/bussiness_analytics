"""Security regression suite - exercises the real HTTP API as each role.

Run:  python -m tests.test_security
Every check is an attack or a boundary: a PASS means the system held.
"""
from __future__ import annotations

import base64
import json
import sys
import time
import uuid

import jwt
from fastapi.testclient import TestClient

from app.db import connect
from app.main import app
from app.rag import retriever
from app.security import ROLE_POLICY, User

client = TestClient(app)  # sends bearer tokens only (a header takes precedence over any cookie from earlier logins)
anon = TestClient(app)    # never logs in: used for unauthenticated checks
results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, extra: str = ""):
    results.append((ok, name))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -> ' + extra) if (extra and not ok) else ''}")


def login(user: str, pw: str) -> dict:
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


ADMIN = login("admin", "admin123")
EXEC = login("executive", "exec123")
ASIA = login("asia.manager", "manager123")
ELEC = login("electronics.manager", "category123")
OPS = login("ops", "ops123")

# ---- authentication ----------------------------------------------------------------------------------
check("no token -> 401 on /api/meta", anon.get("/api/meta").status_code == 401)
check("no token -> 401 on /api/query", anon.post("/api/query", json={"metrics": ["orders"]}).status_code == 401)
check("garbage token -> 401", client.get("/api/meta", headers={"Authorization": "Bearer abc.def.ghi"}).status_code == 401)
tok = ASIA["Authorization"].split()[1]
h, p, s = tok.split(".")
forged = json.loads(base64.urlsafe_b64decode(p + "=="))
forged["role"] = "admin"
forged["sub"] = "1"
p2 = base64.urlsafe_b64encode(json.dumps(forged).encode()).rstrip(b"=").decode()
check("forged JWT payload (role=admin) rejected", client.get("/api/meta", headers={"Authorization": f"Bearer {h}.{p2}.{s}"}).status_code == 401)
check("wrong password -> 401", client.post("/api/auth/login", json={"username": "admin", "password": "nope"}).status_code == 401)
codes = [client.post("/api/auth/login", json={"username": "lockme", "password": "x"}).status_code for _ in range(7)]
check("brute force lockout (429 after repeated failures)", 429 in codes, str(codes))

# ---- row-level security (regional manager) --------------------------------------------------------------
asia_total = client.post("/api/query", headers=ASIA, json={"metrics": ["orders"], "basis": "gross"}).json()["rows"][0][0]
all_total = client.post("/api/query", headers=ADMIN, json={"metrics": ["orders"], "basis": "gross"}).json()["rows"][0][0]
check("admin sees all 10,000 orders; Asia manager only Asia's", all_total == 10000 and asia_total == 2494, f"{all_total}/{asia_total}")
r = client.post("/api/query", headers=ASIA, json={"metrics": ["revenue"], "group_by": ["region"], "filters": {"region": ["Europe"]}}).json()
check("Asia manager filtering region=Europe gets nothing", r["rows"] == [])
r = client.post("/api/query", headers=ASIA, json={"metrics": ["revenue"], "group_by": ["region"]}).json()
check("Asia manager group-by region returns only Asia", [x[0] for x in r["rows"]] == ["Asia"])
r = client.post("/api/orders", headers=ASIA, json={"page_size": 200}).json()
rcol = [c["key"] for c in r["columns"]].index("region")
check("orders table rows are all Asia", r["total"] == 2494 and all(row[rcol] == "Asia" for row in r["rows"]))
opts = client.get("/api/meta", headers=ASIA).json()["options"]["dims"]
check("filter dropdown options only list Asia", opts["region"]["values"] == ["Asia"] and "Japan" in opts["country"]["values"] and "Germany" not in opts["country"]["values"])
csv_text = client.post("/api/orders/export", headers=ASIA, json={}).text
check("CSV export contains only Asia rows", "Europe" not in csv_text and "North America" not in csv_text and csv_text.count("\n") == 2495)
check("Asia manager cannot read audit log (403)", client.get("/api/admin/audit", headers=ASIA).status_code == 403)

# ---- row-level security (category manager) --------------------------------------------------------------
r = client.post("/api/query", headers=ELEC, json={"metrics": ["revenue"], "group_by": ["category"]}).json()
check("Electronics manager sees only Electronics", [x[0] for x in r["rows"]] == ["Electronics"])
check("Category manager cannot group by customer_id (403)", client.post("/api/query", headers=ELEC, json={"metrics": ["orders"], "group_by": ["customer_id"]}).status_code == 403)
cols = [c["key"] for c in client.post("/api/orders", headers=ELEC, json={}).json()["columns"]]
check("customer_id column hidden from category manager", "customer_id" not in cols)

# ---- column-level security (operations) -------------------------------------------------------------------
for metric in ("revenue", "profit", "cost", "margin", "aov", "avg_discount", "loss_rate", "customers"):
    check(f"operations blocked from metric '{metric}' (403)", client.post("/api/query", headers=OPS, json={"metrics": [metric]}).status_code == 403)
cols = [c["key"] for c in client.post("/api/orders", headers=OPS, json={}).json()["columns"]]
check("operations orders table hides money + customer columns", not ({"revenue", "cost", "profit", "unit_price", "discount", "customer_id"} & set(cols)), str(cols))
check("operations cannot filter by discount (403)", client.post("/api/query", headers=OPS, json={"metrics": ["orders"], "filters": {"discount": [0.5]}}).status_code == 403)
r = client.post("/api/orders", headers=OPS, json={"sort": "profit", "page_size": 5})
check("operations sorting by hidden column 'profit' does not leak (falls back)", r.status_code == 200 and "profit" not in [c["key"] for c in r.json()["columns"]])
check("operations has no CSV export (403)", client.post("/api/orders/export", headers=OPS, json={}).status_code == 403)
kp = [c["key"] for c in client.post("/api/kpis", headers=OPS, json={}).json()["cards"]]
check("operations KPI cards contain no financial KPIs", not ({"revenue", "profit", "margin", "aov"} & set(kp)), str(kp))
ins = json.dumps(client.post("/api/insights", headers=OPS, json={}).json())
check("operations insights contain no revenue / profit / margin text", all(w not in ins.lower() for w in ("profit", "margin", "revenue")), ins[:120])

# ---- executive: aggregated only ------------------------------------------------------------------------------
check("executive cannot group by customer_id (403)", client.post("/api/query", headers=EXEC, json={"metrics": ["orders"], "group_by": ["customer_id"]}).status_code == 403)
check("executive orders table hides customer_id", "customer_id" not in [c["key"] for c in client.post("/api/orders", headers=EXEC, json={}).json()["columns"]])
check("executive search by customer id finds nothing", client.post("/api/orders", headers=EXEC, json={"search": "CUST-0"}).json()["total"] == 0)

# ---- injection / abuse ---------------------------------------------------------------------------------------------
r = client.post("/api/query", headers=ASIA, json={"metrics": ["revenue"], "filters": {"region": ["Asia' OR '1'='1"]}})
check("SQL injection in filter value returns nothing / no leak", r.status_code == 200 and r.json()["rows"][0][0] in (0, None))
r = client.post("/api/query", headers=ADMIN, json={"metrics": ["revenue; DROP TABLE orders"]})
check("SQL injection in metric name rejected (400)", r.status_code == 400)
r = client.post("/api/query", headers=ADMIN, json={"metrics": ["revenue"], "group_by": ["region); DROP TABLE orders;--"]})
check("SQL injection in group_by rejected (400)", r.status_code == 400)
r = client.post("/api/orders", headers=ADMIN, json={"search": "'; DROP TABLE orders; --"})
check("SQL injection in search is harmless", r.status_code == 200 and r.json()["total"] == 0)
check("orders table still intact after attacks", client.post("/api/query", headers=ADMIN, json={"metrics": ["orders"], "basis": "gross"}).json()["rows"][0][0] == 10000)
r = client.post("/api/orders", headers=ADMIN, json={"sort": "order_id; DROP TABLE orders", "page_size": 5})
check("SQL injection in sort column ignored", r.status_code == 200)

# ---- cache isolation -----------------------------------------------------------------------------------------------------
body = {"metrics": ["revenue"], "basis": "net"}
a = client.post("/api/query", headers=ADMIN, json=body).json()["rows"][0][0]
b = client.post("/api/query", headers=ASIA, json=body).json()["rows"][0][0]
check("query cache never serves one role's result to another", a != b and abs(b - 951599.44) < 1)

# ---- RAG knowledge-base isolation ---------------------------------------------------------------------------------------
def U(role, scope=None):
    return User(1, role, role, role, scope, ROLE_POLICY[role])


rt = retriever()
asia_docs = [d for d in rt.docs if rt.visible(U("regional_manager", "Asia"), d)]
check("Asia manager can retrieve only Asia + neutral documents", all(d["scope_region"] in ("Asia", "*") and d["scope_category"] in (None, "*") for d in asia_docs))
ops_docs = [d for d in rt.docs if rt.visible(U("operations"), d)]
check("operations can retrieve no document that needs financial columns", all(not (set(d["needs"]) & ROLE_POLICY["operations"]["hidden"]) for d in ops_docs))
hits = rt.search(U("operations"), "total profit and revenue by region and customer ids", 10)
check("operations retrieval for 'profit/revenue' returns no financial document", all(not (set(d["needs"]) & ROLE_POLICY["operations"]["hidden"]) for d in hits))
elec_docs = [d for d in rt.docs if rt.visible(U("category_manager", "Electronics"), d)]
check("Electronics manager retrieves only Electronics + neutral documents", all(d["scope_category"] in ("Electronics", "*") and d["scope_region"] in (None, "*") for d in elec_docs))

# ---- audit trail -------------------------------------------------------------------------------------------------------
r = client.post("/api/chat/stream", headers=ASIA, json={"question": "What is revenue in Europe?"})
audit = client.get("/api/admin/audit?limit=20", headers=ADMIN).json()["rows"]
check("denied chat attempt is recorded in the audit log", any(a["action"] == "chat" and a["status"] == "denied" and a["username"] == "asia.manager" for a in audit))
check("failed logins are recorded in the audit log", any(a["action"] == "login" and a["status"] == "denied" for a in client.get("/api/admin/audit?limit=60", headers=ADMIN).json()["rows"]))

# ======================================================= v2: sessions, cookies, CSRF ==========================================
CSRF = {"X-Requested-With": "panorama"}
br = TestClient(app)
r = br.post("/api/auth/login", json={"username": "executive", "password": "exec123"})
sc = r.headers.get("set-cookie", "").lower()
check("session cookie is httpOnly and SameSite=Strict", "httponly" in sc and "samesite=strict" in sc, sc)
check("cookie authenticates GET requests", br.get("/api/auth/me").status_code == 200)
check("cookie-authenticated POST without CSRF header is rejected (403)", br.post("/api/kpis", json={}).status_code == 403)
check("cookie-authenticated POST with CSRF header works", br.post("/api/kpis", json={}, headers=CSRF).status_code == 200)
old_token = r.json()["token"]
br.post("/api/auth/logout", headers=CSRF)
check("logout revokes the session: replaying the old JWT fails (401)", anon.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401)

t2 = anon.post("/api/auth/login", json={"username": "ops", "password": "ops123"}).json()["token"]
jti = jwt.decode(t2, options={"verify_signature": False})["jti"]
c = connect(); c.execute("UPDATE sessions SET last_seen = ? WHERE jti = ?", (time.time() - 99999, jti)); c.commit(); c.close()
check("idle session expires (401)", anon.get("/api/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 401)

# ---- user management (admin only) ---------------------------------------------------------------------------------------
uname = "t_" + uuid.uuid4().hex[:6]
good = {"username": uname, "name": "Test Europe", "password": "Passw0rd123", "role": "regional_manager", "scope_value": "Europe"}
check("non-admin cannot create users (403)", client.post("/api/admin/users", headers=ASIA, json=good).status_code == 403)
check("non-admin cannot list users (403)", client.get("/api/admin/users", headers=EXEC).status_code == 403)
check("unknown role rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "role": "superuser"}).status_code == 400)
check("scoped role without scope rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "scope_value": None}).status_code == 400)
check("scope that does not exist rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "scope_value": "Atlantis"}).status_code == 400)
check("unscoped role with a scope rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "role": "executive"}).status_code == 400)
check("weak password rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "password": "abc"}).status_code == 400)
check("invalid username rejected (400)", client.post("/api/admin/users", headers=ADMIN, json={**good, "username": "Bad Name!"}).status_code == 400)
r = client.post("/api/admin/users", headers=ADMIN, json=good)
check("admin can create a regional manager", r.status_code == 200 and r.json()["scope_value"] == "Europe", r.text)
uid = r.json().get("id")
check("duplicate username rejected (409)", client.post("/api/admin/users", headers=ADMIN, json=good).status_code == 409)
NEW = {"Authorization": "Bearer " + anon.post("/api/auth/login", json={"username": uname, "password": "Passw0rd123"}).json()["token"]}
rr = client.post("/api/query", headers=NEW, json={"metrics": ["revenue"], "group_by": ["region"]}).json()
check("newly created Europe manager is row-scoped to Europe", [x[0] for x in rr["rows"]] == ["Europe"])

# change password
check("change password: wrong current password rejected (400)", client.post("/api/auth/change-password", headers=NEW, json={"current_password": "nope", "new_password": "Another1234"}).status_code == 400)
check("change password: weak new password rejected (400)", client.post("/api/auth/change-password", headers=NEW, json={"current_password": "Passw0rd123", "new_password": "short"}).status_code == 400)
other = {"Authorization": "Bearer " + anon.post("/api/auth/login", json={"username": uname, "password": "Passw0rd123"}).json()["token"]}
check("change password succeeds", client.post("/api/auth/change-password", headers=NEW, json={"current_password": "Passw0rd123", "new_password": "Another1234"}).status_code == 200)
check("change password signs out the user's other sessions", client.get("/api/auth/me", headers=other).status_code == 401 and client.get("/api/auth/me", headers=NEW).status_code == 200)
check("old password no longer works", anon.post("/api/auth/login", json={"username": uname, "password": "Passw0rd123"}).status_code == 401)

# admin reset + disable
check("admin password reset works", client.post(f"/api/admin/users/{uid}/reset-password", headers=ADMIN, json={"password": "Reset12345"}).status_code == 200)
check("password reset revokes existing sessions", client.get("/api/auth/me", headers=NEW).status_code == 401)
NEW = {"Authorization": "Bearer " + anon.post("/api/auth/login", json={"username": uname, "password": "Reset12345"}).json()["token"]}
check("changing a user's region takes effect immediately", client.patch(f"/api/admin/users/{uid}", headers=ADMIN, json={"scope_value": "Asia"}).status_code == 200 and client.get("/api/auth/me", headers=NEW).status_code == 401)
check("admin can disable a user; their login then fails", client.patch(f"/api/admin/users/{uid}", headers=ADMIN, json={"active": False}).status_code == 200
      and anon.post("/api/auth/login", json={"username": uname, "password": "Reset12345"}).status_code == 401)
my_id = client.get("/api/auth/me", headers=ADMIN).json()["id"]
check("admin cannot disable their own account (400)", client.patch(f"/api/admin/users/{my_id}", headers=ADMIN, json={"active": False}).status_code == 400)
check("admin cannot change their own role (400)", client.patch(f"/api/admin/users/{my_id}", headers=ADMIN, json={"role": "executive"}).status_code == 400)
c = connect(admin=True); c.execute("DELETE FROM users WHERE username LIKE 't!_%' ESCAPE '!'"); c.commit(); c.close()  # cleanup needs the schema owner

# ---- tamper-evident audit log ------------------------------------------------------------------------------------------------
v = client.get("/api/admin/audit/verify", headers=ADMIN).json()
check("audit hash chain verifies", v["ok"] is True, str(v))
c = connect(admin=True)  # tampering requires the schema owner: the app account cannot UPDATE audit_log
row = c.execute("SELECT id, detail FROM audit_log ORDER BY id LIMIT 1 OFFSET 2").fetchone()
c.execute("UPDATE audit_log SET detail = 'tampered' WHERE id = ?", (row["id"],)); c.commit()
v2 = client.get("/api/admin/audit/verify", headers=ADMIN).json()
c.execute("UPDATE audit_log SET detail = ? WHERE id = ?", (row["detail"], row["id"])); c.commit(); c.close()
check("editing an old audit row is detected", v2["ok"] is False and v2.get("broken_at") == row["id"], str(v2))
check("audit chain verifies again once restored", client.get("/api/admin/audit/verify", headers=ADMIN).json()["ok"] is True)
check("audit verification is admin-only (403)", client.get("/api/admin/audit/verify", headers=ASIA).status_code == 403)

# ---- new analytics endpoints respect roles -----------------------------------------------------------------------------------
check("operations cannot forecast revenue (403)", client.post("/api/forecast", headers=OPS, json={"metric": "revenue"}).status_code == 403)
check("operations can forecast orders", client.post("/api/forecast", headers=OPS, json={"metric": "orders"}).status_code == 200)
check("operations cannot set a revenue target (403)", client.put("/api/targets", headers=OPS, json={"metric": "revenue", "year": 2023, "value": 1000}).status_code == 403)
check("targets reject nonsense values (400)", client.put("/api/targets", headers=ASIA, json={"metric": "revenue", "year": 2023, "value": -5}).status_code == 400)
client.put("/api/targets", headers=ASIA, json={"metric": "revenue", "year": 2023, "value": 123456})
mine = client.get("/api/targets", headers=ASIA).json()
check("a regional manager's target is measured against their own region only", any(t["target"] == 123456 and t["actual"] < 600000 for t in mine), str(mine))
check("targets are private to the user who set them", not any(t["target"] == 123456 for t in client.get("/api/targets", headers=ADMIN).json()))
client.delete("/api/targets/revenue/2023", headers=ASIA)
ec = client.post("/api/customers", headers=EXEC, json={}).json()
check("executive customer analytics has no customer-level data", ec["customer_access"] is False and "customers" not in ec)
oc = client.post("/api/customers", headers=OPS, json={}).json()
check("operations customer segments contain no financial metrics", not ({"revenue", "aov", "margin", "avg_discount"} & {c["key"] for c in oc["segments"]["columns"]}))
ac = client.post("/api/customers", headers=ASIA, json={}).json()
con = connect(); asia_cust = con.execute("SELECT COUNT(DISTINCT customer_id) FROM orders WHERE region = 'Asia'").fetchone()[0]; con.close()
check("regional manager customer analytics covers only their region's customers", ac["customers"]["unique"] == asia_cust, f"{ac['customers']['unique']} vs {asia_cust}")
check("operations can group by delivery band", client.post("/api/query", headers=OPS, json={"metrics": ["orders"], "group_by": ["delivery_band"]}).status_code == 200)


# ---- AI chat: record lookups, history, feedback ----------------------------------------------------------------------------------
def say(headers, q):
    return client.post("/api/chat/stream", headers=headers, json={"question": q}).text


t = say(ASIA, "show order ORD-000001")        # a Mexico / North America order
check("Asia manager cannot look up an order from another region", "couldn't find" in t and "Mexico" not in t, t[:200])
check("Asia manager can look up an Asia order (ORD-000004)", "ORD-000004" in say(ASIA, "show order ORD-000004") and "Japan" in say(ASIA, "show order ORD-000004"))
t = say(OPS, "show order ORD-000004")
check("operations order lookup hides revenue, profit and cost", "ORD-000004" in t and not any(w in t for w in ("Revenue", "Profit", "Cost", "revenue", "profit", "Unit price")), t[:300])
check("executive cannot look up customer ids", "customer identifiers" in say(EXEC, "what did CUST-02791 buy"))
check("category manager cannot look up customer ids", "customer identifiers" in say(ELEC, "customer CUST-02791"))
check("admin can look up a customer", "CUST-02791" in say(ADMIN, "tell me about customer CUST-02791") and "customer" in say(ADMIN, "tell me about customer CUST-02791"))
hist_asia = client.get("/api/chat/history", headers=ASIA).json()
hist_ops = client.get("/api/chat/history", headers=OPS).json()
check("chat history is saved per user", len(hist_asia) >= 2 and {m["id"] for m in hist_asia}.isdisjoint({m["id"] for m in hist_ops}))
asia_msg = next(m for m in reversed(hist_asia) if m["role"] == "assistant")
check("feedback on another user's message is rejected (404)", client.post("/api/chat/feedback", headers=OPS, json={"message_id": asia_msg["id"], "rating": 1}).status_code == 404)
check("feedback on your own message is stored", client.post("/api/chat/feedback", headers=ASIA, json={"message_id": asia_msg["id"], "rating": 1}).status_code == 200)
check("chat history can be cleared by its owner", client.delete("/api/chat/history", headers=ASIA).json()["deleted"] >= 2 and client.get("/api/chat/history", headers=ASIA).json() == [])
check("clearing your history does not touch other users", len(client.get("/api/chat/history", headers=OPS).json()) == len(hist_ops))

failed = [n for ok, n in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} security checks passed")
sys.exit(1 if failed else 0)
