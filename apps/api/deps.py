from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import current_user

_graphs: dict = {}


async def graphs() -> dict:
    if not _graphs:
        from agent.graphs.bid_graph import build_bid_graph
        from agent.graphs.conversation_graph import build_conversation_graph
        from agent.persistence import open_persistence
        saver, store = await open_persistence()
        _graphs.update(bid=build_bid_graph(saver, store), conv=build_conversation_graph(saver, store), store=store)
    return _graphs


def get_user(uid: str = Depends(current_user)) -> dict:
    u = db.one(select(db.users).where(db.users.c.id == uid))
    if not u:
        raise HTTPException(401, "unknown user")
    return u


async def pending_interrupt(graph, thread_id: str) -> dict | None:
    snap = await graph.aget_state({"configurable": {"thread_id": thread_id}})
    for t in snap.tasks or []:
        if t.interrupts:
            return t.interrupts[0].value
    return None
