from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import select

from apps.api import db
from apps.api.deps import get_user
from apps.api.schemas.models import RunRow

router = APIRouter(prefix="/api", tags=["runs"])


def trace_url(trace_id: str | None) -> str | None:
    base = os.getenv("LANGSMITH_TRACE_BASE")  # e.g. https://smith.langchain.com/o/<org>/projects/p/<project>/r
    return f"{base}/{trace_id}" if base and trace_id else None


@router.get("/runs", response_model=list[RunRow])
def list_runs(limit: int = 50, u: dict = Depends(get_user)):
    rs = db.rows(select(db.runs).where(db.runs.c.user_id == u["id"]).order_by(db.runs.c.created_at.desc()).limit(limit))
    return [RunRow(**{k: r.get(k) for k in RunRow.model_fields if k != "trace_url"}, trace_url=trace_url(r.get("trace_id")))
            for r in rs]


@router.get("/runs/{run_id}")
def run_detail(run_id: str, u: dict = Depends(get_user)):
    r = db.one(select(db.runs).where(db.runs.c.id == run_id, db.runs.c.user_id == u["id"]))
    evs = db.rows(select(db.events).where(db.events.c.run_id == run_id).order_by(db.events.c.id))
    return {"run": r, "trace_url": trace_url((r or {}).get("trace_id")), "events": [e["data"] for e in evs]}


@router.get("/analytics")
def analytics(u: dict = Depends(get_user)):
    jobs = db.rows(select(db.jobs).where(db.jobs.c.user_id == u["id"]))
    runs = db.rows(select(db.runs).where(db.runs.c.user_id == u["id"]))
    by_cat: dict[str, dict] = {}
    connects_spent, outcomes = 0, {"replied": 0, "interview": 0, "hired": 0, "ignored": 0}
    rejections: dict[str, int] = {}
    skips: dict[str, int] = {}
    for j in jobs:
        s = j.get("summary") or {}
        cat = s.get("category") or "unknown"
        c = by_cat.setdefault(cat, {"analysed": 0, "submitted": 0, "replied": 0, "hired": 0})
        c["analysed"] += 1
        ms = s.get("marketplace_status")
        if j["status"] == "submitted":
            c["submitted"] += 1
            connects_spent += s.get("connects_cost") or 0
        if ms in ("replied", "interview", "hired"):
            c["replied"] += 1
        if ms == "hired":
            c["hired"] += 1
        if ms in outcomes:
            outcomes[ms] += 1
        if j["status"] == "skipped" and s.get("reason"):
            key = s["reason"].split(" (")[0].split(";")[0][:60]
            skips[key] = skips.get(key, 0) + 1
    for r in db.rows(select(db.tasks).where(db.tasks.c.user_id == u["id"], db.tasks.c.kind == "resume_bid")):
        v = (r.get("payload") or {}).get("value") or {}
        if v.get("action") == "reject":
            rejections[v.get("reason") or "?"] = rejections.get(v.get("reason") or "?", 0) + 1
    for c in by_cat.values():
        c["reply_rate"] = round(c["replied"] / c["submitted"], 3) if c["submitted"] else None
        c["hire_rate"] = round(c["hired"] / c["submitted"], 3) if c["submitted"] else None
    bid_runs = [r for r in runs if r["kind"] == "bid" and r.get("latency_s")]
    prop_runs = [r for r in runs if r["kind"] == "bid" and r.get("status") in ("awaiting_approval", "submitted")]

    def p(vals, q):
        v = sorted(x for x in vals if x is not None)
        return round(v[min(len(v) - 1, int(q * len(v)))], 3) if v else None

    return {"by_category": by_cat, "connects_spent": connects_spent, "outcomes": outcomes,
            "cost_per_job_usd": p([r.get("cost_usd") for r in bid_runs], 0.5),
            "cost_per_proposal_usd": p([r.get("cost_usd") for r in prop_runs], 0.5),
            "latency_p50_s": p([r["latency_s"] for r in bid_runs], 0.5), "latency_p95_s": p([r["latency_s"] for r in bid_runs], 0.95),
            "top_rejection_reasons": sorted(rejections.items(), key=lambda x: -x[1])[:5],
            "top_skip_reasons": sorted(skips.items(), key=lambda x: -x[1])[:5], "n_jobs": len(jobs), "n_runs": len(runs)}
