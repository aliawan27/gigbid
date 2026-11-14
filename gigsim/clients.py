"""Simulated client behaviour. Each client has hidden preferences; an LLM decides reply/interview/hire,
with a deterministic heuristic fallback (also used when GIGSIM_CLIENT_LLM=0 for cheap, reproducible runs)."""
from __future__ import annotations

import hashlib
import json
import os
import re

GENERIC = re.compile(r"dear sir|madam|passionate|hardworking|hard-working|to whom it may concern|i am the best", re.I)


def _rand(*parts) -> float:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def heuristic(job: dict, client: dict, letter: str, bid: float) -> dict:
    hid, jh = client["_hidden"], job["_hidden"]
    low = letter.lower()
    score = 0.25
    if all(m.lower() in low for m in jh.get("must_have", [])):
        score += 0.25
    else:
        score -= 0.1
    if GENERIC.search(letter):
        score -= 0.3 if hid["dislikes_generic"] else 0.1
    if re.search(r"\d", letter):
        score += 0.1  # concrete numbers / outcomes
    if job["budget"] and bid > job["budget"] * hid["budget_ceiling_mult"]:
        score -= 0.25
    if hid["prefers_short"] and len(letter) > 1500:
        score -= 0.1
    r = _rand(job["job_id"], letter[:200], bid)
    if r > score:
        return {"status": "ignored", "reason": "heuristic", "reply": ""}
    stage = "hired" if r < score * 0.25 else "interview" if r < score * 0.55 else "replied"
    replies = {
        "replied": "Thanks for your proposal. Can you tell me more about how you would approach the first milestone?",
        "interview": "Your proposal stood out. Could we schedule a 30-minute call this week? What times work for you?",
        "hired": "We'd like to move forward with you. Could you confirm your availability to start and a first milestone?",
    }
    return {"status": stage, "reason": "heuristic", "reply": replies[stage]}


def decide(job: dict, client: dict, letter: str, bid: float) -> dict:
    if client["_hidden"].get("scam"):
        return {"status": "replied", "reason": "scam client",
                "reply": "Great! Let's continue on Telegram @fastjobs, I will pay you in crypto there."}
    if os.getenv("GIGSIM_CLIENT_LLM", "1") != "1":
        return heuristic(job, client, letter, bid)
    try:
        from agent.llm import chat, _extract_json
        prefs = {"must_have_skills": job["_hidden"].get("must_have"), "dislikes_generic_openings": client["_hidden"]["dislikes_generic"],
                 "prefers_short_proposals": client["_hidden"]["prefers_short"],
                 "max_acceptable_bid": round(job["budget"] * client["_hidden"]["budget_ceiling_mult"])}
        sys = ("You simulate a client on a freelance marketplace who receives many proposals and replies to few "
               "(about 1 in 4 good ones). Judge the proposal against your hidden preferences. Be strict: generic, "
               "unspecific or over-budget proposals get ignored. Return JSON {\"status\": one of "
               "ignored|replied|interview|hired, \"reason\": short, \"reply\": message to freelancer or empty}.")
        user = (f"JOB: {job['title']}\n{job['description'][:1200]}\nBUDGET: ${job['budget']}\n"
                f"HIDDEN PREFERENCES: {json.dumps(prefs)}\nBID: ${bid}\nPROPOSAL:\n<<<{letter[:3000]}>>>")
        out = chat(os.getenv("GIGSIM_CLIENT_MODEL", "openai/gpt-oss-20b"),
                   [{"role": "system", "content": sys}, {"role": "user", "content": user}],
                   node="gigsim_client", temperature=0, json_mode=True, max_tokens=400)
        d = _extract_json(out["content"])
        if d.get("status") not in ("ignored", "replied", "interview", "hired"):
            raise ValueError("bad status")
        if d["status"] != "ignored" and not d.get("reply"):
            d["reply"] = "Thanks for applying. Could you share more details on your approach?"
        return d
    except Exception:  # noqa: BLE001
        return heuristic(job, client, letter, bid)
