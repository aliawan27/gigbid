"""MultiServerMCPClient setup + per-agent tool allowlists (A6 client discipline).

Each agent gets only the tools it needs, filtered by name. Calls have timeouts and bounded retries with
backoff; when the marketplace server is down we raise MarketplaceUnavailable so the graph parks the job
(degraded mode) and the UI shows the banner. Transport is streamable HTTP; URLs come from the environment.
"""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.marketplace_port import MarketplaceUnavailable

ALLOWLIST: dict[str, set[str]] = {
    "scout": {"search_jobs", "get_job"},
    "analyst": set(),
    "risk_assessor": {"get_client_history"},
    "fit_matcher": {"search_evidence", "list_skills"},
    "pricing": {"get_market_stats", "get_connects_balance", "get_client_history"},
    "writer": {"search_evidence", "search_past_proposals", "get_case_study"},
    "critic": {"search_evidence", "get_case_study"},
    "verifier": {"search_evidence"},
    "compliance": set(),
    "client_liaison": {"list_messages", "send_message", "free_slots", "create_tentative_hold", "create_email_draft"},
    "submitter": {"create_proposal_draft", "submit_proposal"},
    "api": {"list_proposals", "list_messages", "get_connects_balance", "get_job", "search_jobs", "get_platform_policy",
            "create_proposal_draft", "submit_proposal", "send_message"},
}
SERVER_OF = {
    "search_evidence": "portfolio", "search_past_proposals": "portfolio", "get_case_study": "portfolio",
    "list_skills": "portfolio", "free_slots": "workspace", "create_tentative_hold": "workspace",
    "create_email_draft": "workspace",
}


def connections() -> dict[str, dict]:
    return {
        "portfolio": {"url": os.getenv("PORTFOLIO_MCP_URL", "http://localhost:8091/mcp/"), "transport": "streamable_http"},
        "marketplace": {"url": os.getenv("MARKETPLACE_MCP_URL", "http://localhost:8092/mcp/"), "transport": "streamable_http",
                        "headers": {"Authorization": f"Bearer {os.getenv('MARKETPLACE_MCP_TOKEN', 'marketplace-dev-token')}"}},
        "workspace": {"url": os.getenv("WORKSPACE_MCP_URL", "http://localhost:8093/mcp/"), "transport": "streamable_http"},
    }


_tools_cache: dict[str, dict] = {}


async def _server_tools(server: str) -> dict:
    if server not in _tools_cache:
        client = MultiServerMCPClient({server: connections()[server]})
        _tools_cache[server] = {t.name: t for t in await client.get_tools(server_name=server)}
    return _tools_cache[server]


async def tools_for(agent: str) -> list:
    """LangChain tool objects an agent may use (used by the single-agent/supervisor baselines too)."""
    out = []
    for name in sorted(ALLOWLIST[agent]):
        try:
            out.append((await _server_tools(SERVER_OF.get(name, "marketplace")))[name])
        except Exception:  # noqa: BLE001
            continue
    return out


async def call(agent: str, tool: str, args: dict, timeout: float = 30, retries: int = 2) -> Any:
    if tool not in ALLOWLIST.get(agent, set()):
        raise PermissionError(f"agent '{agent}' is not allowed to call '{tool}'")
    server = SERVER_OF.get(tool, "marketplace")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            t = (await _server_tools(server))[tool]
            out = await asyncio.wait_for(t.ainvoke(args), timeout)
            res = _parse(out)
            if tool in LIST_TOOLS and not isinstance(res, list):
                res = [] if res in ("", None, "[]") else [res]
            return res
        except Exception as e:  # noqa: BLE001
            last = e
            _tools_cache.pop(server, None)
            msg = str(e)
            if "rate limit" in msg:
                await asyncio.sleep(5)
            elif attempt < retries:
                await asyncio.sleep(0.5 * 2 ** attempt)
    msg = str(last)
    outage = ("MARKETPLACE_UNAVAILABLE" in msg or "rate limit" in msg or "TaskGroup" in msg
              or "onnect" in msg or isinstance(last, (asyncio.TimeoutError, OSError)))
    if server == "marketplace" and outage:
        raise MarketplaceUnavailable(f"{tool}: {last}")
    raise RuntimeError(f"MCP {server}.{tool} failed: {last}")


LIST_TOOLS = {"search_jobs", "list_messages", "list_proposals", "search_evidence", "search_past_proposals", "free_slots"}


def _parse(out: Any) -> Any:
    if isinstance(out, tuple):  # (content, artifact) from content_and_artifact tools
        out = out[0]
    if isinstance(out, list) and all(isinstance(o, str) for o in out):
        return [json.loads(o) if o[:1] in "[{" else o for o in out]
    if isinstance(out, list) and out and isinstance(out[0], dict) and "text" in out[0]:
        texts = [o["text"] for o in out]
        parsed = [json.loads(t) if t[:1] in "[{" else t for t in texts]
        return parsed[0] if len(parsed) == 1 else parsed
    if isinstance(out, str) and out[:1] in "[{":
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return out
    return out


async def health() -> dict[str, bool]:
    res = {}
    for s in ("portfolio", "marketplace", "workspace"):
        try:
            _tools_cache.pop(s, None)
            await asyncio.wait_for(_server_tools(s), 20)
            res[s] = True
        except Exception:  # noqa: BLE001
            res[s] = False
    return res
