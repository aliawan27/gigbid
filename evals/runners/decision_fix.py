"""Failure-analysis fix check: re-apply the (deterministic) budget-floor rule with a lower min_rate_floor_ratio to the
analyses recorded in evals/results/decisions.json (no new LLM calls; exact because the rule is deterministic)."""
from __future__ import annotations

import json
import re

from _common import RESULTS, f1

d = json.loads((RESULTS / "decisions.json").read_text())
FLOOR = re.compile(r"budget \$(\d+) is below your floor \(~\$(\d+)")


def rescore(ratio: float) -> dict:
    preds = []
    for r in d["rows"]:
        p = r["pred"]
        m = FLOOR.search(r.get("reason") or "")
        if m and int(m.group(1)) >= ratio * int(m.group(2)):
            p = "bid" if (r.get("fit") or 0) >= 0.55 and (r.get("risk") or 0) <= 0.6 else ("watch" if (r.get("fit") or 0) >= 0.4 else "skip")
        preds.append((p, r["gold"], r["kind"]))
    tp = sum(p == "bid" and g == "bid" for p, g, _ in preds)
    fp = sum(p == "bid" and g != "bid" for p, g, _ in preds)
    fn = sum(p != "bid" and g == "bid" for p, g, _ in preds)
    lowball_bids = sum(p == "bid" and k == "lowball" for p, _, k in preds)
    return {"min_rate_floor_ratio": ratio, "bid_skip_f1": round(f1(tp, fp, fn), 3), "lowball_jobs_bid_on": lowball_bids,
            "accuracy": round(sum((p == "bid") == (g == "bid") for p, g, _ in preds) / len(preds), 3)}


res = [rescore(x) for x in (0.8, 0.7, 0.55, 0.4, 0.25)]
for x in res:
    print(x)
d["fix_tried_floor_ratio"] = res
(RESULTS / "decisions.json").write_text(json.dumps(d, indent=1, default=str))
