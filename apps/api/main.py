"""GigBid API (FastAPI). Long work runs in the worker; this process serves the UI, reads graph state, records
approvals and streams progress over SSE. Run: uvicorn apps.api.main:app --port 8000"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LANGSMITH_PROJECT", "gigbid")
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TRACING", "true")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from agent.config import CONFIG  # noqa: E402
from apps.api import db  # noqa: E402
from apps.api.routers import auth, jobs, messages, runs, settings  # noqa: E402
from apps.api.schemas.models import Health  # noqa: E402
from apps.api.streaming import router as stream_router  # noqa: E402

WEB = Path(__file__).resolve().parents[1] / "web" / "dist"


@asynccontextmanager
async def lifespan(app):
    db.init_db()
    from scripts.seed_users import seed
    seed()
    yield


app = FastAPI(title="GigBid API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def trace_mw(request: Request, call_next):
    tid = request.headers.get("x-trace-id") or uuid.uuid4().hex
    request.state.trace_id = tid
    t0 = time.time()
    resp = await call_next(request)
    resp.headers["x-trace-id"] = tid
    resp.headers["x-latency-ms"] = str(int((time.time() - t0) * 1000))
    return resp


for r in (auth.router, jobs.router, messages.router, runs.router, settings.router, stream_router):
    app.include_router(r)


@app.get("/api/health", response_model=Health, tags=["health"])
async def health():
    from agent.mcp_client import health as mcp_health
    h = await mcp_health()
    return Health(api=True, marketplace=h["marketplace"], portfolio=h["portfolio"], workspace=h["workspace"],
                  degraded=not all(h.values()), mode=os.getenv("MARKETPLACE_MODE", CONFIG["marketplace"]["mode"]))


@app.exception_handler(Exception)
async def unhandled(_req, exc):
    return JSONResponse({"detail": f"internal error: {type(exc).__name__}"}, status_code=500)


if WEB.exists():
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = WEB / path
        return FileResponse(f if path and f.is_file() else WEB / "index.html")
