"""C2 typed state. Three things are kept apart:
  * State            — what this job/conversation needs right now (fields below)
  * Execution trace  — `trace`: every node/tool call with args, result summary, tokens, cost (audit/debug)
  * Long-term memory — NOT here: only promoted knowledge in the LangGraph store (agent/memory/)
Reducers are used wherever parallel branches (analyst / risk / fit) write."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


def merge_evidence(a: list[dict] | None, b: list[dict] | None) -> list[dict]:
    seen, out = set(), []
    for e in (a or []) + (b or []):
        if e["id"] not in seen:
            seen.add(e["id"])
            out.append(e)
    return out


def add_int(a: int | None, b: int | None) -> int:
    return (a or 0) + (b or 0)


SEVERITY = {"dead_letter": 3, "parked": 2, "needs_attention": 1}


def pick_status(a: str | None, b: str | None) -> str | None:
    """Parallel branches may both set status; the more severe one wins, otherwise the newest."""
    if b is None:
        return a
    return a if SEVERITY.get(a or "", 0) > SEVERITY.get(b, 0) else b


class BidState(TypedDict, total=False):
    # identity
    user_id: str
    owner: str               # portfolio owner (persona id or user id)
    job_id: str
    trace_id: str
    # job + analyses (written in parallel)
    job: dict[str, Any]
    client: dict[str, Any]
    job_spec: dict[str, Any]
    risk_report: dict[str, Any]
    fit_report: dict[str, Any]
    evidence: Annotated[list[dict], merge_evidence]
    # decisions and artefacts
    decision: dict[str, Any]
    price: dict[str, Any]
    draft: dict[str, Any]
    claim_checks: list[dict]
    unsupported_before: float
    unsupported_after: float
    critiques: Annotated[list[dict], operator.add]
    revisions: int
    compliance: dict[str, Any]
    approval: dict[str, Any]
    submission: dict[str, Any]
    prefs: dict[str, Any]    # rate_floor, connects_weekly_budget, connects_spent_this_week, autonomy
    status: Annotated[str, pick_status]  # running|skipped|watch|awaiting_approval|submitted|rejected|needs_attention|dead_letter|parked
    # bookkeeping
    steps: Annotated[int, add_int]
    tokens: Annotated[int, add_int]
    cost_usd: Annotated[float, operator.add]
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict], operator.add]


class ConvState(TypedDict, total=False):
    user_id: str
    owner: str
    thread_id: str
    trace_id: str
    thread: dict[str, Any]
    last_client_message: str
    intent: dict[str, Any]
    slots: list[dict]
    reply: dict[str, Any]
    compliance: dict[str, Any]
    approval: dict[str, Any]
    sent: dict[str, Any]
    status: str
    steps: Annotated[int, add_int]
    tokens: Annotated[int, add_int]
    cost_usd: Annotated[float, operator.add]
    errors: Annotated[list[str], operator.add]
    trace: Annotated[list[dict], operator.add]
