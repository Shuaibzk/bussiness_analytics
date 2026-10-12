"""Quick manual check of the chat pipeline. Run: python -m tests.smoke_chat"""
import sys

from app import chat
from app.security import ROLE_POLICY, User


def U(role, scope=None):
    return User(1, role, role, role, scope, ROLE_POLICY[role])


QS = [
    ("admin", None, "Which region has the highest profit?"),
    ("admin", None, "How has revenue changed month by month in 2023?"),
    ("admin", None, "Compare Asia and Europe revenue"),
    ("admin", None, "What is the return rate by category?"),
    ("admin", None, "top 5 products by profit"),
    ("admin", None, "How many orders were cancelled in 2022?"),
    ("admin", None, "Which discount levels cause loss-making orders?"),
    ("regional_manager", "Asia", "What is revenue in Europe?"),
    ("regional_manager", "Asia", "revenue by country"),
    ("operations", None, "What is our profit?"),
    ("operations", None, "average delivery days by shipping method"),
    ("category_manager", "Electronics", "revenue of clothing"),
    ("admin", None, "hello"),
]

if __name__ == "__main__":
    sel = sys.argv[1:]
    for role, scope, q in QS:
        r = chat.answer_sync(U(role, scope), q)
        d, m = r["done"], r["meta"] or {}
        plan = m.get("plan")
        brief = {k: v for k, v in plan.items() if k in ("intent", "metrics", "group_by", "filters")} if plan else None
        print(f"[{role}/{scope}] {q}\n   status={d['status']} mode={d.get('mode')} plan={brief}")
        if m.get("table"):
            print("   rows:", m["table"]["rows"][:4])
        print("   ->", r["text"][:200].replace("\n", " "))
