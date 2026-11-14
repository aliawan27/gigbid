"""App database (users, job index, runs + streamed events, task queue, encrypted OAuth tokens).
Postgres via DATABASE_URL in deployment, SQLite locally. Every query is scoped by user_id (tenant)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from sqlalchemy import (JSON, Column, Float, Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine,
                        insert, select, update)

ROOT = Path(__file__).resolve().parents[2]


def _url() -> str:
    u = os.getenv("DATABASE_URL", "")
    if u.startswith("postgres"):
        return u.replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1)
    p = os.getenv("GIGBID_APP_DB", str(ROOT / "data" / "gigbid_app.db"))
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p}"


engine = create_engine(_url(), pool_pre_ping=True, future=True,
                       connect_args={"check_same_thread": False, "timeout": 30} if _url().startswith("sqlite") else {})
md = MetaData()

users = Table("users", md,
              Column("id", String, primary_key=True), Column("username", String, unique=True),
              Column("password_hash", String), Column("owner", String), Column("prefs", JSON),
              Column("created_at", Float))
jobs = Table("jobs", md,
             Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, index=True),
             Column("job_id", String), Column("thread_id", String), Column("title", String), Column("status", String),
             Column("summary", JSON), Column("updated_at", Float),
             UniqueConstraint("user_id", "job_id", name="uq_user_job"))
runs = Table("runs", md,
             Column("id", String, primary_key=True), Column("user_id", String, index=True), Column("kind", String),
             Column("thread_id", String), Column("ref_id", String), Column("status", String), Column("trace_id", String),
             Column("created_at", Float), Column("updated_at", Float), Column("tokens", Integer), Column("cost_usd", Float),
             Column("latency_s", Float))
events = Table("run_events", md,
               Column("id", Integer, primary_key=True, autoincrement=True), Column("run_id", String, index=True),
               Column("ts", Float), Column("data", JSON))
tasks = Table("tasks", md,
              Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String),
              Column("kind", String), Column("payload", JSON), Column("dedup_key", String, unique=True),
              Column("status", String, index=True), Column("attempts", Integer, default=0), Column("run_id", String),
              Column("error", Text), Column("created_at", Float), Column("updated_at", Float))
oauth = Table("oauth_tokens", md,
              Column("user_id", String, primary_key=True), Column("provider", String, primary_key=True),
              Column("token_encrypted", Text), Column("updated_at", Float))
panel_votes = Table("panel_votes", md,  # blind pairwise human panel (evals/runners/pairwise_panel.py)
                    Column("id", Integer, primary_key=True, autoincrement=True), Column("rater", String, index=True),
                    Column("pair_id", String, index=True), Column("winner", String), Column("ts", Float),
                    UniqueConstraint("rater", "pair_id", name="uq_rater_pair"))
convs = Table("conversations", md,
              Column("id", Integer, primary_key=True, autoincrement=True), Column("user_id", String, index=True),
              Column("thread_id", String), Column("graph_thread", String), Column("status", String),
              Column("n_messages", Integer), Column("updated_at", Float),
              UniqueConstraint("user_id", "graph_thread", name="uq_conv"))


def init_db() -> None:
    md.create_all(engine)


def q(stmt):
    with engine.begin() as c:
        return c.execute(stmt)


def rows(stmt) -> list[dict]:
    with engine.begin() as c:
        return [dict(r._mapping) for r in c.execute(stmt)]


def one(stmt) -> dict | None:
    r = rows(stmt)
    return r[0] if r else None


def enqueue(user_id: str, kind: str, payload: dict, dedup_key: str | None = None) -> int | None:
    now = time.time()
    try:
        with engine.begin() as c:
            res = c.execute(insert(tasks).values(user_id=user_id, kind=kind, payload=payload, dedup_key=dedup_key,
                                                 status="queued", attempts=0, created_at=now, updated_at=now))
            return res.inserted_primary_key[0]
    except Exception:  # noqa: BLE001  duplicate dedup_key -> already queued/done (idempotent processing)
        return None


def upsert_job(user_id: str, job_id: str, **vals) -> None:
    vals["updated_at"] = time.time()
    with engine.begin() as c:
        ex = c.execute(select(jobs.c.id).where(jobs.c.user_id == user_id, jobs.c.job_id == job_id)).first()
        if ex:
            c.execute(update(jobs).where(jobs.c.id == ex[0]).values(**vals))
        else:
            c.execute(insert(jobs).values(user_id=user_id, job_id=job_id, **vals))


def add_event(run_id: str, data: dict) -> None:
    q(insert(events).values(run_id=run_id, ts=time.time(), data=json.loads(json.dumps(data, default=str))))
