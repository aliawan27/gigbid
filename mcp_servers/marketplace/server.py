"""GigBid Marketplace MCP server (A2): wraps the marketplace port (GigSim or live Upwork, chosen by config).

* Read tools:  search_jobs, get_job, get_client_history, get_market_stats, get_connects_balance,
               list_messages, list_proposals, get_platform_policy
* Write tools: create_proposal_draft, submit_proposal, send_message — Pydantic input/output schemas,
               annotations, mandatory idempotency key, dry_run preview (exactly what would be sent + cost)
* Bearer-token auth on HTTP, per-user rate limiter under GigSim's limit, append-only audit log
  (user, tool, masked arguments, result, trace id) in logs/audit.jsonl

Run: python -m mcp_servers.marketplace.server --http 8092
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import argparse
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from agent.marketplace_port import MarketplaceUnavailable, get_adapter
from agent.safety import mask_obj

AUDIT = Path(os.getenv("GIGBID_AUDIT_LOG", Path(__file__).resolve().parents[2] / "logs" / "audit.jsonl"))
TOKEN = os.getenv("MARKETPLACE_MCP_TOKEN", "marketplace-dev-token")
USER_RPM = int(os.getenv("MARKETPLACE_USER_RPM", "30"))

mcp = FastMCP("gigbid-marketplace", instructions="Marketplace access for GigBid agents. Write tools require a human-"
              "approved idempotency key; use dry_run=true to preview exactly what would be sent and its Connects cost.")
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DRAFT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)
_hits: dict[str, deque] = defaultdict(deque)
_drafts: dict[str, dict] = {}
_port = None


def port():
    global _port
    if _port is None:
        _port = get_adapter()
    return _port


def _limit(user_id: str) -> None:
    q, now = _hits[user_id], time.time()
    while q and q[0] < now - 60:
        q.popleft()
    if len(q) >= USER_RPM:
        raise ValueError(f"rate limit: max {USER_RPM} marketplace calls per minute per user; retry shortly")
    q.append(now)


def audit(user_id: str, tool: str, args: dict, result, trace_id: str) -> None:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": time.time(), "user": user_id, "tool": tool, "args": mask_obj(args),
           "result": mask_obj(result if isinstance(result, (dict, list, str)) else str(result)), "trace_id": trace_id}
    with AUDIT.open("a", encoding="utf-8") as f:  # append-only
        f.write(json.dumps(rec, default=str)[:4000] + "\n")


async def _read(_tool: str, _user: str, _trace: str, coro_fn, **args):
    _limit(_user)
    try:
        res = await coro_fn(**args)
    except MarketplaceUnavailable as e:
        audit(_user, _tool, args, {"error": str(e)}, _trace)
        raise ValueError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
    audit(_user, _tool, args, {"ok": True, "n": len(res) if isinstance(res, list) else 1}, _trace)
    return res


UserId = Annotated[str, Field(description="GigBid user / freelancer id on whose behalf the call is made")]
TraceId = Annotated[str, Field(description="Trace id propagated from the UI request")]


@mcp.tool(annotations=READ)
async def search_jobs(user_id: UserId, query: str = "", category: str = "", since: str = "",
                      limit: Annotated[int, Field(ge=1, le=50)] = 20, trace_id: TraceId = "") -> list[dict]:
    """Search open jobs (optionally by keywords, category, posted-after timestamp)."""
    return await _read("search_jobs", user_id, trace_id, port().search_jobs, query=query, category=category, since=since, limit=limit)


@mcp.tool(annotations=READ)
async def get_job(user_id: UserId, job_id: str, trace_id: TraceId = "") -> dict:
    """Get one job post by id (title, description, skills, budget, client id, Connects cost)."""
    return await _read("get_job", user_id, trace_id, port().get_job, job_id=job_id)


@mcp.tool(annotations=READ)
async def get_client_history(user_id: UserId, client_id: str, trace_id: TraceId = "") -> dict:
    """Get a client's public history: spend, hires, payment verification, rating, reviews."""
    return await _read("get_client_history", user_id, trace_id, port().get_client_history, client_id=client_id)


@mcp.tool(annotations=READ)
async def get_market_stats(user_id: UserId, category: str, complexity: Annotated[int, Field(ge=1, le=5)] = 2,
                           trace_id: TraceId = "") -> dict:
    """Historical price statistics (p25/median/p75 USD) for a job category and complexity (1-5)."""
    return await _read("get_market_stats", user_id, trace_id, port().get_market_stats, category=category, complexity=complexity)


@mcp.tool(annotations=READ)
async def get_connects_balance(user_id: UserId, trace_id: TraceId = "") -> dict:
    """Current Connects balance of the user."""
    return await _read("get_connects_balance", user_id, trace_id, port().get_connects_balance, user_id=user_id)


@mcp.tool(annotations=READ)
async def list_messages(user_id: UserId, trace_id: TraceId = "") -> list[dict]:
    """List the user's client message threads."""
    return await _read("list_messages", user_id, trace_id, port().list_messages, user_id=user_id)


@mcp.tool(annotations=READ)
async def list_proposals(user_id: UserId, trace_id: TraceId = "") -> list[dict]:
    """List the user's submitted proposals with their current status (viewed/replied/interview/hired/ignored)."""
    return await _read("list_proposals", user_id, trace_id, port().list_proposals, user_id=user_id)


