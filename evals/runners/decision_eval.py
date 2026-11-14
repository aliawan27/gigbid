"""B4 decisions: bid-or-skip F1, scam precision/recall, price inside the fair band, latency + cost per job analysed.
Runs the real bid graph (scout -> analyst || risk || fit -> decide -> pricing) on every dev job, stopping before the
writer. Run: python evals/runners/decision_eval.py [--limit N]"""
from __future__ import annotations

import argparse
import asyncio
import time

from _common import JOBS, PERSONAS, Stack, dev, f1, mean, pct, persona_prefs, public_job, write
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from agent.graphs.bid_graph import build_bid_graph


async def run_job(g, persona: str, gold: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        job = public_job(JOBS[gold["job_id"]])
        cfg = {"configurable": {"thread_id": f"dec:{persona}:{job['job_id']}"}}
        t0 = time.time()
        await g.ainvoke({"user_id": f"eval-{persona}", "owner": persona, "job_id": job["job_id"], "job": job, "trace_id": "eval",
                         "status": "running", "prefs": persona_prefs(persona)}, cfg)
        st = (await g.aget_state(cfg)).values
        lat = time.time() - t0
    d = (st.get("decision") or {}).get("action", "error")
    price = (st.get("price") or {}).get("amount")
    band = gold["price_band"]
    return {"persona": persona, "job_id": job["job_id"], "kind": gold["kind"], "gold": gold["decision"], "pred": d,
            "gold_scam": gold["scam"], "pred_scam": bool((st.get("risk_report") or {}).get("scam")),
            "risk": (st.get("risk_report") or {}).get("score"), "fit": (st.get("fit_report") or {}).get("score"),
            "reason": (st.get("decision") or {}).get("reason"), "price": price,
            "in_band": (band[0] * 0.9 <= price <= band[1] * 1.1) if price and band[1] else None,
            "latency_s": round(lat, 2), "tokens": st.get("tokens", 0), "usd": st.get("cost_usd", 0.0),
            "status": st.get("status"), "errors": st.get("errors", [])}


def metrics(rows: list[dict]) -> dict:
    tp = sum(r["pred"] == "bid" and r["gold"] == "bid" for r in rows)
    fp = sum(r["pred"] == "bid" and r["gold"] != "bid" for r in rows)
    fn = sum(r["pred"] != "bid" and r["gold"] == "bid" for r in rows)
    stp = sum(r["pred_scam"] and r["gold_scam"] for r in rows)
    sfp = sum(r["pred_scam"] and not r["gold_scam"] for r in rows)
    sfn = sum(not r["pred_scam"] and r["gold_scam"] for r in rows)
    priced = [r for r in rows if r["in_band"] is not None and r["gold"] == "bid"]
    return {"n": len(rows), "bid_skip_f1": round(f1(tp, fp, fn), 3), "accuracy": round(mean(
        [(r["pred"] == "bid") == (r["gold"] == "bid") for r in rows]) or 0, 3),
        "scam_precision": round(stp / (stp + sfp), 3) if stp + sfp else None,
        "scam_recall": round(stp / (stp + sfn), 3) if stp + sfn else None,
        "price_in_fair_band": round(mean([r["in_band"] for r in priced]) or 0, 3) if priced else None,
        "p50_latency_s_per_job": pct([r["latency_s"] for r in rows], 0.5), "p95_latency_s_per_job": pct([r["latency_s"] for r in rows], 0.95),
        "mean_tokens_per_job": mean([r["tokens"] for r in rows]), "mean_usd_per_job": mean([r["usd"] for r in rows]),
        "p95_usd_per_job": pct([r["usd"] for r in rows], 0.95)}


async def main(limit: int | None, kinds: list[str] | None = None, out_name: str = "decisions"):
    with Stack(client_llm=False):
        g = build_bid_graph(MemorySaver(), InMemoryStore())
        g.interrupt_before_nodes = ["writer"]
        sem = asyncio.Semaphore(4)
        tasks = [run_job(g, p, gold, sem) for p in PERSONAS for gold in dev(p)[:limit] if not kinds or gold["kind"] in kinds]
        rows = await asyncio.gather(*tasks)
    out = {"overall": metrics(rows), "by_persona": {p: metrics([r for r in rows if r["persona"] == p]) for p in PERSONAS},
           "by_kind": {k: metrics([r for r in rows if r["kind"] == k]) for k in sorted({r["kind"] for r in rows})},
           "errors": [r for r in rows if r["pred"] != ("bid" if r["gold"] == "bid" else r["pred"]) or r["pred"] == "error"
                      or (r["gold"] == "bid") != (r["pred"] == "bid")],
           "rows": rows}
    print(out["overall"])
    write(out_name, out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--kinds", help="comma-separated job kinds, e.g. inject,scam")
    ap.add_argument("--out", default="decisions")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.kinds.split(",") if a.kinds else None, a.out))
