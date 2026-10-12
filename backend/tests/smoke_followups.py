"""Manual check: follow-up questions and record lookups. Run: python -m tests.smoke_followups"""
from app import chat
from app.security import ROLE_POLICY, User


def U(role, scope=None):
    return User(1, role, role, role, scope, ROLE_POLICY[role])


def ask(u, q, hist):
    r = chat.answer_sync(u, q, hist)
    m = r["meta"] or {}
    plan = m.get("plan") or {}
    brief = {k: v for k, v in plan.items() if k in ("metrics", "group_by", "filters", "basis")}
    print(f"Q: {q}\n   src={m.get('plan_source')} plan={brief} rows={(m.get('table') or {}).get('rows', [])[:3]}")
    print(f"   A: {r['text'][:170]!r} ({r['done']['ms']}ms)")
    hist += [{"role": "user", "content": q}, {"role": "assistant", "content": r["text"], "plan": m.get("plan")}]


if __name__ == "__main__":
    a = U("admin")
    h: list = []
    for q in ["What is the revenue by region?", "and in 2023?", "what about profit", "only Asia", "now by category", "what is the weather like?"]:
        ask(a, q, h)
    ask(a, "show order ORD-000004", [])
    ask(a, "tell me about customer CUST-02791", [])
    ask(U("regional_manager", "Asia"), "show order ORD-000001", [])
    ask(U("operations"), "show order ORD-000004", [])
