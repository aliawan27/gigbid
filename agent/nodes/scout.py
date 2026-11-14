"""Scout: loads the job through the Marketplace MCP server and de-duplicates reposts. (Scheduled searching and
queueing of new jobs happens in worker/scheduler.py, which starts one bid-graph thread per new job.)"""
from __future__ import annotations

import hashlib
import re

from agent.mcp_client import call
from agent.nodes._common import node, tool_rec


def fingerprint(job: dict) -> str:
    t = re.sub(r"\(reposted\)|[^a-z0-9 ]", "", job["title"].lower())
    d = re.sub(r"[^a-z0-9 ]", "", job["description"].lower())[:300]
    return hashlib.sha1(f"{job.get('client_id')}|{t.strip()}|{d}".encode()).hexdigest()


@node("scout")
async def scout(state, store):
    args = {"user_id": state["user_id"], "job_id": state["job_id"], "trace_id": state.get("trace_id", "")}
    job = state.get("job") or await call("scout", "get_job", args)
    out = {"job": job, "status": "running", "_tools": [tool_rec("get_job", args, job.get("title"))]}
    if store is not None:
        ns = ("seen_jobs", state["user_id"])
        fp = fingerprint(job)
        seen = await store.aget(ns, fp)
        if seen and seen.value["job_id"] != job["job_id"]:
            out.update(status="skipped", decision={"action": "skip", "reason": f"duplicate of {seen.value['job_id']}"},
                       _summary="duplicate repost")
            return out
        await store.aput(ns, fp, {"job_id": job["job_id"]})
    out["_summary"] = job["title"]
    return out
