"""SSE bridge: relays LangGraph stream events (custom node start/end events written by the worker while it runs
graph.astream(stream_mode=["custom","updates"])) to the browser. Reconnect-safe via Last-Event-ID."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import read_token

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, token: str = Query(""), last_event_id: str | None = Header(default=None)):
    uid = read_token(token)  # EventSource cannot set headers, so the session token comes as a query param
    run = db.one(select(db.runs).where(db.runs.c.id == run_id))
    if not uid or not run or run["user_id"] != uid:
        raise HTTPException(404, "run not found")

    async def gen():
        last = int(last_event_id or 0)
        idle = 0
        while idle < 600:
            evs = await asyncio.to_thread(db.rows, select(db.events).where(db.events.c.run_id == run_id, db.events.c.id > last)
                                          .order_by(db.events.c.id))
            for e in evs:
                last = e["id"]
                yield f"id: {e['id']}\ndata: {json.dumps(e['data'])}\n\n"
                if e["data"].get("phase") == "run_end":
                    return
            idle = 0 if evs else idle + 1
            if not evs:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/stream/latest")
async def latest_run(job_id: str = "", u: str = Depends(lambda authorization=Header(default=""): read_token(authorization.removeprefix("Bearer ")))):
    if not u:
        raise HTTPException(401, "not signed in")
    stmt = select(db.runs).where(db.runs.c.user_id == u)
    if job_id:
        stmt = stmt.where(db.runs.c.ref_id == job_id)
    r = db.rows(stmt.order_by(db.runs.c.created_at.desc()).limit(1))
    return r[0] if r else None
