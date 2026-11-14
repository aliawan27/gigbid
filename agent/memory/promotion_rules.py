"""R7 explicit promotion rules. Nothing reaches long-term memory except through these functions.

STYLE memory (namespace ("style", user)):
  An edit the user makes in the approval screen is diffed into *candidate* patterns
  (removed phrase / cut first sentence / made shorter). A candidate is PROMOTED to a style rule only when
  the same pattern is seen in >= STYLE_MIN_OCCURRENCES separate approved edits. One-off edits never leak.

OUTCOME memory (namespace ("outcome", user)):
  Updated ONLY from marketplace-confirmed proposal status changes (replied / interview / hired / ignored),
  never from raw tool output or model text. Per job category we keep counts; a category "lesson"
  (which evidence projects and openings got replies) is promoted only when n_submitted >= OUTCOME_MIN_N.
"""
from __future__ import annotations

import difflib
import re

STYLE_MIN_OCCURRENCES = 2
OUTCOME_MIN_N = 3
POSITIVE = {"replied", "interview", "hired"}


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def style_candidates(original: str, edited: str) -> list[dict]:
    """Diff an approved edit into candidate style patterns."""
    cands = []
    o_s, e_s = _sentences(original), _sentences(edited)
    if o_s and e_s and o_s[0] not in edited and o_s[1:2] and o_s[1][:40] in edited:
        cands.append({"key": "cut_first_sentence", "rule": "Cut the generic first sentence; open with the client's problem."})
    o_words, e_words = original.split(), edited.split()
    if len(e_words) < 0.8 * len(o_words):
        cands.append({"key": "shorter", "rule": f"Keep cover letters short (about {max(60, len(e_words) // 10 * 10)} words)."})
    sm = difflib.SequenceMatcher(None, o_words, e_words)
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and 1 <= i2 - i1 <= 4:
            phrase = " ".join(o_words[i1:i2]).strip(".,;:!").lower()
            if len(phrase) > 3:
                cands.append({"key": f"avoid:{phrase}", "rule": f"Never say \"{phrase}\"."})
    return cands


def promote_style(candidate_counts: dict[str, int]) -> list[str]:
    return [k for k, n in candidate_counts.items() if n >= STYLE_MIN_OCCURRENCES]


def outcome_update(stats: dict, status: str, proposal_meta: dict) -> dict:
    """stats = {'n_submitted', 'n_positive', 'positive_examples': [...], 'evidence_projects': {project: n}}"""
    stats = dict(stats or {"n_submitted": 0, "n_positive": 0, "positive_examples": [], "evidence_projects": {}})
    stats["n_submitted"] += 1
    if status in POSITIVE:
        stats["n_positive"] += 1
        stats["positive_examples"] = (stats["positive_examples"] + [{"job_id": proposal_meta.get("job_id"),
                                       "opening": proposal_meta.get("opening", "")[:200], "status": status}])[-5:]
        for p in proposal_meta.get("projects", []):
            stats["evidence_projects"][p] = stats["evidence_projects"].get(p, 0) + 1
    stats["promoted"] = stats["n_submitted"] >= OUTCOME_MIN_N
    return stats
