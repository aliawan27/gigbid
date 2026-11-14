"""Proposal Writer: cover letter + screening answers with evidence citations [E#] (Portfolio MCP), shaped by
promoted style memory and outcome memory."""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent.config import CONFIG, prompt
from agent.handoffs import Citation, ProposalDraft
from agent.llm import LLMUnavailable
from agent.mcp_client import call
from agent.memory.store import outcome_lessons, style_rules
from agent.nodes._common import llm_structured, node, tool_rec
from agent.safety import defended_text, untrusted

TAG = re.compile(r"\[(E\d+)\]")


class WriterOut(BaseModel):
    cover_letter: str
    screening_answers: list[str] = []


def citations_of(letter: str, emap: dict[str, str]) -> list[Citation]:
    out = []
    for s in re.split(r"(?<=[.!?])\s+", letter):
        tags = TAG.findall(s)
        if tags:
            out.append(Citation(sentence=TAG.sub("", s).strip(), evidence_ids=[emap[t] for t in tags if t in emap]))
    return out


def fallback_letter(spec: dict, ev: list[dict]) -> WriterOut:
    reqs = ", ".join(spec.get("requirements", [])[:3])
    lines = [f"Your project needs {reqs}, and I have delivered closely related work."]
    for i, e in enumerate(ev[:2], 1):
        lines.append(f"Relevant example: {e.get('title')} [E{i}].")
    lines.append("I would start by confirming the scope and success metric with you, then share a short plan with milestones.")
    return WriterOut(cover_letter=" ".join(lines),
                     screening_answers=[f"Yes — see {ev[0].get('title')} [E1]." if ev else "Happy to discuss on a call."
                                        for _ in spec.get("screening_questions", [])])


@node("writer")
async def writer(state, store):
    job, spec, uid = state["job"], state["job_spec"], state["user_id"]
    owner = state.get("owner") or uid
    a1 = {"requirement": f"{job['title']}\n{' '.join(spec.get('requirements', []))}", "k": CONFIG["rag"]["k"], "owner": owner}
    extra = await call("writer", "search_evidence", a1)
    ev = []
    for e in (state.get("evidence") or []) + extra:
        if e["id"] not in {x["id"] for x in ev}:
            ev.append(e)
    ev = ev[: CONFIG["rag"]["k"] + 2]
    a2 = {"query": job["title"], "k": 2, "outcome": "won", "owner": owner}
    try:
        exemplars = await call("writer", "search_past_proposals", a2)
    except Exception:  # noqa: BLE001
        exemplars = []
    emap = {f"E{i}": e["id"] for i, e in enumerate(ev, 1)}
    style = await style_rules(store, uid) if store else []
    lessons = await outcome_lessons(store, uid, spec.get("category", "")) if store else None
    clean, _ = defended_text(job["description"])
    feedback = ""
    if state.get("critiques"):
        last = state["critiques"][-1]
        feedback = "\nCRITIC FEEDBACK TO FIX (revision):\n- " + "\n- ".join(last.get("issues", []))
    user = (untrusted("JOB POST", f"{job['title']}\n{clean}") +
            f"\nREQUIREMENTS: {spec.get('requirements')}\nHIDDEN NEEDS: {spec.get('hidden_needs')}\n"
            f"SCREENING QUESTIONS: {spec.get('screening_questions')}\nBID: ${state.get('price', {}).get('amount')}\n"
            "EVIDENCE (cite with the tag):\n" +
            "\n".join(f"[E{i}] ({e['type']}) {e.get('title')}: {e.get('snippet', '')[:350]}" for i, e in enumerate(ev, 1)) +
            "\nPAST WINNING PROPOSALS (phrasing only, do not copy claims):\n" +
            "\n".join(f"- {x.get('snippet', '')[:250]}" for x in exemplars) +
            f"\nUSER STYLE RULES: {style or 'none yet'}" +
            (f"\nWHAT GOT REPLIES IN THIS CATEGORY: {lessons.get('positive_examples')}" if lessons else "") + feedback)
    try:
        out = await llm_structured("writer", prompt("writer"), user, WriterOut, max_tokens=1500)
    except LLMUnavailable:
        out = fallback_letter(spec, ev)
    draft = ProposalDraft(cover_letter=out.cover_letter.strip(), screening_answers=out.screening_answers,
                          citations=citations_of(out.cover_letter, emap), evidence_ids=list(emap.values()),
                          version=(state.get("draft") or {}).get("version", 0) + 1)
    d = draft.model_dump()
    d["evidence_map"] = emap
    return {"draft": d, "evidence": ev, "revisions": state.get("revisions", 0) + (1 if state.get("critiques") else 0),
            "_tools": [tool_rec("search_evidence", a1, [e["id"] for e in extra]),
                       tool_rec("search_past_proposals", a2, len(exemplars))],
            "_summary": f"draft v{draft.version}, {len(draft.cover_letter.split())} words, {len(draft.citations)} cited sentences"}
