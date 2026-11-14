"""R&D question A — does tool granularity change agent behaviour?
40 tasks with a known correct tool call; three tool sets are offered to the same model (gpt-oss-20b, temperature 0):
  fine    : many narrow tools (one per field / filter)
  coarse  : two catch-all tools with an `action` argument
  best    : GigBid's shipped tools with rewritten, example-bearing descriptions
Metrics: tool-selection accuracy, argument accuracy, tokens per task. Run: python evals/runners/tool_granularity.py"""
from __future__ import annotations

import json
import time

from _common import mean, write

from agent.llm import LLMUnavailable, chat

MODEL = "openai/gpt-oss-20b"


def fn(name, desc, props, req=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": req or list(props)}}}


S = {"type": "string"}
I = {"type": "integer"}

BEST = [
    fn("search_jobs", "Search open marketplace jobs. Use for finding NEW jobs by keywords or category. "
       "Example: {'query': 'dbt snowflake', 'category': 'data'}", {"query": S, "category": S}, []),
    fn("get_job", "Get ONE job post by its id (e.g. 'job-0042'): title, description, budget, skills, Connects cost.", {"job_id": S}),
    fn("get_client_history", "A client's public history by client id (e.g. 'c017'): spend, hires, rating, payment verified.", {"client_id": S}),
    fn("get_market_stats", "Historical price statistics for a category ('ai_ml','web','data') and complexity 1-5.",
       {"category": S, "complexity": I}),
    fn("get_connects_balance", "The freelancer's current Connects balance. No arguments.", {}, []),
    fn("search_evidence", "Search the freelancer's PORTFOLIO for proof of a skill/requirement (case studies, repos, reviews). "
       "Example: {'requirement': 'Airflow DAGs', 'k': 5}", {"requirement": S, "k": I}, ["requirement"]),
    fn("get_case_study", "Full text of one portfolio item by id (e.g. 'ai_ml:cs:recsys').", {"id": S}),
    fn("list_messages", "List the freelancer's client message threads. No arguments.", {}, []),
    fn("free_slots", "Free calendar slots for an interview in the next N days.", {"days": I}, []),
]
FINE = [
    fn("search_jobs_by_keyword", "Search jobs by keyword.", {"keyword": S}),
    fn("search_jobs_by_category", "List jobs in a category.", {"category": S}),
    fn("get_job_title", "Get a job's title.", {"job_id": S}), fn("get_job_description", "Get a job's description.", {"job_id": S}),
    fn("get_job_budget", "Get a job's budget.", {"job_id": S}), fn("get_job_skills", "Get a job's skills.", {"job_id": S}),
    fn("get_job_connects_cost", "Get a job's connects cost.", {"job_id": S}),
    fn("get_client_spend", "Client total spend.", {"client_id": S}), fn("get_client_rating", "Client rating.", {"client_id": S}),
    fn("get_client_payment_status", "Client payment verification.", {"client_id": S}),
    fn("get_price_median", "Median price.", {"category": S, "complexity": I}),
    fn("get_price_quartiles", "Price quartiles.", {"category": S, "complexity": I}),
    fn("get_connects_balance", "Connects balance.", {}, []),
    fn("search_case_studies", "Search case studies.", {"query": S}), fn("search_repos", "Search repos.", {"query": S}),
    fn("search_reviews", "Search reviews.", {"query": S}), fn("get_case_study", "Get case study.", {"id": S}),
    fn("list_threads", "List threads.", {}, []), fn("get_free_slots", "Free slots.", {"days": I}, []),
]
COARSE = [
    fn("marketplace", "Marketplace operations.", {"action": {"type": "string", "enum": [
        "search_jobs", "get_job", "get_client", "market_stats", "connects", "messages"]}, "params": {"type": "object"}}),
    fn("portfolio", "Portfolio and calendar operations.", {"action": {"type": "string", "enum": [
        "search", "get_item", "free_slots"]}, "params": {"type": "object"}}),
]

# (task, best tool, best key args, fine acceptable tools, coarse action)
TASKS = [
    ("Find new jobs about dbt and Snowflake.", "search_jobs", {"query": "dbt"}, {"search_jobs_by_keyword"}, "search_jobs"),
    ("Show me open data-category jobs.", "search_jobs", {"category": "data"}, {"search_jobs_by_category"}, "search_jobs"),
    ("What is the budget of job-0042?", "get_job", {"job_id": "job-0042"}, {"get_job_budget"}, "get_job"),
    ("Read the full post for job-0007.", "get_job", {"job_id": "job-0007"}, {"get_job_description"}, "get_job"),
    ("Which skills does job-0101 need?", "get_job", {"job_id": "job-0101"}, {"get_job_skills"}, "get_job"),
    ("How many Connects does job-0033 cost?", "get_job", {"job_id": "job-0033"}, {"get_job_connects_cost"}, "get_job"),
    ("Is client c017 payment verified?", "get_client_history", {"client_id": "c017"}, {"get_client_payment_status"}, "get_client"),
    ("How much has client c004 spent?", "get_client_history", {"client_id": "c004"}, {"get_client_spend"}, "get_client"),
    ("What rating does client c023 give freelancers?", "get_client_history", {"client_id": "c023"}, {"get_client_rating"}, "get_client"),
    ("Typical price for a complexity-3 AI/ML job?", "get_market_stats", {"category": "ai_ml", "complexity": 3}, {"get_price_median", "get_price_quartiles"}, "market_stats"),
    ("Price range for simple web jobs (complexity 1)?", "get_market_stats", {"category": "web", "complexity": 1}, {"get_price_quartiles", "get_price_median"}, "market_stats"),
    ("How many Connects do I have left?", "get_connects_balance", {}, {"get_connects_balance"}, "connects"),
    ("Do I have proof of Airflow experience?", "search_evidence", {"requirement": "Airflow"}, {"search_case_studies", "search_repos"}, "search"),
    ("Find my work with React Native.", "search_evidence", {"requirement": "React Native"}, {"search_case_studies", "search_repos"}, "search"),
    ("Have I done NER for healthcare?", "search_evidence", {"requirement": "NER"}, {"search_case_studies"}, "search"),
    ("Any client reviews mentioning dashboards?", "search_evidence", {"requirement": "dashboard"}, {"search_reviews"}, "search"),
    ("Do I have code using Celery?", "search_evidence", {"requirement": "Celery"}, {"search_repos"}, "search"),
    ("Open case study ai_ml:cs:recsys.", "get_case_study", {"id": "ai_ml:cs:recsys"}, {"get_case_study"}, "get_item"),
    ("Show the full text of fullstack:cs:lms.", "get_case_study", {"id": "fullstack:cs:lms"}, {"get_case_study"}, "get_item"),
    ("Any new client messages?", "list_messages", {}, {"list_threads"}, "messages"),
    ("When am I free for an interview this week?", "free_slots", {}, {"get_free_slots"}, "free_slots"),
    ("Find free interview times in the next 3 days.", "free_slots", {"days": 3}, {"get_free_slots"}, "free_slots"),
    ("Search jobs mentioning Power BI.", "search_jobs", {"query": "Power BI"}, {"search_jobs_by_keyword"}, "search_jobs"),
    ("List AI/ML jobs.", "search_jobs", {"category": "ai_ml"}, {"search_jobs_by_category"}, "search_jobs"),
    ("Get details of job-0090.", "get_job", {"job_id": "job-0090"}, {"get_job_description", "get_job_title"}, "get_job"),
    ("Is job-0015 worth its Connects? First get the job.", "get_job", {"job_id": "job-0015"}, {"get_job_connects_cost", "get_job_budget"}, "get_job"),
    ("Check history of client c045 before bidding.", "get_client_history", {"client_id": "c045"}, {"get_client_spend", "get_client_rating", "get_client_payment_status"}, "get_client"),
    ("Median price for data jobs of complexity 2.", "get_market_stats", {"category": "data", "complexity": 2}, {"get_price_median"}, "market_stats"),
    ("Prove I know LangGraph.", "search_evidence", {"requirement": "LangGraph"}, {"search_case_studies", "search_repos"}, "search"),
    ("Evidence of Stripe billing work?", "search_evidence", {"requirement": "Stripe"}, {"search_case_studies", "search_repos"}, "search"),
    ("Have I used Tableau?", "search_evidence", {"requirement": "Tableau"}, {"search_case_studies"}, "search"),
    ("Find my A/B testing projects.", "search_evidence", {"requirement": "A/B testing"}, {"search_case_studies"}, "search"),
    ("Read data_analyst:cs:dbt-warehouse.", "get_case_study", {"id": "data_analyst:cs:dbt-warehouse"}, {"get_case_study"}, "get_item"),
    ("What jobs ask for Kubernetes?", "search_jobs", {"query": "Kubernetes"}, {"search_jobs_by_keyword"}, "search_jobs"),
    ("Title of job-0055?", "get_job", {"job_id": "job-0055"}, {"get_job_title"}, "get_job"),
    ("Client c010's reviews from freelancers?", "get_client_history", {"client_id": "c010"}, {"get_client_rating"}, "get_client"),
    ("My Connects balance please.", "get_connects_balance", {}, {"get_connects_balance"}, "connects"),
    ("Do I have reviews praising communication?", "search_evidence", {"requirement": "communication"}, {"search_reviews"}, "search"),
    ("Schedule options for a call in the next 5 days?", "free_slots", {"days": 5}, {"get_free_slots"}, "free_slots"),
    ("Open web jobs about Next.js.", "search_jobs", {"query": "Next.js"}, {"search_jobs_by_keyword"}, "search_jobs"),
]


def args_ok(expected: dict, got: dict) -> bool:
    for k, v in expected.items():
        gv = got.get(k) if k in got else next((x for x in got.values() if isinstance(x, (str, int))), None)
        if isinstance(v, str) and (not isinstance(gv, str) or v.lower() not in gv.lower()):
            return False
        if isinstance(v, int) and str(v) != str(gv):
            return False
    return True


def run(set_name: str, tools: list) -> dict:
    rows = []
    for task, best, exp, fine_ok, coarse_action in TASKS:
        msgs = [{"role": "system", "content": "You are a freelancer's assistant. Call exactly one tool to make progress on the request."},
                {"role": "user", "content": task}]
        t0 = time.time()
        try:
            out = chat(MODEL, msgs, node=f"toolA_{set_name}", temperature=0, tools=tools, max_tokens=400)
        except LLMUnavailable as e:
            rows.append({"task": task, "error": str(e)[:100], "sel": False, "args": False, "tokens": 0})
            continue
        calls = out["tool_calls"]
        name = calls[0]["function"]["name"] if calls else None
        try:
            got = json.loads(calls[0]["function"]["arguments"]) if calls else {}
        except (ValueError, KeyError):
            got = {}
        if set_name == "best":
            sel, aok = name == best, name == best and args_ok(exp, got)
        elif set_name == "fine":
            sel = name in fine_ok
            aok = sel and args_ok({k: v for k, v in exp.items() if k in ("job_id", "client_id", "id", "category")} or
                                  {"q": list(exp.values())[0]} if exp else {}, got)
        else:
            act = got.get("action")
            params = got.get("params") or {}
            sel = act == coarse_action
            aok = sel and args_ok(exp, params)
        u = out["usage"]
        rows.append({"task": task, "called": name, "args_got": got, "sel": sel, "args": aok,
                     "tokens": u.get("prompt_tokens", 0) + u.get("completion_tokens", 0), "latency": round(time.time() - t0, 2)})
    return {"n_tasks": len(rows), "n_tools": len(tools), "tool_selection_accuracy": mean([r["sel"] for r in rows]),
            "argument_accuracy": mean([r["args"] for r in rows]), "tokens_per_task": mean([r["tokens"] for r in rows]), "rows": rows}


def main():
    res = {name: run(name, tools) for name, tools in (("fine", FINE), ("coarse", COARSE), ("best", BEST))}
    for k, v in res.items():
        print(k, {m: v[m] for m in ("n_tools", "tool_selection_accuracy", "argument_accuracy", "tokens_per_task")})
    write("tool_granularity", {"model": MODEL, "hypothesis": "Fewer, well-described tools raise selection and argument "
                               "accuracy and cut tokens per task versus many fine-grained tools; catch-all tools lose argument accuracy.",
                               "sets": res})


if __name__ == "__main__":
    main()
