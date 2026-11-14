"""Run one job through the bid graph from the CLI (debug helper): python scripts/run_one.py job-0001 ai_ml"""
import asyncio
import json
import sys
import uuid

from agent.graphs.bid_graph import build_bid_graph
from agent.persistence import open_persistence


async def main(job_id: str, owner: str):
    saver, store = await open_persistence()
    g = build_bid_graph(saver, store)
    cfg = {"configurable": {"thread_id": f"cli:{job_id}:{uuid.uuid4().hex[:6]}"}}
    inp = {"user_id": owner, "owner": owner, "job_id": job_id, "trace_id": uuid.uuid4().hex,
           "prefs": json.load(open(f"data/personas/{owner}/persona.json")) | {"connects_weekly_budget": 120}}
    inp["prefs"]["rate_floor"] = inp["prefs"].pop("rate_floor", 40)
    async for mode, ev in g.astream(inp, cfg, stream_mode=["custom"]):
        if ev.get("phase") == "end":
            print(f"  {ev['node']:<14} {ev['latency_s']:>6}s tok={ev['tokens']:<5} {ev['summary'][:110]}")
    st = (await g.aget_state(cfg)).values
    print("STATUS", st.get("status"), "| next:", (await g.aget_state(cfg)).next)
    if st.get("draft"):
        print(st["draft"]["cover_letter"].encode("ascii", "replace").decode())
    print("tokens", st.get("tokens"), "usd", round(st.get("cost_usd", 0), 5), "errors", st.get("errors"))

asyncio.run(main(sys.argv[1], sys.argv[2]))
