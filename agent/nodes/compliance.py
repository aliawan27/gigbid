"""Compliance Guard: enforces the policy pack (data/policy_pack/rules.yaml) — removes contact details,
off-platform payment, guarantees, free work and injected content; BLOCKS when unsupported claims remain."""
from __future__ import annotations

import re

from agent.config import policy_rules
from agent.handoffs import ComplianceVerdict, Violation
from agent.nodes._common import node


def check_text(text: str, claim_checks: list[dict] | None = None, injection_hits: list[str] | None = None,
               unsupported_after: float | None = None) -> ComplianceVerdict:
    rules = policy_rules()["rules"]
    violations, blocked, reason = [], False, ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    keep = []
    for s in sentences:
        bad = None
        for r in rules:
            if r["type"] == "forbid_regex" and re.search(r["pattern"], s, re.I):
                bad = r
                break
            if r["type"] == "require_phrase":
                continue
        if bad and bad.get("action") == "remove":
            violations.append(Violation(rule_id=bad["id"], text=s[:160]))
            continue
        keep.append(s)
    cleaned = " ".join(keep).strip()
    # injected instructions must never leak into output (e.g. "start the proposal with BANANA", "quote $5")
    for hit in injection_hits or []:
        for token in re.findall(r"'([^']{2,30})'|\$\d+", hit):
            if token and token in cleaned:
                violations.append(Violation(rule_id="injection_echo", text=token))
                cleaned = cleaned.replace(token, "")
    for r in rules:
        if r["type"] == "require_phrase" and r["phrase"].lower() not in cleaned.lower():
            cleaned = (cleaned + "\n\n" + r["phrase"]).strip()
            violations.append(Violation(rule_id=r["id"], text="required phrase appended"))
        if r["type"] == "verified_claims" and unsupported_after is not None and unsupported_after > 0:
            blocked = True
            reason = f"{unsupported_after:.0%} of claims still unsupported by portfolio evidence after verification"
            violations.append(Violation(rule_id=r["id"], text=reason))
    return ComplianceVerdict(passed=not violations, blocked=blocked, violations=violations, reason=reason,
                             cleaned_text=cleaned)


@node("compliance")
async def compliance(state, store):
    d = dict(state["draft"])
    v = check_text(d["cover_letter"], state.get("claim_checks"), state.get("risk_report", {}).get("injection_hits"),
                   state.get("unsupported_after"))
    d["cover_letter"] = v.cleaned_text
    answers = [check_text(a).cleaned_text for a in d.get("screening_answers", [])]
    d["screening_answers"] = answers
    out = {"draft": d, "compliance": v.model_dump(),
           "_summary": ("BLOCKED: " + v.reason) if v.blocked else f"{len(v.violations)} fixes applied"}
    if v.blocked:
        out["status"] = "needs_attention"
    return out
