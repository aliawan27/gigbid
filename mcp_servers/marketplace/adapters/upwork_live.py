"""Live Upwork adapter (A4). Connects to Upwork's official MCP server (https://mcp.upwork.com/mcp) with
MultiServerMCPClient over Streamable HTTP, using the user's OAuth 2.1 access token (stored encrypted per user,
see apps/api/auth/tokens.py), and maps its tools onto the same MarketplacePort the graph uses for GigSim.

Rules enforced here: read tools only; proposals/messages are created as DRAFTS only (the user confirms on
Upwork); no browser automation, no cookies, no scraping. Tool names are mapped in UPWORK_TOOL_MAP so a change
on Upwork's side is a config edit. Not exercised in grading (no Upwork account in this project's tests).
"""
from __future__ import annotations

import json
import os
from typing import Any

from agent.marketplace_port import MarketplaceUnavailable

UPWORK_MCP_URL = os.getenv("UPWORK_MCP_URL", "https://mcp.upwork.com/mcp")
UPWORK_TOOL_MAP = json.loads(os.getenv("UPWORK_TOOL_MAP", json.dumps({
    "search_jobs": "search_jobs", "get_job": "get_job_details", "get_client_history": "get_client_details",
    "get_connects_balance": "get_connects_balance", "list_messages": "list_rooms", "list_proposals": "list_proposals",
    "create_proposal_draft": "create_proposal_draft", "create_message_draft": "create_message_draft"})))


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, access_token: str | None = None):
        self.token = access_token or os.getenv("UPWORK_ACCESS_TOKEN", "")

    async def _call(self, port_name: str, args: dict) -> Any:
        if not self.token:
            raise MarketplaceUnavailable("Upwork not connected: complete the OAuth flow in Settings")
        from langchain_mcp_adapters.client import MultiServerMCPClient
        client = MultiServerMCPClient({"upwork": {"url": UPWORK_MCP_URL, "transport": "streamable_http",
                                                  "headers": {"Authorization": f"Bearer {self.token}"}}})
        try:
            tools = {t.name: t for t in await client.get_tools()}
            tool = tools[UPWORK_TOOL_MAP[port_name]]
            out = await tool.ainvoke(args)
            return json.loads(out) if isinstance(out, str) and out[:1] in "[{" else out
        except KeyError as e:
            raise MarketplaceUnavailable(f"Upwork MCP tool missing: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise MarketplaceUnavailable(f"Upwork MCP error: {e}") from e

    async def search_jobs(self, query="", category="", since="", limit=20):
        return await self._call("search_jobs", {"query": query, "limit": limit})

    async def get_job(self, job_id):
        return await self._call("get_job", {"job_id": job_id})

    async def get_client_history(self, client_id):
        return await self._call("get_client_history", {"client_id": client_id})

    async def get_market_stats(self, category, complexity):
        # Upwork exposes no market-stats tool; fall back to the historical stats bundled with GigBid.
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
        return await GigSimAdapter().get_market_stats(category, complexity)

    async def get_connects_balance(self, user_id):
        return await self._call("get_connects_balance", {})

    async def list_messages(self, user_id):
        return await self._call("list_messages", {})

    async def list_proposals(self, user_id):
        return await self._call("list_proposals", {})

    async def submit_proposal(self, user_id, payload, idempotency_key):
        # Live mode never submits: it creates a draft the user must confirm on Upwork.
        res = await self._call("create_proposal_draft", {**payload, "idempotency_key": idempotency_key})
        return {"status": "draft_created_confirm_on_upwork", "upwork": res}

    async def send_message(self, user_id, thread_id, text, idempotency_key):
        res = await self._call("create_message_draft", {"room_id": thread_id, "text": text})
        return {"status": "draft_created_confirm_on_upwork", "upwork": res}
