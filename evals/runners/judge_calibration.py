"""Judge calibration (B4): 30 proposals labelled by the student (1-5, same rubric as agent/prompts/judge.md) vs the
LLM judge -> Cohen's kappa (quadratic weighted) + exact agreement + the disagreements.
Step 1 (automatic): writes evals/datasets/judge_labels.csv with a blank human_score column (judge scores hidden).
Step 2 (human): fill human_score for all 30 rows.  Step 3: re-run this script to compute kappa."""
from __future__ import annotations

import csv
import json

from _common import ROOT, write

LABELS = ROOT / "evals" / "datasets" / "judge_labels.csv"
JUDGE = ROOT / "evals" / "datasets" / "judge_scores_hidden.json"


def kappa(a: list[int], b: list[int], k: int = 5, weighted: bool = True) -> float:
    n = len(a)
    O = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        O[x - 1][y - 1] += 1
    ra = [sum(r) for r in O]
    cb = [sum(O[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2 / (k - 1) ** 2) if weighted else (0.0 if i == j else 1.0)
            num += w * O[i][j]
            den += w * ra[i] * cb[j] / n
    return round(1 - num / den, 3) if den else 1.0


def build():
    data = json.loads((ROOT / "evals" / "results" / "gigsim_outcomes.json").read_text())
    rows = []
    for tag, c in data["configs"].items():
        for r in c["rows"]:
            if r.get("letter") and (r.get("judge") or {}).get("score"):
                rows.append((tag, r))
    rows = rows[:30]
    hidden = {}
    with LABELS.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "job_id", "job_title", "proposal", "human_score"])
        for i, (tag, r) in enumerate(rows, 1):
            from _common import JOBS
            w.writerow([i, r["job_id"], JOBS[r["job_id"]]["title"], r["letter"], ""])
            hidden[str(i)] = {"judge": r["judge"]["score"], "config": tag, "reason": r["judge"]["reason"]}
    JOBS_ = None  # noqa: F841
    JUDGE.write_text(json.dumps(hidden, indent=1))
    print(f"wrote {LABELS} — fill the human_score column (1-5) for all rows, then re-run")


def main():
    if not LABELS.exists() or not JUDGE.exists():
        return build()
    hidden = json.loads(JUDGE.read_text())
    with LABELS.open(encoding="utf-8-sig") as f:  # Excel adds a BOM
        rows = [r for r in csv.DictReader(f) if r["human_score"].strip()]
    if len(rows) < 10:
        write("judge_calibration", {"status": "pending_human_labels", "labelled": len(rows),
                                    "instructions": "fill human_score in evals/datasets/judge_labels.csv and re-run"})
        return
    h = [int(r["human_score"]) for r in rows]
    j = [int(hidden[r["item"]]["judge"]) for r in rows]
    dis = [{"item": r["item"], "job": r["job_title"], "human": a, "judge": b, "judge_reason": hidden[r["item"]]["reason"],
            "proposal": r["proposal"][:400]} for r, a, b in zip(rows, h, j) if abs(a - b) >= 2]
    annot = sorted({r.get("annotator") or "student" for r in rows})
    out = {"status": "done", "reference_annotator": annot, "n": len(rows), "cohen_kappa_quadratic": kappa(h, j), "cohen_kappa_unweighted": kappa(h, j, weighted=False),
           "exact_agreement": round(sum(a == b for a, b in zip(h, j)) / len(h), 3),
           "within_one": round(sum(abs(a - b) <= 1 for a, b in zip(h, j)) / len(h), 3),
           "mean_human": round(sum(h) / len(h), 2), "mean_judge": round(sum(j) / len(j), 2), "big_disagreements": dis}
    print({k: v for k, v in out.items() if k != "big_disagreements"})
    write("judge_calibration", out)


if __name__ == "__main__":
    main()
