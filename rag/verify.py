"""Claim verification (B3): split a draft into claims, check each against retrieved evidence, label it
supported / partial / unsupported, and remove or rewrite unsupported claims before the Critic sees the draft."""
from __future__ import annotations

import re

from pydantic import BaseModel

from agent.config import model_for
from agent.llm import LLMUnavailable, structured

CLAIMY = re.compile(r"\b(I|I've|I have|I'm|my|we|built|delivered|developed|led|created|designed|achieved|reduced|"
                    r"increased|improved|years|experience|worked)\b", re.I)


class ClaimCheck(BaseModel):
    claim: str
    label: str  # supported | partial | unsupported
    evidence_ids: list[str] = []
    rewrite: str = ""


class Verification(BaseModel):
    claims: list[ClaimCheck]


def split_claims(text: str) -> list[str]:
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]
    return [s for s in sents if CLAIMY.search(s) and len(s.split()) > 3]


def _lexical(claim: str, evidence: list[dict]) -> ClaimCheck:
    toks = {t for t in re.findall(r"[a-z0-9.+#-]{3,}", claim.lower())} - {"the", "and", "for", "with", "have", "your", "that", "this", "built", "which"}
    best, ids = 0.0, []
    for e in evidence:
        et = (e.get("snippet", "") + " " + " ".join(e.get("skills") or []) + " " + (e.get("title") or "")).lower()
        ov = sum(1 for t in toks if t in et) / max(1, len(toks))
        if ov > best:
            best, ids = ov, [e["id"]]
    label = "supported" if best >= 0.5 else "partial" if best >= 0.3 else "unsupported"
    return ClaimCheck(claim=claim, label=label, evidence_ids=ids if label != "unsupported" else [])


def verify(text: str, evidence: list[dict]) -> list[ClaimCheck]:
    claims = split_claims(text)
    if not claims:
        return []
    listing = "\n".join(f"[{e['id']}] {e.get('title')}: {e.get('snippet', '')[:300]}" for e in evidence[:12])
    try:
        res = structured(model_for("verifier"),
                         "You are a strict fact checker. For each CLAIM decide if the EVIDENCE supports it: 'supported' "
                         "(evidence states it), 'partial' (related but overstated/specifics missing), 'unsupported' (no "
                         "evidence). Generic statements of intent ('I would start by...') are 'supported'. For partial or "
                         "unsupported claims give a 'rewrite' that only says what the evidence supports, or empty string "
                         "to delete. Cite evidence ids.",
                         "EVIDENCE:\n" + listing + "\n\nCLAIMS:\n" + "\n".join(f"- {c}" for c in claims),
                         Verification, node="verifier", max_tokens=1800)
        return res.claims
    except LLMUnavailable:
        return [_lexical(c, evidence) for c in claims]


def apply_fixes(text: str, checks: list[ClaimCheck]) -> str:
    for c in checks:
        if c.label in ("unsupported", "partial") and c.claim in text:
            text = text.replace(c.claim, c.rewrite.strip() if c.label == "partial" or c.rewrite else "")
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def unsupported_rate(checks: list[ClaimCheck]) -> float:
    return sum(c.label == "unsupported" for c in checks) / max(1, len(checks))
