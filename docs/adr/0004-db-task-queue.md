# ADR 0004 — Task queue in the app database instead of Celery/Redis
**Decision.** The worker polls a `tasks` table (unique `dedup_key`, status, attempts) instead of Celery on Redis.
**Why.** One fewer service to host for free; the dedup key gives idempotent scouting, and re-queuing `running` tasks on start
gives crash recovery. Trade-off: polling latency (1 s) and a single worker.
