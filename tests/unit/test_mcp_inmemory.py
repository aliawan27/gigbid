"""MCP servers exercised through the SDK's in-memory client (no network)."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session as connect

from mcp_servers.portfolio.server import mcp as portfolio
from mcp_servers.workspace.server import mcp as workspace


def _items(result):
    out = []
    for c in result.content:
        v = json.loads(c.text)
        out.extend(v if isinstance(v, list) else [v])
    return out


@pytest.mark.asyncio
async def test_portfolio_tools_resources_prompts():
    async with connect(portfolio._mcp_server) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert {"search_evidence", "get_case_study", "list_skills"} <= names
        items = _items(await c.call_tool("search_evidence", {"requirement": "spaCy NER clinical notes", "k": 3, "owner": "ai_ml"}))
        assert items and {"type", "source", "date"} <= set(items[0])
        assert any("medical-ner" in i["id"] for i in items)
        cs = await c.call_tool("get_case_study", {"id": "ai_ml:cs:medical-ner", "owner": "ai_ml"})
        assert "Clinical" in cs.content[0].text
        res = await c.read_resource("portfolio://case/ai_ml:cs:medical-ner")
        assert "Outcome" in res.contents[0].text
        assert "answer_screening_question" in {p.name for p in (await c.list_prompts()).prompts}


@pytest.mark.asyncio
async def test_workspace_hold_is_idempotent(tmp_path, monkeypatch):
    import mcp_servers.workspace.server as ws
    monkeypatch.setattr(ws, "STORE", tmp_path / "ws.json")
    async with connect(workspace._mcp_server) as c:
        slots = _items(await c.call_tool("free_slots", {"user_id": "u", "days": 5}))
        args = {"user_id": "u", "start": slots[0]["start"], "title": "Interview", "idempotency_key": "hold-12345"}
        a = _items(await c.call_tool("create_tentative_hold", args))[0]
        b = _items(await c.call_tool("create_tentative_hold", args))[0]
        assert a["status"] == "tentative" and b.get("idempotent_replay")
