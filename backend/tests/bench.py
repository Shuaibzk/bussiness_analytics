"""Micro-benchmark used to back optimisation claims with numbers.  Run: python -m tests.bench"""
import statistics as st
import time

from app import engine
from app.rag import retriever
from app.security import ROLE_POLICY, User

admin = User(1, "admin", "a", "admin", None, ROLE_POLICY["admin"])
asia = User(2, "m", "m", "regional_manager", "Asia", ROLE_POLICY["regional_manager"])

QUERIES = [
    dict(metrics=["revenue", "profit"], group_by=["month"]),
    dict(metrics=["revenue"], group_by=["category"]),
    dict(metrics=["orders", "return_rate"], group_by=["region", "category"]),
    dict(metrics=["margin", "loss_rate"], group_by=["discount"]),
    dict(metrics=["revenue"], group_by=["product"], limit=10),
    dict(metrics=["customers"], group_by=["segment"]),
]


def timeit(fn, n=1):
    t = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t) / n * 1000


def run(user, label):
    engine._CACHE.clear()
    cold = [timeit(lambda q=q: engine.run_query(user, **q)) for q in QUERIES]
    warm = [timeit(lambda q=q: engine.run_query(user, **q), 200) for q in QUERIES]
    print(f"{label:<14} cold query  median {st.median(cold):6.2f} ms  max {max(cold):6.2f} ms | cached median {st.median(warm) * 1000:6.1f} us")


run(admin, "admin")
run(asia, "asia manager")
engine._CACHE.clear()
print(f"dashboard load (8 KPI cards + sparkline + insights), cold: {timeit(lambda: (engine.kpis(admin, {}, 'net'), engine.insights(admin, {}, 'net'))):.1f} ms")
rt = retriever()
rt.reload()
print(f"hybrid retrieval over {len(rt.docs)} docs (BM25 + query embedding on CPU if Ollama is up) median {st.median([timeit(lambda: rt.search(admin, 'which discount levels cause loss making orders')) for _ in range(30)]):.1f} ms")
