# ADR 0004 — Arq on Redis, with the app DB as the task record (supersedes "DB queue only")
**Decision.** Tasks are recorded in the app DB `tasks` table (unique `dedup_key`, status, attempts — what the UI and analytics
read) and executed by an **Arq** worker on **Redis** (`worker/queue.py`, `worker/main.py::run_arq`). Scouting and pipeline sync
are Arq cron jobs. The Arq job id is derived from the task, so duplicate enqueues are no-ops; Arq re-runs jobs whose worker
died, and on start-up unfinished DB tasks are handed back to Arq. Without `REDIS_URL` (local runs, CI) — or if Redis becomes
unreachable — the worker falls back to polling the DB queue, so the system degrades instead of stopping.
**Deployment.** Render free Key Value (Redis-compatible) in the same region as the service; `docker compose` runs `redis:7.2`.
**Why.** The brief asks for Celery, Arq or Dramatiq on Redis; Arq is asyncio-native like the graphs, and keeping the DB as the
record preserves idempotent, inspectable task history.