@mcp.tool(annotations=READ)
async def get_platform_policy(user_id: UserId, trace_id: TraceId = "") -> dict:
    """The marketplace's current platform policy (versioned; rules may change)."""
    fn = getattr(port(), "get_policy", None)
    if fn is None:
        return {"version": "unknown"}
    return await _read("get_platform_policy", user_id, trace_id, fn)


class ProposalIn(BaseModel):
    user_id: str
    job_id: str
    cover_letter: str = Field(min_length=50, max_length=5000)
    screening_answers: list[str] = Field(default_factory=list, max_length=10)
    bid_amount: float = Field(gt=0, le=1_000_000)
    idempotency_key: str = Field(min_length=8, max_length=128, description="Same key => the action happens once")
    dry_run: bool = Field(False, description="Return exactly what would be sent and what it costs; send nothing")
    trace_id: str = ""


class ProposalOut(BaseModel):
    status: str
    dry_run: bool
    job_id: str
    connects_cost: int | None = None
    connects_balance_after: int | None = None
    payload_preview: dict | None = None
    proposal_id: str | None = None
    thread_id: str | None = None
    idempotent_replay: bool = False


async def _preview(p: ProposalIn) -> ProposalOut:
    job = await port().get_job(p.job_id)
    bal = await port().get_connects_balance(p.user_id)
    cost = job.get("connects_cost")
    payload = {"job_id": p.job_id, "cover_letter": p.cover_letter, "screening_answers": p.screening_answers,
               "bid_amount": p.bid_amount}
    return ProposalOut(status="preview", dry_run=True, job_id=p.job_id, connects_cost=cost,
                       connects_balance_after=(bal.get("balance", 0) - (cost or 0)), payload_preview=payload)


@mcp.tool(annotations=DRAFT)
async def create_proposal_draft(p: ProposalIn) -> ProposalOut:
    """Store a proposal DRAFT (nothing is sent, no Connects spent). Returns the dry-run preview and cost."""
    _limit(p.user_id)
    try:
        out = await _preview(p)
    except MarketplaceUnavailable as e:
        raise ValueError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
    replay = p.idempotency_key in _drafts
    _drafts[p.idempotency_key] = out.model_dump()
    out.status, out.dry_run, out.idempotent_replay = "draft_saved", p.dry_run, replay
    audit(p.user_id, "create_proposal_draft", p.model_dump(), out.model_dump(), p.trace_id)
    return out


@mcp.tool(annotations=WRITE)
async def submit_proposal(p: ProposalIn) -> ProposalOut:
    """Submit a human-approved proposal (spends Connects). Idempotent on idempotency_key; dry_run previews only."""
    _limit(p.user_id)
    try:
        if p.dry_run:
            out = await _preview(p)
        else:
            res = await port().submit_proposal(p.user_id, p.model_dump(), p.idempotency_key)
            out = ProposalOut(status=res.get("status", "submitted"), dry_run=False, job_id=p.job_id,
                              connects_cost=res.get("connects_spent"), proposal_id=res.get("proposal_id"),
                              thread_id=res.get("thread_id"), idempotent_replay=bool(res.get("idempotent_replay")))
    except MarketplaceUnavailable as e:
        audit(p.user_id, "submit_proposal", p.model_dump(), {"error": str(e)}, p.trace_id)
        raise ValueError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
    audit(p.user_id, "submit_proposal", p.model_dump(), out.model_dump(), p.trace_id)
    return out


class MessageIn(BaseModel):
    user_id: str
    thread_id: str
    text: str = Field(min_length=1, max_length=4000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    dry_run: bool = False
    trace_id: str = ""


class MessageOut(BaseModel):
    status: str
    dry_run: bool
    thread_id: str
    preview: str | None = None
    idempotent_replay: bool = False


@mcp.tool(annotations=WRITE)
async def send_message(m: MessageIn) -> MessageOut:
    """Send a human-approved message in a client thread. Idempotent on idempotency_key; dry_run previews only."""
    _limit(m.user_id)
    if m.dry_run:
        out = MessageOut(status="preview", dry_run=True, thread_id=m.thread_id, preview=m.text)
    else:
        try:
            res = await port().send_message(m.user_id, m.thread_id, m.text, m.idempotency_key)
        except MarketplaceUnavailable as e:
            raise ValueError(f"MARKETPLACE_UNAVAILABLE: {e}") from e
        out = MessageOut(status=res.get("status", "sent"), dry_run=False, thread_id=m.thread_id,
                         idempotent_replay=bool(res.get("idempotent_replay")))
    audit(m.user_id, "send_message", m.model_dump(), out.model_dump(), m.trace_id)
    return out


def http_app():
    """Streamable-HTTP ASGI app guarded by a bearer token (pure ASGI wrapper; MCP lifespan passes through)."""
    from starlette.responses import JSONResponse
    mcp.settings.stateless_http = True
    inner = mcp.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
            if auth != f"Bearer {TOKEN}":
                return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        await inner(scope, receive, send)
    return app


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int)
    a = ap.parse_args()
    if not a.http:
        return mcp.run()
    import uvicorn
    uvicorn.run(http_app(), host="0.0.0.0", port=a.http, log_level="warning")


if __name__ == "__main__":
    main()
