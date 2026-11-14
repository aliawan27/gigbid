"""GigBid worker (E1): scheduled scouting, long agent runs, pipeline sync — never inside web requests.

* Task queue in the app DB (tasks table). A task has a unique dedup_key, so a re-scout never double-queues a
  job, and a restart re-runs only tasks that were 'running' (resume is idempotent: graph checkpoints + the
  deterministic submit idempotency key mean a crashed submit is applied exactly once).
* Each user's saved searches are scouted every `scout_interval_minutes` (gigsim) or the conservative
  `live_scout_interval_minutes` (live Upwork) from agent/config.yaml.
* Pipeline sync polls proposal statuses + message threads; outcome memory is updated only from these
  marketplace-confirmed status changes (promotion rule in agent/memory/promotion_rules.py).

Run: python -m worker.main
"""
from __future__ import annotations

import os as _os

from dotenv import load_dotenv

load_dotenv()
_os.environ.setdefault("LANGSMITH_PROJECT", "gigbid")
if _os.getenv("LANGSMITH_API_KEY"):
    _os.environ.setdefault("LANGSMITH_TRACING", "true")

import asyncio
import logging
import os
import time
import traceback

from sqlalchemy import case, select

from agent.config import CONFIG
from agent.marketplace_port import MarketplaceUnavailable
from agent.mcp_client import call
from agent.memory.store import record_outcome
from apps.api import db
from worker import runner

log = logging.getLogger("worker")
POLL_S = float(os.getenv("WORKER_POLL_S", "1.0"))
SYNC_EVERY_S = float(os.getenv("WORKER_SYNC_EVERY_S", "45"))
MAX_PARALLEL = int(os.getenv("WORKER_MAX_PARALLEL", "2"))


def users() -> list[dict]:
    return db.rows(select(db.users))


def user(uid: str) -> dict:
    return db.one(select(db.users).where(db.users.c.id == uid))


async def scout(u: dict) -> int:
    """Run saved searches, de-duplicate, queue new jobs (one bid thread per job)."""
    prefs = u.get("prefs") or {}
    seen = {r["job_id"] for r in db.rows(select(db.jobs.c.job_id).where(db.jobs.c.user_id == u["id"]))}
    cat = {"ai_ml": "ai_ml", "fullstack": "web", "data_analyst": "data"}.get(u.get("owner") or "", "")
    n = 0
    for q in prefs.get("saved_searches") or [""]:
        found = await call("scout", "search_jobs", {"user_id": u["id"], "query": q, "category": cat, "limit": 10})
        for j in found:
            if j["job_id"] in seen or (prefs.get("min_budget") and (j.get("budget") or 0) < prefs["min_budget"]):
                continue
            seen.add(j["job_id"])
            db.upsert_job(u["id"], j["job_id"], title=j["title"], status="queued",
                          summary={"budget": j.get("budget"), "connects_cost": j.get("connects_cost")})
            if db.enqueue(u["id"], "bid", {"job_id": j["job_id"]}, dedup_key=f"bid:{u['id']}:{j['job_id']}"):
                n += 1
    return n


async def sync_pipeline(u: dict) -> None:
    """Pull proposal statuses + threads; update pipeline and outcome memory; start conversation threads."""
    g = await runner.graphs()
    props = await call("api", "list_proposals", {"user_id": u["id"]})
    for p in props:
        row = db.one(select(db.jobs).where(db.jobs.c.user_id == u["id"], db.jobs.c.job_id == p["job_id"]))
        if not row:
            continue
        summ = row.get("summary") or {}
        if summ.get("marketplace_status") != p["status"]:
            summ["marketplace_status"] = p["status"]
            db.upsert_job(u["id"], p["job_id"], summary=summ)
            if p["status"] in ("replied", "interview", "hired", "ignored"):
                await record_outcome(g["store"], u["id"], summ.get("category") or "general", p["status"],
                                     {"job_id": p["job_id"], "opening": (p.get("cover_letter") or "")[:200]})
    threads = await call("api", "list_messages", {"user_id": u["id"]})
    for t in threads:
        last = t["messages"][-1]
        if last["from"] == "client":
            db.enqueue(u["id"], "conversation", {"thread_id": t["thread_id"], "n": len(t["messages"])},
                       dedup_key=f"conv:{u['id']}:{t['thread_id']}:{len(t['messages'])}")


