"""Make the four required LangSmith traces public and record their links in evals/results/trace_links.json.
Usage: python scripts/share_traces.py <app.db path>"""
import json
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
from langsmith import Client  # noqa: E402

c = sqlite3.connect(sys.argv[1])
rows = c.execute("select id, kind, ref_id, status, trace_id from runs order by created_at").fetchall()
want = {}
for rid, kind, ref, st, tid in rows:
    if ref == "job-0036" and kind == "bid":
        want["skipped_scam"] = tid
    if ref == "job-0123" and kind == "bid":
        want["critic_loop_2_revisions"] = tid
    if ref == "job-0123" and kind == "bid_resume" and st == "submitted":
        want["approved_proposal_submitted"] = tid
    if ref == "job-0121" and kind == "bid_resume" and st == "submitted":
        want["crash_and_resume_exactly_once"] = tid
print(want)
cl = Client()
out = {}
for k, tid in want.items():
    try:
        out[k] = cl.share_run(tid)
    except Exception as e:  # noqa: BLE001
        out[k] = f"error: {e}"[:200]
print(json.dumps(out, indent=1))
(ROOT / "evals" / "results" / "trace_links.json").write_text(json.dumps(out, indent=1))
