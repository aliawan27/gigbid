"""Thin OpenAI-compatible chat client for Groq with automatic API-key rotation.

* GROQ_API_KEYS is a comma-separated list; on 429/401/5xx the next key is tried.
* Every call records tokens, latency and estimated USD into a per-thread usage ledger
  (used by the budget guard, traces and evals).
* GIGBID_FAKE_LLM=1 forces the deterministic fallbacks (CI, tests, degraded mode).
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import time
from typing import Any, TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")

# USD per 1M tokens (input, output) — Groq public pricing, used for cost reporting.
PRICES = {
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
    "qwen/qwen3.8-27b": (0.29, 0.59),
}


class LLMUnavailable(RuntimeError):
    pass


class _KeyRing:
    """Keys rotate per model: a cooldown is tracked per (key, model), so one model hitting its daily cap on a key does not
    block other models on that key. If every key is cooling down for longer than FAIL_FAST_S, fail fast so the caller can
    use its fallback model instead of sleeping."""
    FAIL_FAST_S = 45

    def __init__(self) -> None:
        self.keys = [k.strip() for k in os.getenv("GROQ_API_KEYS", os.getenv("GROQ_API_KEY", "")).split(",") if k.strip()]
        self.i: dict[str, int] = {}
        self.cooldown: dict[tuple[int, str], float] = {}
        self.lock = threading.Lock()

    def current(self, model: str = "") -> tuple[int, str]:
        with self.lock:
            if not self.keys:
                raise LLMUnavailable("no GROQ_API_KEYS configured")
            now = time.time()
            i = self.i.get(model, 0)
            for _ in range(len(self.keys)):
                if self.cooldown.get((i, model), 0) <= now:
                    self.i[model] = i
                    return i, self.keys[i]
                i = (i + 1) % len(self.keys)
            idx = min(range(len(self.keys)), key=lambda k: self.cooldown.get((k, model), 0))
            wait = max(0.0, self.cooldown.get((idx, model), 0) - now)
        if wait > self.FAIL_FAST_S:
            raise LLMUnavailable(f"{model}: all keys rate-limited for {wait:.0f}s")
        time.sleep(wait)
        return idx, self.keys[idx]

    def fail(self, idx: int, seconds: float, model: str = "") -> None:
        with self.lock:
            self.cooldown[(idx, model)] = time.time() + seconds
            self.i[model] = (idx + 1) % len(self.keys)


KEYS = _KeyRing()

# usage ledger: list of dicts per logical run (contextvar so concurrent runs don't mix)
_ledger: contextvars.ContextVar[list | None] = contextvars.ContextVar("ledger", default=None)


def start_ledger() -> list:
    led: list = []
    _ledger.set(led)
    return led


def ledger() -> list:
    led = _ledger.get()
    if led is None:
        led = start_ledger()
    return led


def fake_mode() -> bool:
    return os.getenv("GIGBID_FAKE_LLM", "0") == "1"


def _traced(fn):
    from agent.tracing import llm_span
    return llm_span(fn)


def free_model_chain(model: str) -> list[str]:
    """Each Groq free-tier model has its own daily token cap per key, so a call that finds its model exhausted moves on to
    the next free model instead of failing: preferred model first, then the rest of models.free_chain (agent/config.yaml)."""
    try:
        from agent.config import CONFIG
        chain = CONFIG["models"].get("free_chain", [])
    except Exception:  # noqa: BLE001
        chain = []
    return [model] + [m for m in chain if m != model]


def chat(model: str, messages: list[dict], **kw) -> dict:
    last: Exception | None = None
    for m in free_model_chain(model):
        try:
            return _chat_one(m, messages, **kw)
        except LLMUnavailable as e:
            last = e
            if fake_mode() or "rate-limited" not in str(e) and "exhausted" not in str(e):
                raise
    raise LLMUnavailable(f"all free models exhausted: {last}")


@_traced
def _chat_one(model: str, messages: list[dict], *, node: str = "", temperature: float = 0.2,
         max_tokens: int = 1200, json_mode: bool = False, tools: list | None = None, timeout: float = 60) -> dict:
    """Returns {'content', 'tool_calls', 'usage', 'latency'}; raises LLMUnavailable after retries."""
    if fake_mode():
        raise LLMUnavailable("fake mode")
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if "gpt-oss" in model:
        body["reasoning_effort"] = "low"
    last = None
    for attempt in range(2 * max(1, len(KEYS.keys)) + 1):
        idx, key = KEYS.current(model)
        t0 = time.time()
        try:
            r = httpx.post(f"{BASE_URL}/chat/completions", json=body, timeout=timeout,
                           headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as e:
            last = str(e)
            time.sleep(min(2 ** attempt, 8))
            continue
        if r.status_code in (429, 401, 403):
            ra = float(r.headers.get("retry-after", "20") or 20)
            KEYS.fail(idx, ra if r.status_code == 429 else 3600, model)
            last = f"{r.status_code}"
            continue
        if r.status_code >= 500:
            last = f"{r.status_code}"
            time.sleep(min(2 ** attempt, 8))
            continue
        if r.status_code == 400 and json_mode and "json" in r.text.lower():
            # model produced invalid JSON; retry once without strict mode
            body.pop("response_format", None)
            last = "json_validate_failed"
            continue
        if r.status_code >= 400:
            raise LLMUnavailable(f"{r.status_code}: {r.text[:300]}")
        data = r.json()
        msg = data["choices"][0]["message"]
        usage = data.get("usage", {})
        lat = time.time() - t0
        pin, pout = PRICES.get(model, (0.2, 0.6))
        cost = usage.get("prompt_tokens", 0) / 1e6 * pin + usage.get("completion_tokens", 0) / 1e6 * pout
        ledger().append({"node": node, "model": model, "in": usage.get("prompt_tokens", 0),
                         "out": usage.get("completion_tokens", 0), "latency": round(lat, 3), "usd": cost})
        return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [], "usage": usage,
                "latency": lat}
    raise LLMUnavailable(f"all keys/retries exhausted: {last}")


def _extract_json(text: str) -> Any:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def structured(model: str, system: str, user: str, schema: type[T], *, node: str = "", temperature: float = 0.1,
               max_tokens: int = 1500) -> T:
    """Ask for a JSON object matching `schema`; validates with Pydantic, one repair attempt."""
    sys = system + "\n\nRespond ONLY with a JSON object matching this JSON schema:\n" + json.dumps(
        schema.model_json_schema())
    msgs = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
    err = None
    for _ in range(2):
        out = chat(model, msgs, node=node, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        try:
            return schema.model_validate(_extract_json(out["content"]))
        except Exception as e:  # noqa: BLE001
            err = e
            msgs = msgs + [{"role": "assistant", "content": out["content"]},
                           {"role": "user", "content": f"That was invalid ({str(e)[:200]}). Return valid JSON only."}]
    raise LLMUnavailable(f"could not parse structured output: {err}")
