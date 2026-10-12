"""Hybrid retrieval over the knowledge base: BM25 (keywords) + dense embeddings (meaning), fused with
Reciprocal Rank Fusion.  Works without Ollama (BM25 only) so the app degrades gracefully.

Run:  python -m app.rag      (re-builds documents and embeddings)
"""
from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter

import numpy as np

from . import llm
from .db import connect
from .docs import build_all
from .security import User

_STOP = set("the a an of in on for to and or is are was were be by with what which who how much many me my show tell give from "
            "at as it its this that do does did can you i we our us all there their than then".split())


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    out = []
    count = 0
    for t in toks:
        if t in _STOP:
            continue
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        count += 1
        out.append(t)
    return out


def index_docs(verbose: bool = True) -> dict:
    docs = build_all()
    conn = connect()
    conn.execute("DELETE FROM docs")
    embedded = False
    vectors: list[bytes | None] = [None] * len(docs)
    if llm.embed_ready():
        try:
            for i in range(0, len(docs), 32):
                batch = docs[i:i + 32]
                embs = llm.embed([d["text"] for d in batch])
                for j, e in enumerate(embs):
                    v = np.asarray(e, dtype=np.float32)
                    vectors[i + j] = (v / (np.linalg.norm(v) or 1)).tobytes()
            embedded = True
        except Exception as exc:  # embeddings are an enhancement, not a dependency
            print("embedding failed, falling back to BM25 only:", exc)
            vectors = [None] * len(docs)
    for d, v in zip(docs, vectors):
        conn.execute(
            "INSERT INTO docs (id,title,topic,text,scope_region,scope_category,needs,embedding) VALUES (?,?,?,?,?,?,?,?)",
            (d["id"], d["title"], d["topic"], d["text"], d["scope_region"], d["scope_category"], json.dumps(d["needs"]), v),
        )
    conn.commit()
    conn.close()
    _retriever.reload()
    info = {"documents": len(docs), "embedded": embedded}
    if verbose:
        print(info)
    return info


class Retriever:
    def __init__(self):
        self._lock = threading.Lock()
        self.docs: list[dict] = []
        self.emb: np.ndarray | None = None
        self.df: dict[str, int] = {}
        self.tf: list[Counter] = []
        self.len: np.ndarray = np.zeros(0)
        self.loaded = False

    def reload(self):
        with self._lock:
            conn = connect()
            rows = conn.execute("SELECT * FROM docs").fetchall()
            conn.close()
            self.docs = [dict(r) | {"needs": json.loads(r["needs"] or "[]")} for r in rows]
            self.tf = [Counter(tokenize(d["title"] + " " + d["title"] + " " + d["text"])) for d in self.docs]
            self.len = np.array([sum(c.values()) for c in self.tf], dtype=float)
            self.df = Counter(t for c in self.tf for t in c)
            have = [d["embedding"] is not None for d in self.docs]
            if self.docs and all(have):
                self.emb = np.vstack([np.frombuffer(d["embedding"], dtype=np.float32) for d in self.docs])
            else:
                self.emb = None
            for d in self.docs:
                d.pop("embedding", None)
            self.loaded = True

    @property
    def stats(self) -> dict:
        if not self.loaded:
            self.reload()
        return {"documents": len(self.docs), "dense": self.emb is not None}

    # -- access control ---------------------------------------------------
    @staticmethod
    def visible(user: User, d: dict) -> bool:
        if set(d["needs"]) & user.hidden:
            return False
        sr, sc = d["scope_region"], d["scope_category"]
        if sr == "*":
            return True
        col = user.row_scope_col
        if col == "region":
            return sr == user.scope_value and sc is None
        if col == "category":
            return sc == user.scope_value and sr is None
        return True

    def search(self, user: User, query: str, k: int = 4) -> list[dict]:
        if not self.loaded:
            self.reload()
        mask = np.array([self.visible(user, d) for d in self.docs])
        if not mask.any():
            return []
        # BM25
        q = tokenize(query)
        n = len(self.docs)
        avgdl = self.len.mean() or 1
        bm = np.zeros(n)
        for t in set(q):
            df = self.df.get(t, 0)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for i, c in enumerate(self.tf):
                f = c.get(t, 0)
                if f:
                    bm[i] += idf * f * 2.5 / (f + 1.5 * (0.25 + 0.75 * self.len[i] / avgdl))
        ranks: list[np.ndarray] = [bm]
        # dense
        if self.emb is not None and llm.embed_ready():
            try:
                qv = np.asarray(llm.embed([query])[0], dtype=np.float32)
                qv /= np.linalg.norm(qv) or 1
                ranks.append(self.emb @ qv)
            except Exception:
                pass
        fused = np.zeros(n)
        for score in ranks:
            s = np.where(mask, score, -np.inf)
            order = np.argsort(-s)
            for rank, i in enumerate(order[:50]):
                if np.isfinite(s[i]) and (s[i] > 0 or score is not bm):
                    fused[i] += 1.0 / (60 + rank)
        if not user.row_scope_col:
            # unrestricted roles: prefer the global fact sheet unless the question names a specific region/category
            ql = query.lower()
            for i, d in enumerate(self.docs):
                named = [v for v in (d["scope_region"], d["scope_category"]) if v and v != "*"]
                if named and not any(v.lower() in ql for v in named):
                    fused[i] *= 0.55
        fused = np.where(mask, fused, -1)
        top = [i for i in np.argsort(-fused)[:k] if fused[i] > 0]
        return [{**self.docs[i], "score": round(float(fused[i]), 4)} for i in top]


_retriever = Retriever()


def retriever() -> Retriever:
    return _retriever


if __name__ == "__main__":
    index_docs()
