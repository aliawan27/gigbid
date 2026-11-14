"""Failure-analysis fix check for mispricing: recompute the (deterministic) PriceQuote with complexity estimated from the
number of listed requirements instead of the analyst LLM's estimate. No new LLM calls."""
from __future__ import annotations

import json

from _common import JOBS, RESULTS, ROOT, persona_prefs

from agent.nodes.pricing import quote
from agent.nodes.risk_assessor import client_quality

d = json.loads((RESULTS / "decisions.json").read_text())
market = json.loads((ROOT / "gigsim" / "seed" / "market_stats.json").read_text())["by_category_complexity"]
clients = {c["client_id"]: c for c in json.loads((ROOT / "gigsim" / "seed" / "clients.json").read_text())}
dev = {g["job_id"]: g for p in ("ai_ml", "fullstack", "data_analyst")
       for g in json.loads((ROOT / "evals" / "datasets" / f"dev_{p}.json").read_text())}
base_ok = new_ok = n = 0
above_b = above_n = 0
for r in d["rows"]:
    if r["gold"] != "bid" or not r["price"]:
        continue
    j, band = JOBS[r["job_id"]], dev[r["job_id"]]["price_band"]
    cx = max(1, min(5, len(j["skills"]) - 1))
    q = quote({"category": j["category"], "complexity": cx, "budget": j["budget"]},
              {"client_quality": client_quality({k: v for k, v in clients[j["client_id"]].items() if not k.startswith("_")})},
              {"score": r["fit"]}, market[f"{j['category']}:{cx}"], 10**6, j["connects_cost"], persona_prefs(r["persona"]))
    inb = lambda p: band[0] * 0.9 <= p <= band[1] * 1.1  # noqa: E731
    n += 1
    base_ok += inb(r["price"])
    new_ok += inb(q.amount)
    above_b += r["price"] > band[1] * 1.1
    above_n += q.amount > band[1] * 1.1
res = {"n": n, "llm_complexity_in_band": round(base_ok / n, 3), "requirement_count_complexity_in_band": round(new_ok / n, 3),
       "above_band_before": above_b, "above_band_after": above_n}
print(res)
d["fix_tried_pricing_complexity"] = res
(RESULTS / "decisions.json").write_text(json.dumps(d, indent=1, default=str))
