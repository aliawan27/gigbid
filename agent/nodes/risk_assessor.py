"""Risk Assessor: client quality from history + scam / free-work / off-platform / injection flags."""
from __future__ import annotations

import re

from agent.config import prompt
from agent.handoffs import RiskReport
from agent.llm import LLMUnavailable
from agent.mcp_client import call
from agent.nodes._common import llm_structured, node, tool_rec
from agent.safety import defended_text, detect_injection, untrusted

RULES = [
    (re.compile(r"telegram|whatsapp|signal app|skype|outside (the )?platform|off[- ]platform|contact me (on|at|via)", re.I),
     0.55, "off_platform_contact"),
    (re.compile(r"crypto|bitcoin|usdt|send (you )?a check|deposit it|transfer the balance|western union", re.I),
     0.6, "off_platform_payment"),
    (re.compile(r"unpaid|for free|free (test|trial|sample)|without pay", re.I), 0.45, "free_work_request"),
    (re.compile(r"(your|send me your) (email|phone|bank|id card|passport)", re.I), 0.4, "personal_data_request"),
]


def rule_score(job: dict, client: dict) -> tuple[float, list[str]]:
    # rules run on the injection-stripped text: an injected "include your WhatsApp" is an attack on us, not a client
    # asking to move off-platform (failure analysis: 4/9 injected jobs were skipped as scams)
    text = f"{job['title']} {defended_text(job['description'])[0]}"
    score, flags = 0.0, []
    for rx, w, flag in RULES:
        if rx.search(text):
            score += w
            flags.append(flag)
    if not job.get("budget"):
        score += 0.25
        flags.append("no_budget")
    if client and not client.get("payment_verified") and not client.get("total_spent"):
        score += 0.25
        flags.append("unverified_new_client")
    return min(1.0, score), flags


def client_quality(c: dict) -> float:
    if not c:
        return 0.3
    q = 0.2 + 0.3 * bool(c.get("payment_verified")) + min(0.3, (c.get("total_spent") or 0) / 30000)
    q += 0.2 * (((c.get("avg_rating_given") or 3) - 3) / 2)
    return round(max(0.0, min(1.0, q)), 2)


@node("risk_assessor")
async def risk_assessor(state, store):
    job = state["job"]
    args = {"user_id": state["user_id"], "client_id": job["client_id"], "trace_id": state.get("trace_id", "")}
    client = await call("risk_assessor", "get_client_history", args)
    rs, flags = rule_score(job, client)
    inj = detect_injection(job["description"])
    if inj:
        flags.append("prompt_injection")
    cq = client_quality(client)
    user = untrusted("JOB POST", f"{job['title']}\n{job['description']}") + "\n" + untrusted("CLIENT HISTORY", str(client))
    try:
        r = await llm_structured("risk_assessor", prompt("risk_assessor"), user, RiskReport, max_tokens=700)
        score = max(rs, r.score if (r.scam or r.score > 0.5) else min(r.score, rs + 0.2))
        flags = list(dict.fromkeys(flags + r.flags))[:8]
        expl = r.explanation
        scam = (r.scam and score >= 0.6) or rs >= 0.8
    except LLMUnavailable:
        score, expl, scam = rs, "rule-based assessment (LLM unavailable)", rs >= 0.8
    rep = RiskReport(score=round(score, 2), scam=scam, flags=flags, injection_hits=inj, client_quality=cq,
                     explanation=expl)
    return {"risk_report": rep.model_dump(), "client": client,
            "_tools": [tool_rec("get_client_history", args, client.get("name"))],
            "_summary": f"risk {rep.score} scam={rep.scam} flags={flags}"}
