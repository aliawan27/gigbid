from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import call
from apps.api import db
from apps.api.deps import get_user, graphs, pending_interrupt
from apps.api.schemas.models import ApprovalIn, TaskOut

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("")
async def threads(u: dict = Depends(get_user)):
    try:
        ts = await call("api", "list_messages", {"user_id": u["id"]})
    except MarketplaceUnavailable as e:
        raise HTTPException(503, f"marketplace unavailable: {e}") from e
    g = await graphs()
    convs = db.rows(select(db.convs).where(db.convs.c.user_id == u["id"]))
    out = []
    for t in ts:
        mine = sorted([c for c in convs if c["thread_id"] == t["thread_id"]], key=lambda c: -c["updated_at"])
        pend = None
        if mine and mine[0]["status"] == "awaiting_approval":
            pend = await pending_interrupt(g["conv"], mine[0]["graph_thread"])
        title = (db.one(select(db.jobs.c.title).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == t["job_id"])) or {}).get("title")
        out.append({**t, "job_title": title, "graph_thread": mine[0]["graph_thread"] if mine else None,
                    "agent_status": mine[0]["status"] if mine else None, "pending": pend})
    return out


@router.post("/{thread_id}/draft", response_model=TaskOut)
def draft_reply(thread_id: str, n: int, u: dict = Depends(get_user)):
    tid = db.enqueue(u["id"], "conversation", {"thread_id": thread_id, "n": n}, dedup_key=f"conv:{u['id']}:{thread_id}:{n}")
    return TaskOut(queued=bool(tid), task_id=tid, message="drafting reply")


@router.post("/{thread_id}/decision", response_model=TaskOut)
def decide(thread_id: str, graph_thread: str, d: ApprovalIn, u: dict = Depends(get_user)):
    c = db.one(select(db.convs).where(db.convs.c.user_id == u["id"], db.convs.c.graph_thread == graph_thread))
    if not c or c["status"] != "awaiting_approval":
        raise HTTPException(409, "no pending reply")
    if d.action == "reject" and not (d.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    db.q(db.convs.update().where(db.convs.c.id == c["id"]).values(status="resuming"))
    tid = db.enqueue(u["id"], "resume_conv", {"thread_id": thread_id, "graph_thread": graph_thread, "value": d.model_dump()},
                     dedup_key=f"rconv:{graph_thread}:{time.time()}")
    return TaskOut(queued=bool(tid), task_id=tid, message=f"{d.action} recorded")