async def handle(task: dict) -> str | None:
    u = user(task["user_id"])
    p = task["payload"]
    k = task["kind"]
    if k == "bid":
        return await runner.start_bid(u, p["job_id"], attempt=p.get("attempt", 0))
    if k == "resume_bid":
        return await runner.resume_bid(u, p["job_id"], p["thread_id"], p["value"])
    if k == "conversation":
        return await runner.start_conv(u, p["thread_id"], p["n"])
    if k == "resume_conv":
        return await runner.resume_conv(u, p["thread_id"], p["graph_thread"], p["value"])
    if k == "scout":
        await scout(u)
        return None
    raise ValueError(f"unknown task {k}")


async def run_task(task: dict, sem: asyncio.Semaphore):
    async with sem:
        try:
            run_id = await handle(task)
            db.q(db.tasks.update().where(db.tasks.c.id == task["id"]).values(status="done", run_id=run_id, updated_at=time.time()))
        except MarketplaceUnavailable as e:
            db.q(db.tasks.update().where(db.tasks.c.id == task["id"]).values(status="queued", error=str(e)[:500],
                                                                             updated_at=time.time() + 30))
        except Exception as e:  # noqa: BLE001
            log.error("task %s failed: %s", task["id"], traceback.format_exc())
            st = "dead_letter" if task["attempts"] >= 2 else "queued"
            db.q(db.tasks.update().where(db.tasks.c.id == task["id"]).values(status=st, error=str(e)[:500], updated_at=time.time()))


def claim(limit: int, resumes_only: bool = False) -> list[dict]:
    now = time.time()
    cond = [db.tasks.c.status == "queued", db.tasks.c.updated_at <= now]
    if resumes_only:
        cond.append(db.tasks.c.kind.in_(["resume_bid", "resume_conv"]))
    with db.engine.begin() as c:
        rows = [dict(r._mapping) for r in c.execute(
            select(db.tasks).where(*cond)
            .order_by(case((db.tasks.c.kind.in_(["resume_bid", "resume_conv"]), 0), else_=1), db.tasks.c.id).limit(limit))]
        for r in rows:
            c.execute(db.tasks.update().where(db.tasks.c.id == r["id"], db.tasks.c.status == "queued")
                      .values(status="running", attempts=(r["attempts"] or 0) + 1, updated_at=now))
    return rows


def recover() -> None:
    """On start: tasks left 'running' by a crash are re-queued (idempotent resume)."""
    db.q(db.tasks.update().where(db.tasks.c.status == "running").values(status="queued"))


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    db.init_db()
    recover()
    await runner.graphs()
    sem = asyncio.Semaphore(MAX_PARALLEL)
    last_scout: dict[str, float] = {}
    last_sync = 0.0
    live = os.getenv("MARKETPLACE_MODE", CONFIG["marketplace"]["mode"]) == "upwork_live"
    interval = 60 * CONFIG["marketplace"]["live_scout_interval_minutes" if live else "scout_interval_minutes"]
    log.info("worker started (scout interval %ss)", interval)
    running: set[asyncio.Task] = set()
    while True:
        now = time.time()
        try:
            for u in users():
                if u.get("owner") and now - last_scout.get(u["id"], 0) > interval:
                    last_scout[u["id"]] = now
                    db.enqueue(u["id"], "scout", {}, dedup_key=f"scout:{u['id']}:{int(now // interval)}")
            if now - last_sync > SYNC_EVERY_S:
                last_sync = now
                for u in users():
                    if u.get("owner"):
                        try:
                            await sync_pipeline(u)
                        except Exception as e:  # noqa: BLE001
                            log.warning("sync failed for %s: %s", u["id"], e)
            free = MAX_PARALLEL - len(running)
            # approvals/resumes are short and a human is waiting: they never wait behind long analyses
            for t in claim(5, resumes_only=True) + (claim(free) if free > 0 else []):
                task = asyncio.create_task(run_task(t, asyncio.Semaphore(1) if t["kind"].startswith("resume") else sem))
                running.add(task)
                task.add_done_callback(running.discard)
        except Exception:  # noqa: BLE001
            log.error("loop error: %s", traceback.format_exc())
        await asyncio.sleep(POLL_S)


if __name__ == "__main__":
    asyncio.run(main())
