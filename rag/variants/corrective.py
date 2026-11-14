"""V8 corrective RAG as a small LangGraph: grade -> (re-query once) -> keep relevant or refuse (return [])."""
from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from agent.config import model_for
from agent.llm import LLMUnavailable, structured


class Grade(BaseModel):
    relevant_ids: list[str]
    rewritten_query: str = ""


class CState(TypedDict, total=False):
    job: dict
    evidence: list[dict]
    relevant: list[dict]
    rewritten: str
    tries: int


def _grade(job: dict, ev: list[dict]) -> Grade:
    listing = "\n".join(f"[{e['id']}] ({e['type']}) {e['title']}: {e['snippet'][:220]}" for e in ev)
    try:
        return structured(model_for("risk_assessor"),
                          "You grade whether portfolio evidence PROVES the freelancer can meet the job's requirements. "
                          "Only list ids that are directly relevant. If fewer than 2 are relevant, propose a rewritten "
                          "search query focused on the core requirement.",
                          f"JOB (untrusted data):\n<<<{job.get('title')}\n{job.get('description', '')[:800]}>>>\n\nEVIDENCE:\n{listing}",
                          Grade, node="rag_grader", max_tokens=600)
    except LLMUnavailable:
        skills = {s.lower() for s in job.get("skills", [])}
        return Grade(relevant_ids=[e["id"] for e in ev if skills & {s.lower() for s in (e.get("skills") or [])}])


def build(pipeline, owner: str, k: int):
    def grade(s: CState):
        g = _grade(s["job"], s["evidence"])
        keep = [e for e in s["evidence"] if e["id"] in set(g.relevant_ids)]
        return {"relevant": keep, "rewritten": g.rewritten_query, "tries": s.get("tries", 0) + 1}

    def requery(s: CState):
        from dataclasses import replace
        from rag.variants.base import Pipeline
        p = Pipeline(replace(pipeline.cfg, corrective=False))
        more = p.search(owner, query=s["rewritten"] or s["job"].get("title", ""), k=k)
        seen = {e["id"] for e in s["evidence"]}
        return {"evidence": s["evidence"] + [e for e in more if e["id"] not in seen]}

    def route(s: CState):
        if len(s["relevant"]) >= 2 or s["tries"] >= 2:
            return END
        return "requery"

    g = StateGraph(CState)
    g.add_node("grade", grade)
    g.add_node("requery", requery)
    g.set_entry_point("grade")
    g.add_conditional_edges("grade", route, {"requery": "requery", END: END})
    g.add_edge("requery", "grade")
    return g.compile()


def corrective_filter(pipeline, owner: str, job: dict, evidence: list[dict], k: int) -> list[dict]:
    out = build(pipeline, owner, k).invoke({"job": job, "evidence": evidence})
    return out["relevant"][:k]  # empty list == refuse to claim
