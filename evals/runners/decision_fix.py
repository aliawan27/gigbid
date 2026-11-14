"""Failure-analysis fix checks on the analyses recorded in evals/results/decisions.json (no new LLM calls; exact because the
decision rule is deterministic given fit, risk, budget and floor).
1. budget-floor ratio (wrong skips of good jobs)   2. bid fit threshold (off-domain jobs bid on)"""
from __future__ import annotations

import json
import re

from _common import RESULTS, f1

d = json.loads((RESULTS / "decisions.json").read_text())
FLOOR = re.compile(r"budget \$(\d+) is below your floor \(~\$(\d+)")


def rescore(ratio: float, fit_th: float = 0.55) -> dict:
    preds = []
    for r in d["rows"]:
        p = r["pred"]
        m = FLOOR.search(r.get("reason") or "")
        floor_ok = (not m) or int(m.group(1)) >= ratio * int(m.group(2))
        if p == "bid" or m:
            ok = (r.get("fit") or 0) >= fit_th and (r.get("risk") or 0) <= 0.6 and floor_ok
            p = "bid" if ok else "skip"
        preds.append((p, r["gold"], r["kind"]))
    tp = sum(p == "bid" and g == "bid" for p, g, _ in preds)
    fp = sum(p == "bid" and g != "bid" for p, g, _ in preds)
    fn = sum(p != "bid" and g == "bid" for p, g, _ in preds)
    return {"min_rate_floor_ratio": ratio, "bid_fit_score": fit_th, "bid_skip_f1": round(f1(tp, fp, fn), 3),
            "lowball_jobs_bid_on": sum(p == "bid" and k == "lowball" for p, _, k in preds),
            "off_domain_jobs_bid_on": sum(p == "bid" and k == "off" for p, _, k in preds),
            "good_jobs_missed": sum(p != "bid" and g == "bid" for p, g, _ in preds),
            "accuracy": round(sum((p == "bid") == (g == "bid") for p, g, _ in preds) / len(preds), 3)}


d["fix_tried_floor_ratio"] = [rescore(x) for x in (0.8, 0.7, 0.55, 0.4, 0.25)]
d["fix_tried_fit_threshold"] = [rescore(0.55, t) for t in (0.55, 0.7, 0.75, 0.8)]
for x in d["fix_tried_floor_ratio"] + d["fix_tried_fit_threshold"]:
    print(x)
(RESULTS / "decisions.json").write_text(json.dumps(d, indent=1, default=str))
