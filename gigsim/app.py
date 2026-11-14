"""GigSim — the GigBid marketplace simulator (written for this project; synthetic data only).

REST API that behaves like a small freelance marketplace:
  * bearer-token auth, per-token rate limit (429 + Retry-After) and occasional 5xx errors
  * jobs (seed pool + a live stream released over time, incl. duplicates/scams/injections)
  * clients with public history and HIDDEN preferences
  * Connects balance, proposals (idempotent), client decisions (LLM with heuristic fallback)
  * message threads, a versioned platform policy (the 2 Nov change request lives here)

Run: uvicorn gigsim.app:app --port 8081
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

SEED = Path(__file__).parent / "seed"
TOKEN = os.getenv("GIGSIM_API_TOKEN", "gigsim-dev-token")
RATE_PER_MIN = int(os.getenv("GIGSIM_RATE_PER_MIN", "120"))
ERROR_RATE = float(os.getenv("GIGSIM_ERROR_RATE", "0.02"))
STREAM_EVERY_S = int(os.getenv("GIGSIM_STREAM_EVERY_S", "300"))
WEEKLY_CONNECTS = 200

app = FastAPI(title="GigSim", version="1.1.0", description="Synthetic freelance marketplace simulator")
_lock = threading.Lock()
_started = time.time()


def _load(name):
    return json.loads((SEED / name).read_text(encoding="utf-8"))


JOBS = {j["job_id"]: j for j in _load("jobs.json")}
STREAM = _load("stream.json")
CLIENTS = {c["client_id"]: c for c in _load("clients.json")}
MARKET = _load("market_stats.json")
POLICY = json.loads((SEED / "policy.json").read_text(encoding="utf-8"))
CONNECTS: dict[str, int] = defaultdict(lambda: WEEKLY_CONNECTS)
PROPOSALS: dict[str, dict] = {}
IDEMP: dict[str, dict] = {}
THREADS: dict[str, dict] = {}
_hits: dict[str, deque] = defaultdict(deque)


def public(obj: dict) -> dict:
    return {k: v for k, v in obj.items() if not k.startswith("_")}


def auth(request: Request, authorization: str = Header(default="")) -> str:
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "invalid token")
    now = time.time()
    q = _hits[authorization]
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= RATE_PER_MIN:
        raise HTTPException(429, "rate limit", headers={"Retry-After": "10"})
    q.append(now)
    if ERROR_RATE and request.method == "GET" and random.random() < ERROR_RATE:
        raise HTTPException(503, "transient upstream error (simulated)")
    return authorization


def _released_stream():
    n = int((time.time() - _started) / STREAM_EVERY_S) + 3
    return STREAM[: min(n, len(STREAM))]


def connects_cost(job: dict) -> int:
    cost = job["connects_cost"]
    for rule in POLICY.get("connects_rules", []):
        if rule["type"] == "budget_over" and job.get("budget", 0) > rule["threshold"]:
            cost = int(round(cost * rule["multiplier"]))
    return cost


def _job_out(j):
    o = public(j)
    o["connects_cost"] = connects_cost(j)
    return o


@app.get("/health")
def health():
    return {"ok": True, "policy_version": POLICY["version"]}


@app.get("/policy")
def policy(_=Depends(auth)):
    return POLICY


@app.get("/jobs")
def search_jobs(q: str = "", category: str = "", since: str = "", limit: int = 50, offset: int = 0, _=Depends(auth)):
    pool = list(JOBS.values()) + _released_stream()
    out = []
    for j in pool:
        text = (j["title"] + " " + j["description"] + " " + " ".join(j["skills"])).lower()
        if q and not all(t in text for t in q.lower().split()):
            continue
        if category and j["category"] != category:
            continue
        if since and j["posted_at"] <= since:
            continue
        out.append(_job_out(j))
    out.sort(key=lambda j: j["posted_at"], reverse=True)
    return {"total": len(out), "jobs": out[offset: offset + limit]}


@app.get("/jobs/{job_id}")
def get_job(job_id: str, _=Depends(auth)):
    j = JOBS.get(job_id) or next((s for s in _released_stream() if s["job_id"] == job_id), None)
    if not j:
        raise HTTPException(404, "job not found")
    return _job_out(j)


@app.get("/clients/{client_id}")
def client_history(client_id: str, _=Depends(auth)):
    c = CLIENTS.get(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    return public(c)


@app.get("/market/stats")
def market_stats(category: str, complexity: int = 2, _=Depends(auth)):
    s = MARKET["by_category_complexity"].get(f"{category}:{max(1, min(5, complexity))}")
    if not s:
        raise HTTPException(404, "unknown category")
    return {"category": category, "complexity": complexity, **s, "currency": "USD"}


@app.get("/freelancers/{fid}/connects")
def connects_balance(fid: str, _=Depends(auth)):
    return {"freelancer_id": fid, "balance": CONNECTS[fid], "weekly_allowance": WEEKLY_CONNECTS}


class ProposalIn(BaseModel):
    freelancer_id: str
    job_id: str
    cover_letter: str = Field(min_length=20, max_length=5000)
    screening_answers: list[str] = []
    bid_amount: float = Field(gt=0)
    idempotency_key: str = Field(min_length=8)


@app.post("/proposals")
def submit_proposal(p: ProposalIn, _=Depends(auth)):
    with _lock:
        if p.idempotency_key in IDEMP:
            return {**IDEMP[p.idempotency_key], "idempotent_replay": True}
        job = JOBS.get(p.job_id) or next((s for s in _released_stream() if s["job_id"] == p.job_id), None)
        if not job:
            raise HTTPException(404, "job not found")
        cost = connects_cost(job)
        if CONNECTS[p.freelancer_id] < cost:
            raise HTTPException(402, "not enough connects")
        violation = _policy_violation(p.cover_letter)
        if violation:
            raise HTTPException(422, f"policy violation: {violation}")
        CONNECTS[p.freelancer_id] -= cost
        pid = "prop-" + hashlib.sha1(p.idempotency_key.encode()).hexdigest()[:10]
        rec = {"proposal_id": pid, "job_id": p.job_id, "freelancer_id": p.freelancer_id, "bid_amount": p.bid_amount,
               "connects_spent": cost, "status": "submitted", "submitted_at": time.time(),
               "cover_letter": p.cover_letter}
        PROPOSALS[pid] = rec
        IDEMP[p.idempotency_key] = {k: rec[k] for k in ("proposal_id", "status", "connects_spent")}
    from gigsim.clients import decide  # lazy: may call an LLM
    d = decide(job, CLIENTS[job["client_id"]], p.cover_letter, p.bid_amount)
    with _lock:
        rec["status"] = d["status"]
        rec["decision_reason"] = d.get("reason", "")
        IDEMP[p.idempotency_key]["status"] = d["status"]
        if d["status"] in ("replied", "interview", "hired"):
            tid = f"thr-{pid}"
            THREADS[tid] = {"thread_id": tid, "job_id": job["job_id"], "client_id": job["client_id"],
                            "freelancer_id": p.freelancer_id, "messages": [
                                {"from": "client", "text": d["reply"], "at": time.time()}]}
            rec["thread_id"] = tid
    return {k: rec[k] for k in ("proposal_id", "status", "connects_spent")} | {"thread_id": rec.get("thread_id")}


def _policy_violation(text: str) -> str | None:
    low = text.lower()
    for rule in POLICY.get("proposal_rules", []):
        if rule["type"] == "forbid_regex":
            import re
            if re.search(rule["pattern"], text, re.I):
                return rule["id"]
        if rule["type"] == "require_phrase" and rule["phrase"].lower() not in low:
            return rule["id"]
    return None


@app.get("/proposals")
def list_proposals(freelancer_id: str, _=Depends(auth)):
    return {"proposals": [p for p in PROPOSALS.values() if p["freelancer_id"] == freelancer_id]}


@app.get("/messages")
def list_messages(freelancer_id: str, _=Depends(auth)):
    return {"threads": [t for t in THREADS.values() if t["freelancer_id"] == freelancer_id]}


class MessageIn(BaseModel):
    thread_id: str
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8)


@app.post("/messages")
def send_message(m: MessageIn, _=Depends(auth)):
    with _lock:
        if m.idempotency_key in IDEMP:
            return {**IDEMP[m.idempotency_key], "idempotent_replay": True}
        t = THREADS.get(m.thread_id)
        if not t:
            raise HTTPException(404, "thread not found")
        t["messages"].append({"from": "freelancer", "text": m.text, "at": time.time()})
        res = {"thread_id": m.thread_id, "status": "sent", "n_messages": len(t["messages"])}
        IDEMP[m.idempotency_key] = res
    return res


@app.post("/admin/client-message")
def inject_client_message(body: dict, _=Depends(auth)):
    """Test hook: append a client message to a thread (used by demos/tests)."""
    t = THREADS.get(body["thread_id"])
    if not t:
        raise HTTPException(404, "thread not found")
    t["messages"].append({"from": "client", "text": body["text"], "at": time.time()})
    return {"ok": True}


@app.exception_handler(HTTPException)
async def _http_exc(_req, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
