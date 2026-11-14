"""All-in-one deployment mode for small free hosts (512 MB RAM): one process serves
  /            web UI + API              /gigsim/*      GigSim simulator
  /mcp-portfolio/mcp/, /mcp-marketplace/mcp/, /mcp-workspace/mcp/   the three MCP servers (real MCP over HTTP)
and runs the worker loop as a background task (still never inside a web request).
docker compose runs each of these as its own container instead. Run: python -m apps.api.allinone
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import asyncio
import contextlib
import os

PORT = int(os.getenv("PORT", "7860"))
BASE = f"http://127.0.0.1:{PORT}"
os.environ.setdefault("GIGSIM_BASE_URL", f"{BASE}/gigsim")
os.environ.setdefault("PORTFOLIO_MCP_URL", f"{BASE}/mcp-portfolio/mcp/")
os.environ.setdefault("MARKETPLACE_MCP_URL", f"{BASE}/mcp-marketplace/mcp/")
os.environ.setdefault("WORKSPACE_MCP_URL", f"{BASE}/mcp-workspace/mcp/")
os.environ.setdefault("WORKER_MAX_PARALLEL", "1")

from gigsim.app import app as gigsim_app  # noqa: E402
from mcp_servers.marketplace import server as market  # noqa: E402
from mcp_servers.portfolio import server as portfolio  # noqa: E402
from mcp_servers.workspace import server as workspace  # noqa: E402

for m in (portfolio.mcp, workspace.mcp, market.mcp):
    m.settings.stateless_http = True
portfolio_app = portfolio.mcp.streamable_http_app()
workspace_app = workspace.mcp.streamable_http_app()
market_app = market.http_app()  # bearer-token guarded

from apps.api import main as api  # noqa: E402

_orig_lifespan = api.app.router.lifespan_context


@contextlib.asynccontextmanager
async def lifespan(app):
    async with contextlib.AsyncExitStack() as stack:
        for m in (portfolio.mcp, workspace.mcp, market.mcp):  # mounted apps don't get their own lifespan
            await stack.enter_async_context(m.session_manager.run())
        await stack.enter_async_context(_orig_lifespan(app))
        from worker import main as worker
        task = asyncio.create_task(worker.main())
        try:
            yield
        finally:
            task.cancel()


api.app.router.lifespan_context = lifespan
# mounts must precede the SPA catch-all route
for path, sub in (("/gigsim", gigsim_app), ("/mcp-portfolio", portfolio_app), ("/mcp-workspace", workspace_app),
                  ("/mcp-marketplace", market_app)):
    api.app.mount(path, sub)
    api.app.router.routes.insert(0, api.app.router.routes.pop())
app = api.app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
