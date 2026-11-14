"""Job Analyst: job post -> JobSpec (no MCP access)."""
from __future__ import annotations

from agent.config import prompt
from agent.handoffs import JobSpec
from agent.llm import LLMUnavailable
from agent.nodes._common import llm_structured, node
from agent.safety import defended_text, untrusted


def fallback_spec(job: dict) -> JobSpec:
    skills = job.get("skills", [])
    return JobSpec(job_id=job["job_id"], title=job["title"], category=job.get("category", ""), requirements=skills,
                   deliverables=[], budget=job.get("budget"), timeline_weeks=job.get("duration_weeks"),
                   screening_questions=job.get("screening_questions", []),
                   complexity=min(5, max(1, len(skills) - 1)), vague=len(job.get("description", "")) < 160)


@node("analyst")
async def analyst(state, store):
    job = state["job"]
    clean, _ = defended_text(job["description"])
    user = untrusted("JOB POST", f"TITLE: {job['title']}\nSKILLS LISTED: {', '.join(job.get('skills', []))}\n"
                     f"BUDGET: ${job.get('budget')}\nDURATION: {job.get('duration_weeks')} weeks\n{clean}")
    base = fallback_spec(job)
    try:
        spec = await llm_structured("analyst", prompt("analyst"), user, JobSpec, max_tokens=900)
        reqs = list(dict.fromkeys(job.get("skills", []) + [r for r in spec.requirements if len(r) < 40]))[:10]
        spec = spec.model_copy(update={"job_id": job["job_id"], "title": job["title"], "category": job.get("category", ""),
                                       "budget": job.get("budget"), "requirements": reqs,
                                       "screening_questions": base.screening_questions,
                                       "complexity": max(1, min(5, spec.complexity))})
    except LLMUnavailable:
        spec = base
    return {"job_spec": spec.model_dump(), "_summary": f"{len(spec.requirements)} requirements, complexity {spec.complexity}"}
