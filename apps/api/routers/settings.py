from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select

from agent.memory.store import delete_memory, list_memory
from apps.api import db
from apps.api.deps import get_user, graphs
from apps.api.schemas.models import MemoryItem, Prefs

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings(u: dict = Depends(get_user)):
    connected = [r["provider"] for r in db.rows(select(db.oauth.c.provider).where(db.oauth.c.user_id == u["id"]))]
    return {"prefs": Prefs(**(u.get("prefs") or {})).model_dump(), "owner": u.get("owner"),
            "connected_accounts": ["gigsim"] + connected}


@router.put("/settings", response_model=Prefs)
def put_settings(p: Prefs, u: dict = Depends(get_user)):
    db.q(db.users.update().where(db.users.c.id == u["id"]).values(prefs=p.model_dump()))
    return p


@router.get("/memory", response_model=list[MemoryItem])
async def memory(u: dict = Depends(get_user)):
    g = await graphs()
    return [MemoryItem(**m) for m in await list_memory(g["store"], u["id"])]


@router.delete("/memory/{namespace}/{key:path}")
async def forget(namespace: str, key: str, u: dict = Depends(get_user)):
    g = await graphs()
    await delete_memory(g["store"], u["id"], namespace, key)
    return {"deleted": True}
