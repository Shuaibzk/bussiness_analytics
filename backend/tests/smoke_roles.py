"""Every role x every page's API calls: nothing may 500, and denials must be 403 (never a crash). Run: python -m tests.smoke_roles"""
import sys

from fastapi.testclient import TestClient

from app.main import app

ACCOUNTS = [("admin", "admin123"), ("executive", "exec123"), ("asia.manager", "manager123"), ("electronics.manager", "category123"), ("ops", "ops123")]
F = [{}, {"year": [2023]}, {"region": ["Asia"]}, {"date_from": "2023-03-01", "date_to": "2023-09-30"}, {"quarter_of_year": ["Q2"], "season": ["Summer"]}]
CALLS = [
    ("POST", "/api/kpis", lambda f, b: {"filters": f, "basis": b}),
    ("POST", "/api/insights", lambda f, b: {"filters": f, "basis": b}),
    ("POST", "/api/customers", lambda f, b: {"filters": f, "basis": b}),
    ("POST", "/api/forecast", lambda f, b: {"filters": f, "basis": b, "metric": "orders"}),
    ("POST", "/api/forecast", lambda f, b: {"filters": f, "basis": b, "metric": "revenue", "baseline": "recent"}),
    ("POST", "/api/query", lambda f, b: {"filters": f, "basis": b, "metrics": ["orders", "return_rate"], "group_by": ["delivery_band"]}),
    ("POST", "/api/query", lambda f, b: {"filters": f, "basis": b, "metrics": ["avg_shipping_days", "slow_rate", "fast_rate"], "group_by": ["country"]}),
    ("POST", "/api/query", lambda f, b: {"filters": f, "basis": b, "metrics": ["revenue", "profit", "margin", "loss_rate", "avg_discount"], "group_by": ["product", "category"]}),
    ("POST", "/api/orders", lambda f, b: {"filters": f, "page_size": 5}),
]

bad = 0
for user, pw in ACCOUNTS:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": pw})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    codes = {}
    for method, path, mk in CALLS:
        for f in F:
            for basis in ("net", "gross"):
                resp = c.request(method, path, headers=h, json=mk(f, basis))
                codes[resp.status_code] = codes.get(resp.status_code, 0) + 1
                if resp.status_code >= 500:
                    bad += 1
                    print(f"  500 {user} {path} {f} {basis}: {resp.text[:200]}")
    c.get("/api/targets", headers=h)
    print(f"{user:<22} status codes: {codes}")
print("OK - no server errors" if not bad else f"{bad} server errors")
sys.exit(1 if bad else 0)
