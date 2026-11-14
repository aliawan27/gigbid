# ADR 0003 — One process on the free host, separate containers in compose
**Decision.** `apps/api/allinone.py` mounts GigSim and the three MCP servers (still real MCP over HTTP) into the API process
and runs the worker loop as a background task; `docker compose` runs every service as its own container.
**Why.** Free hosts give ~512 MB; six Python processes needed ~800 MB, one process needs ~340 MB.
