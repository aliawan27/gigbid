"""Fit Matcher: maps every requirement to portfolio evidence (Portfolio MCP) and scores fit with reasons."""
from __future__ import annotations

import asyncio

from agent.config import CONFIG
from agent.handoffs import FitReport, RequirementMatch
from agent.mcp_client import call
from agent.nodes._common import node, tool_rec


def covers(req: str, ev: dict) -> bool:
    r = req.lower()
    hay = " ".join([ev.get("snippet") or "", ev.get("title") or "", " ".join(ev.get("skills") or [])]).lower()
    return r in hay or all(t in hay for t in r.split() if len(t) > 2)


@node("fit_matcher")
async def fit_matcher(state, store):
    job = state["job"]
    reqs = list(dict.fromkeys(job.get("skills") or []))[:8] or [job["title"]]
    owner = state.get("owner") or state["user_id"]

    async def one(req):
        args = {"requirement": req, "k": 3, "owner": owner}
        return req, args, await call("fit_matcher", "search_evidence", args)

    results = await asyncio.gather(*[one(r) for r in reqs])
    matches, evidence, tools = [], [], []
    for req, args, evs in results:
        good = [e for e in evs if covers(req, e)]
        matches.append(RequirementMatch(requirement=req, covered=bool(good), evidence_ids=[e["id"] for e in good][:3],
                                        note=good[0]["title"] if good else "no portfolio evidence"))
        evidence += good or evs[:1]
        tools.append(tool_rec("search_evidence", args, [e["id"] for e in evs]))
    covered = sum(m.covered for m in matches)
    score = covered / max(1, len(matches))
    rep = FitReport(score=round(score, 2), matches=matches, missing=[m.requirement for m in matches if not m.covered],
                    reasons=[f"{covered}/{len(matches)} requirements backed by portfolio evidence"])
    return {"fit_report": rep.model_dump(), "evidence": evidence[: CONFIG["rag"]["k"] * 2], "_tools": tools,
            "_summary": f"fit {rep.score} missing={rep.missing}"}
