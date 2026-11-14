from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from agent.llm import LLMUnavailable
from apps.api import db
from apps.api.deps import get_user, graphs, pending_interrupt
from apps.api.schemas.models import ApprovalIn, JobDetail, JobRow, RegenerateIn, TaskOut

router = APIRouter(prefix="/api", tags=["jobs"])


def _row(r: dict) -> JobRow:
    s = r.get("summary") or {}
    return JobRow(job_id=r["job_id"], title=r["title"] or r["job_id"], status=r["status"], thread_id=r.get("thread_id"),
                  fit=s.get("fit"), risk=s.get("risk"), scam=s.get("scam"), flags=s.get("flags") or [],
                  action=s.get("action"), reason=s.get("reason"), price=s.get("price"),
                  connects_cost=s.get("connects_cost"), budget=s.get("budget"), marketplace_status=s.get("marketplace_status"),
                  updated_at=r.get("updated_at"))


@router.get("/jobs", response_model=list[JobRow])
def inbox(status: str = "", u: dict = Depends(get_user)):
    rows = db.rows(select(db.jobs).where(db.jobs.c.user_id == u["id"]))
    out = [_row(r) for r in rows if not status or r["status"] == status]
    order = {"awaiting_approval": 0, "bid": 1}
    return sorted(out, key=lambda j: (order.get(j.status, order.get(j.action or "", 2)), -(j.fit or 0), -(j.updated_at or 0)))


@router.post("/jobs/scout", response_model=TaskOut)
def scout_now(u: dict = Depends(get_user)):
    tid = db.enqueue(u["id"], "scout", {}, dedup_key=f"scout:{u['id']}:manual:{int(time.time() // 30)}")
    return TaskOut(queued=bool(tid), task_id=tid, message="scouting saved searches")


@router.post("/jobs/{job_id}/analyse", response_model=TaskOut)
def analyse(job_id: str, u: dict = Depends(get_user)):
    row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == job_id))
    attempt = int(time.time()) % 100000 if row and row["status"] in ("parked", "dead_letter", "skipped", "watch", "rejected") else 0
    db.upsert_job(u["id"], job_id, title=(row or {}).get("title") or job_id, status="queued")
    tid = db.enqueue(u["id"], "bid", {"job_id": job_id, "attempt": attempt}, dedup_key=f"bid:{u['id']}:{job_id}:{attempt}")
    return TaskOut(queued=bool(tid), task_id=tid, message="queued for analysis")


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, u: dict = Depends(get_user)):
    row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == job_id))
    if not row:
        raise HTTPException(404, "job not in your inbox")
    g = await graphs()
    st, pend = {}, None
    if row.get("thread_id"):
        snap = await g["bid"].aget_state({"configurable": {"thread_id": row["thread_id"]}})
        st = {k: v for k, v in (snap.values or {}).items() if k not in ("trace",)}
        pend = await pending_interrupt(g["bid"], row["thread_id"])
    return JobDetail(job=st.get("job") or {"job_id": job_id, "title": row["title"]}, status=row["status"],
                     thread_id=row.get("thread_id"), state=st, pending_approval=pend)


@router.get("/jobs/{job_id}/trace")
async def job_trace(job_id: str, u: dict = Depends(get_user)):
    row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == job_id))
    if not row or not row.get("thread_id"):
        raise HTTPException(404, "no trace")
    g = await graphs()
    cfg = {"configurable": {"thread_id": row["thread_id"]}}
    snap = await g["bid"].aget_state(cfg)
    history = [{"step": h.metadata.get("step"), "next": list(h.next), "checkpoint_id": h.config["configurable"]["checkpoint_id"]}
               async for h in g["bid"].aget_state_history(cfg)]
    return {"trace": snap.values.get("trace", []), "errors": snap.values.get("errors", []), "checkpoints": history,
            "tokens": snap.values.get("tokens"), "cost_usd": snap.values.get("cost_usd")}


@router.get("/approvals")
async def approvals(u: dict = Depends(get_user)):
    """Pending approvals are read from interrupted graph threads, so a refresh never loses one."""
    g = await graphs()
    out = []
    for r in db.rows(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.status == "awaiting_approval")):
        p = await pending_interrupt(g["bid"], r["thread_id"])
        if p:
            out.append({"kind": "proposal", "job_id": r["job_id"], "title": r["title"]})
    for c in db.rows(select(db.convs).where(db.convs.c.user_id == u["id"], db.convs.c.status == "awaiting_approval")):
        out.append({"kind": "message", "thread_id": c["thread_id"], "graph_thread": c["graph_thread"]})
    return out


@router.post("/proposals/{job_id}/decision", response_model=TaskOut)
async def decide(job_id: str, d: ApprovalIn, u: dict = Depends(get_user)):
    row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == job_id))
    if not row or row["status"] != "awaiting_approval":
        raise HTTPException(409, "no pending approval for this job")
    if d.action == "reject" and not (d.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    if d.action == "edit" and not (d.edited_text or "").strip():
        raise HTTPException(422, "edited_text required")
    db.upsert_job(u["id"], job_id, status="resuming")
    tid = db.enqueue(u["id"], "resume_bid", {"job_id": job_id, "thread_id": row["thread_id"], "value": d.model_dump()},
                     dedup_key=f"resume:{row['thread_id']}:{time.time()}")
    return TaskOut(queued=bool(tid), task_id=tid, message=f"{d.action} recorded; graph resuming")


@router.post("/proposals/{job_id}/regenerate")
async def regenerate(job_id: str, r: RegenerateIn, u: dict = Depends(get_user)):
    """Regenerate one paragraph of the pending draft (the result goes back through approval as an edit)."""
    import asyncio

    from agent.config import model_for
    from agent.llm import chat
    from agent.safety import untrusted
    g = await graphs()
    row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == job_id))
    p = await pending_interrupt(g["bid"], row["thread_id"]) if row else None
    if not p:
        raise HTTPException(409, "no pending draft")
    paras = [x for x in p["draft"]["cover_letter"].split("\n\n")]
    if not 0 <= r.paragraph_index < len(paras):
        raise HTTPException(400, "bad paragraph index")
    ev = "\n".join(f"[{k}] {v}" for k, v in (p["draft"].get("evidence_map") or {}).items())
    msg = [{"role": "system", "content": "Rewrite ONE paragraph of a freelance proposal. Keep every [E#] citation that "
            "supports a claim; never add claims without a citation from the evidence list. Return only the paragraph."},
           {"role": "user", "content": f"{untrusted('JOB', p['title'])}\nEVIDENCE: {ev}\nPARAGRAPH: {paras[r.paragraph_index]}\n"
            f"INSTRUCTION: {r.instruction or 'make it more specific and concise'}"}]
    try:
        out = await asyncio.to_thread(chat, model_for("writer"), msg, node="regenerate", max_tokens=500)
    except LLMUnavailable as e:
        raise HTTPException(503, f"model unavailable: {e}") from e
    paras[r.paragraph_index] = out["content"].strip()
    return {"cover_letter": "\n\n".join(paras)}
