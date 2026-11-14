"""Critic: grounding, personalisation and length; sends the draft back to the Writer at most twice (C4)."""
from __future__ import annotations

import re

from agent.config import prompt
from agent.handoffs import Critique
from agent.llm import LLMUnavailable
from agent.nodes._common import llm_structured, node
from agent.safety import untrusted

GENERIC = re.compile(r"^(dear|hello sir|i am a|i'm a)|passionate|hardworking|hard-working", re.I)


def rule_critique(letter: str, spec: dict) -> Critique:
    issues = []
    n = len(letter.split())
    if n > 230:
        issues.append(f"too long ({n} words); cut to under 200")
    if n < 60:
        issues.append(f"too short ({n} words)")
    if GENERIC.search(letter):
        issues.append("generic opening/filler words; open with the client's problem")
    if not re.search(r"\[E\d+\]", letter):
        issues.append("no evidence citations")
    reqs = [r for r in spec.get("requirements", []) if r.lower() in letter.lower()]
    if spec.get("requirements") and not reqs:
        issues.append("does not mention any of the client's requirements")
    return Critique(approve=not issues, issues=issues, grounding=4 if "no evidence citations" not in issues else 1,
                    personalisation=4 if reqs else 2, length_ok=60 <= n <= 230)


@node("critic")
async def critic(state, store):
    d, spec = state["draft"], state["job_spec"]
    rc = rule_critique(d["cover_letter"], spec)
    ev = "\n".join(f"[{k}] {v}" for k, v in (d.get("evidence_map") or {}).items())
    user = (untrusted("JOB POST", f"{state['job']['title']}\n{state['job']['description'][:1000]}") +
            f"\nREQUIREMENTS: {spec.get('requirements')}\nEVIDENCE IDS:\n{ev}\nDRAFT:\n{d['cover_letter']}\n"
            f"SCREENING ANSWERS: {d.get('screening_answers')}")
    try:
        c = await llm_structured("critic", prompt("critic"), user, Critique, max_tokens=700)
        if rc.issues:  # hard rule failures always count
            c = c.model_copy(update={"approve": False, "issues": list(dict.fromkeys(rc.issues + c.issues))})
    except LLMUnavailable:
        c = rc
    return {"critiques": [c.model_dump()],
            "_summary": ("approved" if c.approve else f"revise: {'; '.join(c.issues)[:200]}")}
