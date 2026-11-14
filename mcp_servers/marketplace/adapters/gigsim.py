"""GigSim adapter: REST client with polite client-side rate limiting, retries with exponential backoff on
429/5xx (honouring Retry-After) and a clear MarketplaceUnavailable error for degraded mode."""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from agent.marketplace_port import MarketplaceUnavailable


class GigSimAdapter:
    name = "gigsim"

    def __init__(self, base_url: str | None = None, token: str | None = None, max_rpm: int | None = None):
        from agent.config import CONFIG
        self.base = base_url or os.getenv("GIGSIM_BASE_URL", "http://localhost:8081")
        self.token = token or os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
        self.min_gap = 60.0 / (max_rpm or CONFIG["marketplace"]["max_requests_per_minute"])
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def _req(self, method: str, path: str, **kw) -> Any:
        delay = 0.5
        for attempt in range(4):
            async with self._lock:  # stay under GigSim's limits
                wait = self._last + self.min_gap - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=20) as c:
                    r = await c.request(method, self.base + path, headers={"Authorization": f"Bearer {self.token}"}, **kw)
            except httpx.HTTPError as e:
                err = str(e)
            else:
                if r.status_code < 400:
                    return r.json()
                if r.status_code in (429, 500, 502, 503, 504):
                    err = f"{r.status_code}"
                    delay = max(delay, float(r.headers.get("retry-after", 0) or 0))
                else:
                    raise ValueError(f"GigSim {r.status_code}: {r.text[:200]}")
            await asyncio.sleep(delay)
            delay *= 2
        raise MarketplaceUnavailable(f"GigSim unavailable after retries ({err})")

    async def search_jobs(self, query="", category="", since="", limit=20):
        return (await self._req("GET", "/jobs", params={"q": query, "category": category, "since": since, "limit": limit}))["jobs"]

    async def get_job(self, job_id):
        return await self._req("GET", f"/jobs/{job_id}")

    async def get_client_history(self, client_id):
        return await self._req("GET", f"/clients/{client_id}")

    async def get_market_stats(self, category, complexity):
        return await self._req("GET", "/market/stats", params={"category": category, "complexity": complexity})

    async def get_connects_balance(self, user_id):
        return await self._req("GET", f"/freelancers/{user_id}/connects")

    async def list_messages(self, user_id):
        return (await self._req("GET", "/messages", params={"freelancer_id": user_id}))["threads"]

    async def list_proposals(self, user_id):
        return (await self._req("GET", "/proposals", params={"freelancer_id": user_id}))["proposals"]

    async def get_policy(self):
        return await self._req("GET", "/policy")

    async def submit_proposal(self, user_id, payload, idempotency_key):
        body = {"freelancer_id": user_id, "job_id": payload["job_id"], "cover_letter": payload["cover_letter"],
                "screening_answers": payload.get("screening_answers", []), "bid_amount": payload["bid_amount"],
                "idempotency_key": idempotency_key}
        return await self._req("POST", "/proposals", json=body)

    async def send_message(self, user_id, thread_id, text, idempotency_key):
        return await self._req("POST", "/messages", json={"thread_id": thread_id, "text": text, "idempotency_key": idempotency_key})
