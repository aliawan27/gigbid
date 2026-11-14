"""CI smoke eval (E2): 30 dev jobs through the decision part of the graph + 3 full proposals.
Fails (exit 1) if bid/skip F1 drops below the threshold or unsupported claims rise above it.
Expects a running all-in-one stack (CI starts one) at SMOKE_BASE (default http://127.0.0.1:7860)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from _common import JOBS, PERSONAS, dev, f1, mean, persona_prefs, public_job, write
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agent.graphs.bid_graph import build_bid_graph

THRESHOLDS = {"min_bid_skip_f1": 0.75, "max_unsupported_claim_rate": 0.10}


async def main(n: int):
    base = os.getenv("SMOKE_BASE", "http://127.0.0.1:7860")
    os.environ.update({"PORTFOLIO_MCP_URL": f"{base}/mcp-portfolio/mcp/", "MARKETPLACE_MCP_URL": f"{base}/mcp-marketplace/mcp/",
                       "WORKSPACE_MCP_URL": f"{base}/mcp-workspace/mcp/"})
    g = build_bid_graph(MemorySaver(), InMemoryStore())
    per = max(1, n // len(PERSONAS))
    rows, unsupported = [], []
    for p in PERSONAS:
        for i, gold in enumerate(dev(p)[::max(1, 40 // per)][:per]):
            job = public_job(JOBS[gold["job_id"]])
            cfg = {"configurable": {"thread_id": f"smoke:{job['job_id']}"}}
            full = i == 0
            if not full:
                g.interrupt_before_nodes = ["writer"]
            await g.ainvoke({"user_id": f"smoke-{p}", "owner": p, "job_id": job["job_id"], "job": job, "trace_id": "smoke",
                             "status": "running", "prefs": persona_prefs(p)}, cfg)
            g.interrupt_before_nodes = []
            st = (await g.aget_state(cfg)).values
            rows.append(((st.get("decision") or {}).get("action"), gold["decision"]))
            if st.get("unsupported_after") is not None:
                unsupported.append(st["unsupported_after"])
    tp = sum(a == "bid" and b == "bid" for a, b in rows)
    fp = sum(a == "bid" and b != "bid" for a, b in rows)
    fn = sum(a != "bid" and b == "bid" for a, b in rows)
    res = {"n": len(rows), "bid_skip_f1": round(f1(tp, fp, fn), 3), "unsupported_claim_rate": mean(unsupported) or 0.0,
           "thresholds": THRESHOLDS, "fake_llm": os.getenv("GIGBID_FAKE_LLM") == "1"}
    res["passed"] = res["bid_skip_f1"] >= THRESHOLDS["min_bid_skip_f1"] and res["unsupported_claim_rate"] <= THRESHOLDS["max_unsupported_claim_rate"]
    print(res)
    write("smoke_eval", res)
    sys.exit(0 if res["passed"] else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    asyncio.run(main(ap.parse_args().n))
