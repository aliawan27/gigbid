"""Arq on Redis (E1). Every task is first recorded in the app DB (status, attempts, dedup key — what the UI and analytics
read); when REDIS_URL is set it is also pushed onto Arq's Redis queue and an Arq worker executes it. The push writes the
same keys arq.ArqRedis.enqueue_job writes (job data + queue sorted set), from synchronous code, with the task's dedup key
as the Arq job id, so a duplicate enqueue is a no-op on both sides. Without REDIS_URL the worker polls the DB queue."""
from __future__ import annotations

import os
import time
from functools import lru_cache

QUEUE = "arq:queue"
JOB_KEY = "arq:job:"
RESULT_KEY = "arq:result:"
FUNCTION = "arq_run_task"


def redis_url() -> str:
    return os.getenv("REDIS_URL", "")


@lru_cache(1)
def _client():
    import redis
    return redis.Redis.from_url(redis_url(), socket_timeout=5, socket_connect_timeout=5)


def push(task_id: int, job_id: str | None = None, defer_s: float = 0) -> bool:
    """Enqueue an Arq job that runs DB task `task_id`. Returns False if Redis is not configured or the job exists."""
    if not redis_url():
        return False
    from arq.jobs import serialize_job
    job_id = job_id or f"task:{task_id}"
    r = _client()
    if r.exists(JOB_KEY + job_id) or r.exists(RESULT_KEY + job_id):
        return False
    now_ms = int(time.time() * 1000)
    data = serialize_job(FUNCTION, (task_id,), {}, None, now_ms)
    with r.pipeline() as p:
        p.psetex(JOB_KEY + job_id, 24 * 3600 * 1000, data)
        p.zadd(QUEUE, {job_id: now_ms + int(defer_s * 1000)})
        p.execute()
    return True


def ping() -> bool:
    if not redis_url():
        return False
    try:
        return bool(_client().ping())
    except Exception:  # noqa: BLE001
        return False
