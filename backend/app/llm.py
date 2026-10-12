"""Thin client for the local Ollama server (chat + embeddings). No cloud calls, no API keys."""
from __future__ import annotations

import json
import time

import httpx

from .config import CHAT_MODEL, EMBED_MODEL, LLM_TIMEOUT, OLLAMA_URL

_status = {"ts": 0.0, "models": [], "up": False}
_warm = {"chat": False}


def status(max_age: float = 5.0) -> dict:
    """Is Ollama up and which models are pulled?  (cached for a few seconds)"""
    if time.time() - _status["ts"] < max_age:
        return _status
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        models = [m["name"] for m in r.json().get("models", [])]
        _status.update(up=True, models=models)
    except Exception:
        _status.update(up=False, models=[])
    _status["ts"] = time.time()
    return _status


def _has(model: str) -> bool:
    names = status()["models"]
    if ":" in model:
        return model in names
    return any(m == model or m == f"{model}:latest" for m in names)


def chat_ready() -> bool:
    return status()["up"] and _has(CHAT_MODEL)


def embed_ready() -> bool:
    return status()["up"] and _has(EMBED_MODEL)


def embed(texts: list[str]) -> list[list[float]]:
    # embeddings run on CPU (num_gpu=0): the chat model keeps the whole 6 GB GPU and the two models never evict each other
    r = httpx.post(f"{OLLAMA_URL}/api/embed", timeout=LLM_TIMEOUT,
                   json={"model": EMBED_MODEL, "input": texts, "keep_alive": "30m", "options": {"num_gpu": 0}})
    r.raise_for_status()
    return r.json()["embeddings"]


def chat(messages: list[dict], schema: dict | None = None, temperature: float = 0.1,
         num_predict: int = 400) -> str:
    body = {
        "model": CHAT_MODEL, "messages": messages, "stream": False, "keep_alive": "30m",
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": 4096},
    }
    if schema:
        body["format"] = schema  # constrained decoding: output MUST match this JSON schema
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]


def chat_stream(messages: list[dict], temperature: float = 0.2, num_predict: int = 500):
    body = {
        "model": CHAT_MODEL, "messages": messages, "stream": True, "keep_alive": "30m",
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": 4096},
    }
    with httpx.stream("POST", f"{OLLAMA_URL}/api/chat", json=body, timeout=LLM_TIMEOUT) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("message", {}).get("content"):
                yield chunk["message"]["content"]
            if chunk.get("done"):
                break


def is_warm() -> bool:
    return _warm["chat"]


def warm_up() -> None:
    """Loads the chat + embedding models into memory at startup so the first user question is not a 60-second cold start."""
    try:
        if chat_ready():
            chat([{"role": "user", "content": "ok"}], num_predict=1)
            _warm["chat"] = True
        if embed_ready():
            embed(["warm up"])
    except Exception:
        pass