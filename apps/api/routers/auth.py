from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select

from apps.api import db
from apps.api.auth.security import hash_password, make_token, verify_password
from apps.api.deps import get_user
from apps.api.schemas.models import Credentials, Onboarding, Prefs, TaskOut, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
UPLOADS = Path(__file__).resolve().parents[3] / "data" / "uploads"
PERSONAS = Path(__file__).resolve().parents[3] / "data" / "personas"


def user_out(u: dict) -> UserOut:
    return UserOut(id=u["id"], username=u["username"], owner=u.get("owner"), prefs=Prefs(**(u.get("prefs") or {})))


@router.post("/register", response_model=TokenOut)
def register(c: Credentials):
    if db.one(select(db.users).where(db.users.c.username == c.username)):
        raise HTTPException(409, "username taken")
    uid = re.sub(r"[^a-z0-9]", "", c.username.lower())[:20] + "-" + uuid.uuid4().hex[:6]
    db.q(db.users.insert().values(id=uid, username=c.username, password_hash=hash_password(c.password), owner=None,
                                  prefs=Prefs().model_dump(), created_at=time.time()))
    u = db.one(select(db.users).where(db.users.c.id == uid))
    return TokenOut(token=make_token(uid), user=user_out(u))


@router.post("/login", response_model=TokenOut)
def login(c: Credentials):
    u = db.one(select(db.users).where(db.users.c.username == c.username))
    if not u or not verify_password(c.password, u["password_hash"]):
        raise HTTPException(401, "wrong username or password")
    return TokenOut(token=make_token(u["id"]), user=user_out(u))


@router.get("/me", response_model=UserOut)
def me(u: dict = Depends(get_user)):
    return user_out(u)


@router.post("/onboarding", response_model=UserOut)
def onboarding(o: Onboarding, u: dict = Depends(get_user)):
    owner = u["id"] if o.persona == "own" else o.persona
    prefs = o.prefs
    if o.persona != "own" and prefs.rate_floor == 40:
        prefs.rate_floor = json.loads((PERSONAS / o.persona / "persona.json").read_text())["rate_floor"]
    db.q(db.users.update().where(db.users.c.id == u["id"]).values(owner=owner, prefs=prefs.model_dump()))
    db.enqueue(u["id"], "scout", {}, dedup_key=f"scout:{u['id']}:onboard:{int(time.time())}")
    return user_out(db.one(select(db.users).where(db.users.c.id == u["id"])))


@router.post("/portfolio", response_model=TaskOut)
async def upload_portfolio(file: UploadFile = File(...), u: dict = Depends(get_user)):
    """Upload a CV (PDF), case study (Markdown) or code file; it is indexed incrementally on next search."""
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", file.filename or "upload.md")[:80]
    if Path(name).suffix.lower() not in (".pdf", ".md", ".txt", ".py", ".js", ".ts"):
        raise HTTPException(400, "supported: .pdf .md .txt .py .js .ts")
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(413, "max 5 MB")
    owner = u.get("owner") or u["id"]
    d = UPLOADS / owner
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(data)
    return TaskOut(queued=False, message=f"{name} added to portfolio '{owner}' (re-indexed incrementally)")


@router.get("/upwork/connect")
def upwork_connect(u: dict = Depends(get_user)):
    """Start of the Upwork OAuth 2.1 flow for live mode (tokens are stored encrypted per user, never logged)."""
    import os
    cid = os.getenv("UPWORK_CLIENT_ID")
    if not cid:
        return {"available": False, "message": "Live Upwork mode needs UPWORK_CLIENT_ID; GigSim is used for grading."}
    return {"available": True, "authorize_url": f"https://www.upwork.com/ab/account-security/oauth2/authorize?"
            f"response_type=code&client_id={cid}&redirect_uri={os.getenv('UPWORK_REDIRECT_URI', '')}&state={u['id']}"}
