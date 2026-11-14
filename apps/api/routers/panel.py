"""Public blind pairwise panel: classmates compare two anonymised proposals for the same job (no login).
Raters never see configuration names; left/right order is randomised on every view."""
from __future__ import annotations

import json
import random
import re
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from apps.api import db

router = APIRouter(prefix="/api/panel", tags=["panel"])
PAIRS = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "pairwise_pairs.json"
RATER = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


@lru_cache(1)
def pairs() -> list[dict]:
    return json.loads(PAIRS.read_text(encoding="utf-8")) if PAIRS.exists() else []


class PanelPair(BaseModel):
    pair_ref: int
    swap: bool
    job_title: str
    job_description: str
    left: str
    right: str
    done: int
    total: int


class PanelVote(BaseModel):
    rater: str = Field(min_length=6, max_length=64)
    pair_ref: int
    swap: bool
    choice: str = Field(pattern="^(left|right|tie)$")


@router.get("/pair", response_model=PanelPair | None)
def next_pair(rater: str):
    if not RATER.match(rater):
        raise HTTPException(400, "bad rater id")
    ps = pairs()
    done = {r["pair_id"] for r in db.rows(select(db.panel_votes.c.pair_id).where(db.panel_votes.c.rater == rater))}
    counts = {r["pair_id"]: r["n"] for r in db.rows(select(db.panel_votes.c.pair_id, func.count().label("n"))
                                                     .group_by(db.panel_votes.c.pair_id))}
    todo = [i for i, p in enumerate(ps) if p["pair_id"] not in done]
    if not todo:
        return None
    least = min(counts.get(ps[i]["pair_id"], 0) for i in todo)  # spread votes evenly across pairs
    i = random.choice([i for i in todo if counts.get(ps[i]["pair_id"], 0) == least])
    p, swap = ps[i], random.random() < 0.5
    left, right = (p["b_text"], p["a_text"]) if swap else (p["a_text"], p["b_text"])
    return PanelPair(pair_ref=i, swap=swap, job_title=p["job_title"], job_description=p["job_description"],
                     left=left, right=right, done=len(done), total=len(ps))


@router.post("/vote")
def vote(v: PanelVote):
    ps = pairs()
    if not RATER.match(v.rater) or not 0 <= v.pair_ref < len(ps):
        raise HTTPException(400, "bad vote")
    winner = "tie" if v.choice == "tie" else ("a" if (v.choice == "left") != v.swap else "b")
    try:
        db.q(db.panel_votes.insert().values(rater=v.rater, pair_id=ps[v.pair_ref]["pair_id"], winner=winner, ts=time.time()))
    except Exception:  # noqa: BLE001  (already voted on this pair)
        pass
    return {"ok": True}
