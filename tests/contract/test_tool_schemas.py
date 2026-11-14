"""Schema snapshot: fails CI when an MCP tool signature changes unintentionally.
Update intentionally with: UPDATE_SNAPSHOTS=1 pytest tests/contract"""
import json
import os
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.marketplace.server import mcp as marketplace
from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace

SNAP = Path(__file__).parent / "snapshots"


async def _schema(server):
    async with connect(server._mcp_server) as c:
        tools = (await c.list_tools()).tools
        return {t.name: {"input": t.inputSchema, "annotations": t.annotations.model_dump() if t.annotations else None}
                for t in sorted(tools, key=lambda t: t.name)}


@pytest.mark.asyncio
@pytest.mark.parametrize("name,server", [("portfolio", portfolio), ("marketplace", marketplace), ("workspace", workspace)])
async def test_tool_schema_snapshot(name, server):
    cur = json.loads(json.dumps(await _schema(server)))
    f = SNAP / f"{name}.json"
    if os.getenv("UPDATE_SNAPSHOTS") or not f.exists():
        SNAP.mkdir(exist_ok=True)
        f.write_text(json.dumps(cur, indent=1, sort_keys=True))
    assert json.loads(f.read_text()) == cur, f"{name} tool schema changed; run UPDATE_SNAPSHOTS=1 if intended"


@pytest.mark.asyncio
async def test_write_tools_have_idempotency_and_dry_run():
    s = await _schema(marketplace)
    for t in ("create_proposal_draft", "submit_proposal", "send_message"):
        body = json.dumps(s[t]["input"])
        assert "idempotency_key" in body and "dry_run" in body
        assert s[t]["annotations"]["readOnlyHint"] is False
    assert s["search_jobs"]["annotations"]["readOnlyHint"] is True
    assert s["submit_proposal"]["annotations"]["destructiveHint"] is True
