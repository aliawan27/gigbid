"""Graph execution used by the worker: start/resume bid and conversation threads, stream node events into
run_events (the API relays them over SSE), keep the job index and run costs current."""
from __future__ import annotations

import json
import os
import time
import uuid

from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph
from agent.persistence import open_persistence
from apps.api import db

_graphs: dict = {}


async def graphs():
    if not _graphs:
        saver, store = await open_persistence()
        _graphs["bid"] = build_bid_graph(saver, store)
        _graphs["conv"] = build_conversation_graph(saver, store)
        _graphs["store"] = store
    return _graphs


def job_summary(st: dict) -> dict:
    r, f, d, p = st.get("risk_report") or {}, st.get("fit_report") or {}, st.get("decision") or {}, st.get("price") or {}
    job = st.get("job") or {}
    return {"fit": f.get("score"), "risk": r.get("score"), "scam": r.get("scam"), "flags": r.get("flags", []),
            "action": d.get("action"), "reason": d.get("reason"), "price": p.get("amount"),
            "connects_cost": job.get("connects_cost"), "budget": job.get("budget"),
            "unsupported_before": st.get("unsupported_before"), "unsupported_after": st.get("unsupported_after"),
            "revisions": st.get("revisions", 0), "errors": st.get("errors", [])[-3:], "tokens": st.get("tokens"),
            "cost_usd": st.get("cost_usd"), "category": job.get("category")}


def langsmith_url(run_id: str) -> str | None:
    if not os.getenv("LANGSMITH_API_KEY"):
        return None
    try:
        from langsmith import Client
        return Client().read_run(run_id).url
    except Exception:  # noqa: BLE001
        return None


async def _execute(kind: str, graph, inp, thread_id: str, user_id: str, ref_id: str, run_id: str, trace_id: str):
    now = time.time()
    db.q(db.runs.insert().values(id=run_id, user_id=user_id, kind=kind, thread_id=thread_id, ref_id=ref_id,
                                 status="running", trace_id=trace_id, created_at=now, updated_at=now))
    cfg = {"configurable": {"thread_id": thread_id}, "run_id": uuid.UUID(trace_id), "run_name": f"gigbid-{kind}",
           "metadata": {"user_id": user_id, "ref_id": ref_id, "trace_id": trace_id}, "tags": [kind]}
    db.add_event(run_id, {"phase": "run_start", "kind": kind, "thread_id": thread_id})
    t0 = time.time()
    async for mode, ev in graph.astream(inp, cfg, stream_mode=["custom", "updates"]):
        if mode == "custom":
            db.add_event(run_id, ev)
        elif mode == "updates" and "__interrupt__" in ev:
            db.add_event(run_id, {"phase": "interrupt", "node": "human_approval"})
    snap = await graph.aget_state(cfg)
    st = snap.values
    status = st.get("status") or "done"
    if snap.next and any(t.interrupts for t in snap.tasks):
        status = "awaiting_approval"
    db.q(db.runs.update().where(db.runs.c.id == run_id).values(
        status=status, updated_at=time.time(), tokens=st.get("tokens"), cost_usd=st.get("cost_usd"),
        latency_s=round(time.time() - t0, 2)))
    db.add_event(run_id, {"phase": "run_end", "status": status})
    return st, status


async def start_bid(user: dict, job_id: str, attempt: int = 0, job: dict | None = None) -> str:
    g = (await graphs())["bid"]
    thread_id = f"{user['id']}:{job_id}" + (f":r{attempt}" if attempt else "")
    run_id, trace_id = uuid.uuid4().hex[:12], str(uuid.uuid4())
    prefs = user.get("prefs") or {}
    inp = {"user_id": user["id"], "owner": user.get("owner") or user["id"], "job_id": job_id, "trace_id": trace_id,
           "prefs": prefs, "status": "running"}
    if job:
        inp["job"] = job
    db.upsert_job(user["id"], job_id, thread_id=thread_id, title=(job or {}).get("title", job_id), status="analysing")
    st, status = await _execute("bid", g, inp, thread_id, user["id"], job_id, run_id, trace_id)
    db.upsert_job(user["id"], job_id, title=(st.get("job") or {}).get("title", job_id), status=status,
                  summary=job_summary(st) | {"run_id": run_id, "trace_id": trace_id})
    return run_id


async def resume_bid(user: dict, job_id: str, thread_id: str, value: dict) -> str:
    g = (await graphs())["bid"]
    cfg = {"configurable": {"thread_id": thread_id}}
    snap = await g.aget_state(cfg)
    pending = snap.next and any(t.interrupts for t in snap.tasks)
    # crash-safe: if the approval was already recorded, just continue (submit uses a deterministic idempotency key)
    inp = Command(resume=value) if pending else None
    run_id, trace_id = uuid.uuid4().hex[:12], str(uuid.uuid4())
    st, status = await _execute("bid_resume", g, inp, thread_id, user["id"], job_id, run_id, trace_id)
    db.upsert_job(user["id"], job_id, status=status, summary=job_summary(st) | {"run_id": run_id, "trace_id": trace_id})
    return run_id


async def start_conv(user: dict, thread: str, n_messages: int) -> str:
    g = (await graphs())["conv"]
    gthread = f"{user['id']}:conv:{thread}:{n_messages}"
    run_id, trace_id = uuid.uuid4().hex[:12], str(uuid.uuid4())
    inp = {"user_id": user["id"], "owner": user.get("owner") or user["id"], "thread_id": thread, "trace_id": trace_id,
           "status": "running"}
    st, status = await _execute("conversation", g, inp, gthread, user["id"], thread, run_id, trace_id)
    _upsert_conv(user["id"], thread, gthread, status, n_messages)
    return run_id


async def resume_conv(user: dict, thread: str, gthread: str, value: dict) -> str:
    g = (await graphs())["conv"]
    cfg = {"configurable": {"thread_id": gthread}}
    snap = await g.aget_state(cfg)
    pending = snap.next and any(t.interrupts for t in snap.tasks)
    run_id, trace_id = uuid.uuid4().hex[:12], str(uuid.uuid4())
    st, status = await _execute("conversation_resume", g, Command(resume=value) if pending else None, gthread,
                                user["id"], thread, run_id, trace_id)
    with db.engine.begin() as c:
        c.execute(db.convs.update().where(db.convs.c.user_id == user["id"], db.convs.c.graph_thread == gthread)
                  .values(status=status, updated_at=time.time()))
    return run_id


def _upsert_conv(user_id, thread, gthread, status, n):
    ex = db.one(db.select(db.convs).where(db.convs.c.user_id == user_id, db.convs.c.graph_thread == gthread))
    if ex:
        db.q(db.convs.update().where(db.convs.c.id == ex["id"]).values(status=status, updated_at=time.time()))
    else:
        db.q(db.convs.insert().values(user_id=user_id, thread_id=thread, graph_thread=gthread, status=status,
                                      n_messages=n, updated_at=time.time()))


def dumps(o) -> str:
    return json.dumps(o, default=str)
