"""Human-in-the-loop (C5): dry-run preview -> interrupt() for approve / edit / reject -> exactly-once submit."""
from __future__ import annotations

import hashlib
import re

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision
from agent.mcp_client import call
from agent.memory.store import record_edit
from agent.nodes._common import node, tool_rec

TAG = re.compile(r"\s?\[E\d+\]")


def clean_letter(text: str) -> str:
    return TAG.sub("", text).strip()


def idem_key(state: dict, kind: str = "submit") -> str:
    """Deterministic key: a resumed/retried submit after a crash reuses it, so GigSim applies it once."""
    d = state.get("draft") or {}
    h = hashlib.sha1(clean_letter(d.get("cover_letter", "")).encode()).hexdigest()[:10]
    return f"{state['user_id']}:{state['job_id']}:{kind}:{h}"


def _proposal(state: dict, dry_run: bool) -> dict:
    d = state["draft"]
    return {"p": {"user_id": state["user_id"], "job_id": state["job_id"], "cover_letter": clean_letter(d["cover_letter"]),
                  "screening_answers": [clean_letter(a) for a in d.get("screening_answers", [])],
                  "bid_amount": state["price"]["amount"], "idempotency_key": idem_key(state), "dry_run": dry_run,
                  "trace_id": state.get("trace_id", "")}}


@node("preview")
async def preview(state, store):
    args = _proposal(state, dry_run=True)
    res = await call("submitter", "create_proposal_draft", args)
    return {"submission": {"preview": res}, "status": "awaiting_approval", "_tools": [tool_rec("create_proposal_draft", args, res)],
            "_summary": f"dry-run: {res.get('connects_cost')} Connects, balance after {res.get('connects_balance_after')}"}


@node("approval")
async def approval(state, store):
    payload = {"kind": "proposal", "job_id": state["job_id"], "title": state["job"]["title"], "draft": state["draft"],
               "evidence": state.get("evidence"), "claim_checks": state.get("claim_checks"),
               "unsupported_before": state.get("unsupported_before"), "unsupported_after": state.get("unsupported_after"),
               "risk_report": state.get("risk_report"), "fit_report": state.get("fit_report"),
               "price": state.get("price"), "compliance": state.get("compliance"),
               "critiques": state.get("critiques"), "dry_run": (state.get("submission") or {}).get("preview")}
    decision = ApprovalDecision(**interrupt(payload))
    if decision.action == "reject":
        return {"approval": decision.model_dump(), "status": "rejected", "_summary": f"rejected: {decision.reason}"}
    if decision.action == "edit":
        original = state["draft"]["cover_letter"]
        edited = decision.edited_text or original
        promoted = await record_edit(store, state["user_id"], clean_letter(original), clean_letter(edited)) if store else []
        d = dict(state["draft"])
        d["cover_letter"], d["edited_by_user"] = edited, True
        return {"approval": {**decision.model_dump(), "promoted_style_rules": promoted}, "draft": d,
                "status": "running", "_summary": f"edited by user; style rules promoted: {promoted}"}
    return {"approval": decision.model_dump(), "status": "approved", "_summary": "approved by user"}


@node("submit")
async def submit(state, store):
    args = _proposal(state, dry_run=False)
    res = await call("submitter", "submit_proposal", args)
    return {"submission": {**(state.get("submission") or {}), "result": res, "idempotency_key": args["p"]["idempotency_key"]},
            "status": "submitted", "_tools": [tool_rec("submit_proposal", args, res)],
            "_summary": f"submitted ({res.get('status')}); replay={res.get('idempotent_replay')}"}
