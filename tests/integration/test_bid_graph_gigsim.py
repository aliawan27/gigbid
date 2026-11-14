"""Graph runs against GigSim through the real MCP servers (all-in-one process started on a free port).
Deterministic fallbacks are used (GIGBID_FAKE_LLM=1), so no API keys are needed."""
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

ROOT = Path(__file__).resolve().parents[2]


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    port = _port()
    d = tmp_path_factory.mktemp("stack")
    env = {**os.environ, "PORT": str(port), "PYTHONPATH": str(ROOT), "GIGBID_FAKE_LLM": "1", "GIGSIM_CLIENT_LLM": "0",
           "GIGSIM_ERROR_RATE": "0", "GIGBID_APP_DB": str(d / "app.db"), "GIGBID_SQLITE": str(d / "g.db"),
           "GIGBID_AUDIT_LOG": str(d / "audit.jsonl"), "WORKSPACE_STORE": str(d / "ws.json"), "GIGSIM_STATE": str(d / "gigsim.json"),
           "MARKETPLACE_MCP_TOKEN": "test-token", "GIGSIM_API_TOKEN": "test-gigsim", "WORKER_SYNC_EVERY_S": "100000", "GIGBID_WORKER": "0"}
    for k in ("GIGSIM_BASE_URL", "PORTFOLIO_MCP_URL", "MARKETPLACE_MCP_URL", "WORKSPACE_MCP_URL"):
        env.pop(k, None)
    p = subprocess.Popen([sys.executable, "-m", "apps.api.allinone"], cwd=ROOT, env=env,
                         stdout=open(d / "log.txt", "w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(90):
        try:
            if httpx.get(base + "/gigsim/health", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(1)
    os.environ.update({"PORTFOLIO_MCP_URL": f"{base}/mcp-portfolio/mcp/", "MARKETPLACE_MCP_URL": f"{base}/mcp-marketplace/mcp/",
                       "WORKSPACE_MCP_URL": f"{base}/mcp-workspace/mcp/", "MARKETPLACE_MCP_TOKEN": "test-token"})
    from agent import mcp_client
    mcp_client._tools_cache.clear()
    yield base
    p.terminate()


def _graph():
    from agent.graphs.bid_graph import build_bid_graph
    return build_bid_graph(MemorySaver(), InMemoryStore())


def _inp(job_id, user="it-user"):
    return {"user_id": user, "owner": "ai_ml", "job_id": job_id, "trace_id": "t", "status": "running",
            "prefs": {"rate_floor": 55, "connects_weekly_budget": 120}}


def test_fit_job_reaches_approval_then_submits_exactly_once(stack):
    async def run():
        g = _graph()
        cfg = {"configurable": {"thread_id": "it-1"}}
        await g.ainvoke(_inp("job-0002"), cfg)
        snap = await g.aget_state(cfg)
        assert snap.next == ("human_approval",), snap.values.get("errors")
        payload = snap.tasks[0].interrupts[0].value
        assert payload["draft"]["cover_letter"] and payload["dry_run"]["connects_cost"]
        bal0 = httpx.get(f"{stack}/gigsim/freelancers/it-user/connects", headers={"Authorization": "Bearer test-gigsim"}).json()["balance"]
        await g.ainvoke(Command(resume={"action": "approve"}), cfg)
        st = (await g.aget_state(cfg)).values
        assert st["status"] == "submitted"
        # simulate a crash after submit: re-run the submit step from its checkpoint -> idempotent replay
        from agent.nodes.approval import submit
        again = await submit({**st, "status": "approved"}, store=None)
        assert again["submission"]["result"]["idempotent_replay"] is True
        bal1 = httpx.get(f"{stack}/gigsim/freelancers/it-user/connects", headers={"Authorization": "Bearer test-gigsim"}).json()["balance"]
        assert bal0 - bal1 == st["job"]["connects_cost"]  # Connects spent once
    asyncio.run(run())


def test_scam_job_is_skipped_with_reason(stack):
    async def run():
        g = _graph()
        cfg = {"configurable": {"thread_id": "it-2"}}
        await g.ainvoke(_inp("job-0036"), cfg)  # "Unpaid trial ... WhatsApp"
        st = (await g.aget_state(cfg)).values
        assert st["status"] == "skipped" and st["risk_report"]["scam"]
        assert "scam" in st["decision"]["reason"]
    asyncio.run(run())


def test_reject_records_reason(stack):
    async def run():
        g = _graph()
        cfg = {"configurable": {"thread_id": "it-3"}}
        await g.ainvoke(_inp("job-0004"), cfg)
        await g.ainvoke(Command(resume={"action": "reject", "reason": "not interested"}), cfg)
        st = (await g.aget_state(cfg)).values
        assert st["status"] == "rejected" and st["approval"]["reason"] == "not interested"
    asyncio.run(run())
