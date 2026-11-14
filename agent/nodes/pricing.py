"""Pricing Strategist: market statistics + client spend + the user's floor -> PriceQuote; decides whether the
Connects cost is worth it."""
from __future__ import annotations

from agent.config import CONFIG
from agent.handoffs import PriceQuote
from agent.mcp_client import call
from agent.nodes._common import node, tool_rec
from agent.nodes.decision import floor_price


def quote(spec: dict, risk: dict, fit: dict, market: dict, balance: int, cost: int, prefs: dict) -> PriceQuote:
    p25, med, p75 = market.get("p25", 0), market.get("median", 0), market.get("p75", 0)
    cq, f = risk.get("client_quality", 0.5), fit.get("score", 0.5)
    amount = med * (0.9 + 0.2 * cq) * (0.9 + 0.2 * f)
    floor = floor_price(prefs, spec.get("complexity", 2))
    amount = max(amount, p25, floor * 0.9)
    budget = spec.get("budget") or 0
    if budget:
        amount = min(amount, max(budget * 1.1, p25))
    amount = round(min(amount, p75 * 1.15) / 10) * 10
    weekly = prefs.get("connects_weekly_budget", 120)
    spent = prefs.get("connects_spent_this_week", 0)
    worth = balance >= cost and spent + cost <= weekly and f >= CONFIG["thresholds"]["bid_fit_score"]
    why = (f"Market p25/median/p75 ${p25:.0f}/${med:.0f}/${p75:.0f} for {spec.get('category')} complexity "
           f"{spec.get('complexity')}; client quality {cq}, fit {f}; your floor ~${floor:.0f}; client budget ${budget:.0f}. "
           f"Connects: {cost} of {balance} available ({spent}/{weekly} used this week) -> "
           f"{'worth it' if worth else 'NOT worth it'}.")
    return PriceQuote(amount=float(amount), market={"p25": p25, "median": med, "p75": p75}, connects_cost=cost,
                      connects_balance=balance, connects_worth_it=worth, rationale=why)


@node("pricing")
async def pricing(state, store):
    spec, uid = state["job_spec"], state["user_id"]
    a1 = {"user_id": uid, "category": spec.get("category") or state["job"].get("category"),
          "complexity": spec.get("complexity", 2), "trace_id": state.get("trace_id", "")}
    market = await call("pricing", "get_market_stats", a1)
    a2 = {"user_id": uid, "trace_id": state.get("trace_id", "")}
    bal = await call("pricing", "get_connects_balance", a2)
    q = quote(spec, state.get("risk_report", {}), state.get("fit_report", {}), market, bal.get("balance", 0),
              state["job"].get("connects_cost", 0), state.get("prefs", {}))
    out = {"price": q.model_dump(), "_tools": [tool_rec("get_market_stats", a1, market), tool_rec("get_connects_balance", a2, bal)],
           "_summary": f"${q.amount:.0f}, connects worth it: {q.connects_worth_it}"}
    if not q.connects_worth_it:
        out["status"] = "skipped"
        out["decision"] = {"action": "skip", "reason": "Connects cost not worth it / weekly Connects budget exhausted", "auto": True}
    return out
