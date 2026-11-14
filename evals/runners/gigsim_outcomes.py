"""B4/B5 proposal quality + outcomes on a fixed GigSim job set, for three configurations:
  v0_open    : V0 naive retrieval, open profile (gpt-oss-120b writer/critic)
  best_open  : shipped retrieval (V5 + hybrid), open profile
  best_qwen  : shipped retrieval, second open profile (qwen3.8-27b writer/critic)
Each proposal runs the full bid graph, is auto-approved by the harness (standing in for the human), submitted to a
fresh GigSim whose LLM clients decide reply/interview/hire. Metrics: unsupported claims per proposal (before/after
verification), calibrated-judge score, reply/hire rate, p50/p95 latency and USD per proposal.
Run: python evals/runners/gigsim_outcomes.py [--per-persona N]"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

from _common import JOBS, PERSONAS, ROOT, Stack, dev, mean, pct, persona_prefs, public_job, write
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from agent.graphs.bid_graph import build_bid_graph
from agent.llm import LLMUnavailable, _extract_json, chat
from agent.nodes.approval import clean_letter

CONFIGS = {"v0_open": ("v0_naive", "open"), "best_open": ("best", "open"), "best_qwen": ("best", "open_qwen")}
JUDGE_MODEL = "openai/gpt-oss-120b"


def fixed_jobs(per_persona: int) -> list[tuple[str, str]]:
    out = []
    for p in PERSONAS:
        bids = [g for g in dev(p) if g["decision"] == "bid" and g["kind"] == "fit"]
        out += [(p, g["job_id"]) for g in bids[:per_persona]]
    return out


def judge(job: dict, letter: str) -> dict:
    sys = (ROOT / "agent" / "prompts" / "judge.md").read_text()
    user = f"JOB: {job['title']}\n{job['description'][:900]}\n\nPROPOSAL:\n{letter}"
    try:
        out = chat(JUDGE_MODEL, [{"role": "system", "content": sys}, {"role": "user", "content": user}], node="judge",
                   temperature=0, json_mode=True, max_tokens=300)
        d = _extract_json(out["content"])
        return {"score": int(d["score"]), "reason": d.get("reason", "")}
    except (LLMUnavailable, KeyError, ValueError):
        return {"score": None, "reason": "judge unavailable"}


async def proposal(g, stack: Stack, persona: str, job_id: str, tag: str, sem) -> dict:
    async with sem:
        job = public_job(JOBS[job_id])
        user = f"eval-{tag}-{persona}"
        cfg = {"configurable": {"thread_id": f"{tag}:{job_id}"}}
        t0 = time.time()
        await g.ainvoke({"user_id": user, "owner": persona, "job_id": job_id, "job": job, "trace_id": "eval", "status": "running",
                         "prefs": persona_prefs(persona)}, cfg)
        st = (await g.aget_state(cfg)).values
        lat = time.time() - t0
        row = {"persona": persona, "job_id": job_id, "config": tag, "status": st.get("status"), "latency_s": round(lat, 2),
               "tokens": st.get("tokens", 0), "usd": st.get("cost_usd", 0), "revisions": st.get("revisions", 0),
               "unsupported_before": st.get("unsupported_before"), "unsupported_after": st.get("unsupported_after"),
               "n_claims": len(st.get("claim_checks") or []), "decision": (st.get("decision") or {}).get("action")}
        checks = st.get("claim_checks") or []
        row["unsupported_claims_before"] = sum(c["label"] == "unsupported" for c in checks)
        if st.get("status") != "awaiting_approval":
            return row
        letter = clean_letter(st["draft"]["cover_letter"])
        await g.ainvoke(Command(resume={"action": "approve"}), cfg)  # harness approves (stands in for the human)
        st = (await g.aget_state(cfg)).values
        res = (st.get("submission") or {}).get("result") or {}
        row.update(letter=letter, words=len(letter.split()), marketplace_status=res.get("status"),
                   judge=(await asyncio.to_thread(judge, job, letter)))
        row["unsupported_claims_after"] = round(row["unsupported_after"] * row["n_claims"]) if row["unsupported_after"] is not None else None
        return row


def summarise(rows: list[dict]) -> dict:
    sub = [r for r in rows if r.get("marketplace_status")]
    return {"n_jobs": len(rows), "n_submitted": len(sub),
            "unsupported_claims_per_proposal_before": mean([r.get("unsupported_claims_before") for r in sub]),
            "unsupported_claims_per_proposal_after": mean([r.get("unsupported_claims_after") for r in sub]),
            "judge_score": mean([(r.get("judge") or {}).get("score") for r in sub]),
            "reply_rate": round(sum(r["marketplace_status"] in ("replied", "interview", "hired") for r in sub) / len(sub), 3) if sub else None,
            "hire_rate": round(sum(r["marketplace_status"] == "hired" for r in sub) / len(sub), 3) if sub else None,
            "p50_latency_s_per_proposal": pct([r["latency_s"] for r in sub], 0.5),
            "p95_latency_s_per_proposal": pct([r["latency_s"] for r in sub], 0.95),
            "usd_per_proposal": mean([r["usd"] for r in sub]), "p95_usd_per_proposal": pct([r["usd"] for r in sub], 0.95),
            "tokens_per_proposal": mean([r["tokens"] for r in sub]), "mean_revisions": mean([r["revisions"] for r in sub]),
            "mean_words": mean([r.get("words") for r in sub])}


async def run_config(tag: str, jobs, conc: int) -> list[dict]:
    variant, profile = CONFIGS[tag]
    os.environ["GIGBID_RAG_VARIANT"] = variant
    os.environ["MODEL_PROFILE"] = profile
    with Stack(client_llm=True) as stack:
        g = build_bid_graph(MemorySaver(), InMemoryStore())
        sem = asyncio.Semaphore(conc)
        rows = await asyncio.gather(*[proposal(g, stack, p, j, tag, sem) for p, j in jobs])
    return list(rows)


async def main(per_persona: int, configs: list[str]):
    jobs = fixed_jobs(per_persona)
    prev = {}
    f = ROOT / "evals" / "results" / "gigsim_outcomes.json"
    if f.exists():
        prev = json.loads(f.read_text()).get("configs", {})
    out = dict(prev)
    for tag in configs:
        rows = await run_config(tag, jobs, conc=3)
        out[tag] = {"summary": summarise(rows), "rows": rows}
        print(tag, out[tag]["summary"])
        write("gigsim_outcomes", {"job_set": jobs, "configs": out, "judge_model": JUDGE_MODEL,
                                  "note": "Proposals auto-approved by the harness; GigSim clients are LLM-simulated (gpt-oss-20b)."})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-persona", type=int, default=6)
    ap.add_argument("--configs", default="v0_open,best_open,best_qwen")
    a = ap.parse_args()
    asyncio.run(main(a.per_persona, a.configs.split(",")))
