"""Bid-or-skip decision node: combines RiskReport + FitReport + JobSpec using thresholds from config.yaml."""
from __future__ import annotations

from agent.config import CONFIG
from agent.handoffs import BidDecision
from agent.nodes._common import node


def floor_price(prefs: dict, complexity: int) -> float:
    return float(prefs.get("rate_floor", 40)) * 10 * max(1, complexity)  # ~10 billable hours per complexity point


def decide_rule(spec: dict, risk: dict, fit: dict, prefs: dict) -> BidDecision:
    t = CONFIG["thresholds"]
    if risk.get("scam") or risk.get("score", 0) >= t["scam_risk_score"]:
        return BidDecision(action="skip", reason=f"likely scam / unsafe (risk {risk.get('score')}: {', '.join(risk.get('flags', []))})")
    if risk.get("score", 0) > t["max_risk_score"]:
        return BidDecision(action="skip", reason=f"risk {risk['score']} above limit {t['max_risk_score']}")
    budget = spec.get("budget") or 0
    floor = floor_price(prefs, spec.get("complexity", 2))
    if budget and budget < t["min_rate_floor_ratio"] * floor:
        return BidDecision(action="skip", reason=f"budget ${budget:.0f} is below your floor (~${floor:.0f} for this scope)")
    f = fit.get("score", 0)
    if f >= t["bid_fit_score"]:
        return BidDecision(action="bid", reason=f"fit {f} >= {t['bid_fit_score']}; risk {risk.get('score')} acceptable")
    if f >= t["watch_fit_score"]:
        return BidDecision(action="watch", reason=f"partial fit {f}; missing {', '.join(fit.get('missing', [])[:3])}")
    return BidDecision(action="skip", reason=f"low fit {f}; missing {', '.join(fit.get('missing', [])[:3])}")


@node("decide")
async def decide(state, store):
    d = decide_rule(state.get("job_spec", {}), state.get("risk_report", {}), state.get("fit_report", {}),
                    state.get("prefs", {}))
    status = {"bid": "running", "watch": "watch", "skip": "skipped"}[d.action]
    return {"decision": d.model_dump(), "status": status, "_summary": f"{d.action}: {d.reason}"}
