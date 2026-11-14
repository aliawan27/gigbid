"""Blind pairwise human panel (B4).
  build:   python evals/runners/pairwise_panel.py build    -> evals/datasets/pairwise_pairs.json
           pairs of proposals for the SAME job from two configurations (shipped vs V0 retrieval, writer A vs B,
           gpt-oss-120b vs qwen writer). Raters see them anonymised, in random left/right order, at /panel.
  analyse: python evals/runners/pairwise_panel.py analyse  -> evals/results/pairwise_panel.json
           reads the votes (app DB), win rate per comparison + exact two-sided sign test (ties excluded)."""
from __future__ import annotations

import json
import math
import sys

from _common import JOBS, ROOT, write

PAIRS = ROOT / "evals" / "datasets" / "pairwise_pairs.json"
COMPARISONS = [("best_open", "v0_open", "shipped retrieval vs naive V0 retrieval"),
               ("best_open_B", "best_open", "writer B (question-led) vs writer A (evidence-led)"),
               ("best_open", "best_qwen", "gpt-oss-120b writer vs qwen3.8-27b writer")]


def build():
    cfg = json.loads((ROOT / "evals" / "results" / "gigsim_outcomes.json").read_text())["configs"]
    letters = {k: {r["job_id"]: r["letter"] for r in v["rows"] if r.get("letter")} for k, v in cfg.items()}
    pairs = []
    for a, b, label in COMPARISONS:
        for job_id in sorted(set(letters[a]) & set(letters[b])):
            j = JOBS[job_id]
            pairs.append({"pair_id": f"{a}__{b}__{job_id}", "comparison": label, "a_config": a, "b_config": b,
                          "job_id": job_id, "job_title": j["title"], "job_description": j["description"][:700],
                          "a_text": letters[a][job_id], "b_text": letters[b][job_id]})
    PAIRS.write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    print(f"wrote {len(pairs)} pairs to {PAIRS}")


def sign_test(wins: int, losses: int) -> float:
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return round(min(1.0, 2 * p), 4)


def analyse():
    sys.path.insert(0, str(ROOT))
    from apps.api import db
    votes = db.rows(db.select(db.panel_votes))
    pairs = {p["pair_id"]: p for p in json.loads(PAIRS.read_text(encoding="utf-8"))}
    out = {}
    for a, b, label in COMPARISONS:
        vs = [v for v in votes if pairs.get(v["pair_id"], {}).get("a_config") == a and pairs[v["pair_id"]]["b_config"] == b]
        wa = sum(v["winner"] == "a" for v in vs)
        wb = sum(v["winner"] == "b" for v in vs)
        ties = sum(v["winner"] == "tie" for v in vs)
        out[label] = {"a": a, "b": b, "votes": len(vs), "a_wins": wa, "b_wins": wb, "ties": ties,
                      "a_win_rate_excl_ties": round(wa / (wa + wb), 3) if wa + wb else None,
                      "sign_test_p_two_sided": sign_test(wa, wb)}
    raters = len({v["rater"] for v in votes})
    res = {"n_votes": len(votes), "n_raters": raters, "comparisons": out,
           "method": "blind: raters never see configuration names; left/right order randomised per view"}
    print(json.dumps(res, indent=1))
    write("pairwise_panel", res)


if __name__ == "__main__":
    {"build": build, "analyse": analyse}[sys.argv[1] if len(sys.argv) > 1 else "build"]()
