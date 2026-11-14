"""R1: the single marketplace port. Everything that touches a marketplace goes through this interface;
two adapters implement it (mcp_servers/marketplace/adapters/gigsim.py and upwork_live.py), chosen by config."""
from __future__ import annotations

from typing import Any, Protocol


class MarketplaceUnavailable(RuntimeError):
    """Raised after retries are exhausted; the UI shows the 'marketplace unavailable' degraded banner."""


class MarketplacePort(Protocol):
    name: str

    async def search_jobs(self, query: str = "", category: str = "", since: str = "", limit: int = 20) -> list[dict[str, Any]]: ...
    async def get_job(self, job_id: str) -> dict[str, Any]: ...
    async def get_client_history(self, client_id: str) -> dict[str, Any]: ...
    async def get_market_stats(self, category: str, complexity: int) -> dict[str, Any]: ...
    async def get_connects_balance(self, user_id: str) -> dict[str, Any]: ...
    async def list_messages(self, user_id: str) -> list[dict[str, Any]]: ...
    async def list_proposals(self, user_id: str) -> list[dict[str, Any]]: ...
    async def submit_proposal(self, user_id: str, payload: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...
    async def send_message(self, user_id: str, thread_id: str, text: str, idempotency_key: str) -> dict[str, Any]: ...


def get_adapter(mode: str | None = None) -> MarketplacePort:
    import os

    from agent.config import CONFIG
    mode = mode or os.getenv("MARKETPLACE_MODE", CONFIG["marketplace"]["mode"])
    if mode == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter
        return UpworkLiveAdapter()
    from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
    return GigSimAdapter()
