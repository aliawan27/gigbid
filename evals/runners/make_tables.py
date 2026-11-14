"""Regenerates the results tables (README + report) from evals/results/*.json -> evals/results/tables.md"""
from __future__ import annotations

import json
import math

from _common import RESULTS


def load(name):
    p = RESULTS / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def f(x, d=3):
    if x is None:
        return "—"
    return f"{x:.{d}f}" if isinstance(x, float) else str(x)


def fisher_two_sided(a, b, c, d):
    """Fisher exact test for [[a,b],[c,d]] (successes/failures of A and B)."""
    n1, n2, k, n = a + b, c + d, a + c, a + b + c + d

    def p(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(n, k)
    obs = p(a)
    return round(sum(p(x) for x in range(max(0, k - n2), min(k, n1) + 1) if p(x) <= obs + 1e-12), 4)


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    out = []
    rag, outc, dec, tools, cmp_, inj, jc = (load(n) for n in ("rag_variants", "gigsim_outcomes", "decisions", "tool_granularity",
                                                              "agent_comparison", "injection", "judge_calibration"))
    if rag and outc:
        o = outc["configs"]
        out.append("### B5 results table (dev set)\n")
        out.append("| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal (after verification) | Judge score (1-5) | GigSim reply rate | p95 latency / proposal (s) | Cost / proposal (USD) |")
        out.append("|---|---|---|---|---|---|---|---|")
        for label, var, cfg in (("V0 (naive dense)", "v0_naive", "v0_open"), ("Your best (V5 + hybrid, shipped)", "best", "best_open")):
            v, s = rag["variants"][var], (o.get(cfg) or {}).get("summary", {})
            out.append(f"| {label} | {f(v['recall@5'])} | {f(v['ndcg@10'])} | {f(s.get('unsupported_claims_per_proposal_after'), 2)} "
                       f"| {f(s.get('judge_score'), 2)} | {f(s.get('reply_rate'))} | {f(s.get('p95_latency_s_per_proposal'), 1)} | {f(s.get('usd_per_proposal'), 4)} |")
    if rag:
        out.append("\n### All retrieval variants\n")
        out.append("| Variant | Recall@5 | MRR | nDCG@10 | multi-req R@5 | vague R@5 | p95 query latency (s) |")
        out.append("|---|---|---|---|---|---|---|")
        for k, v in rag["variants"].items():
            bt = v["by_job_type"]
            out.append(f"| {k} | {f(v['recall@5'])} | {f(v['mrr'])} | {f(v['ndcg@10'])} | {f(bt.get('multi_req(>=4)', {}).get('recall@5'))} "
                       f"| {f(bt.get('vague', {}).get('recall@5'))} | {f(v['p95_latency_s'])} |")
        out.append("\n**Ablation of the shipped pipeline**\n\n| Change | Recall@5 | nDCG@10 |\n|---|---|---|")
        out.append(f"| shipped (V5 + hybrid) | {f(rag['variants']['best']['recall@5'])} | {f(rag['variants']['best']['ndcg@10'])} |")
        for k, v in rag["ablation_of_best"].items():
            out.append(f"| {k} | {f(v['recall@5'])} | {f(v['ndcg@10'])} |")
        out.append("\n**By persona (shipped)**\n\n| Persona | Recall@5 | nDCG@10 |\n|---|---|---|")
        for p, v in rag["variants"]["best"]["by_persona"].items():
            out.append(f"| {p} | {f(v['recall@5'])} | {f(v['ndcg@10'])} |")
    if outc:
        out.append("\n### Proposal configurations on the fixed GigSim job set\n")
        out.append("| Config | Submitted | Unsupported claims before → after | Judge | Reply rate | Hire rate | p50 / p95 latency (s) | USD / proposal | Revisions |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for k, c in outc["configs"].items():
            s = c["summary"]
            out.append(f"| {k} | {s['n_submitted']}/{s['n_jobs']} | {f(s['unsupported_claims_per_proposal_before'], 2)} → {f(s['unsupported_claims_per_proposal_after'], 2)} "
                       f"| {f(s['judge_score'], 2)} | {f(s['reply_rate'])} | {f(s['hire_rate'])} | {f(s['p50_latency_s_per_proposal'], 1)} / {f(s['p95_latency_s_per_proposal'], 1)} "
                       f"| {f(s['usd_per_proposal'], 4)} | {f(s['mean_revisions'], 2)} |")
        a, b = outc["configs"].get("best_open"), outc["configs"].get("best_open_B")
        if a and b:
            def cnt(rows):
                sub = [r for r in rows if r.get("marketplace_status")]
                return sum(r["marketplace_status"] in ("replied", "interview", "hired") for r in sub), len(sub)
            (ra, na), (rb, nb) = cnt(a["rows"]), cnt(b["rows"])
            pv = fisher_two_sided(ra, na - ra, rb, nb - rb)
            out.append(f"\n**X2 A/B test** — A (evidence-led) {ra}/{na} replies vs B (question-led) {rb}/{nb}; Fisher exact two-sided p = {pv}.")
            (RESULTS / "ab_test.json").write_text(json.dumps({"A_replies": ra, "A_n": na, "B_replies": rb, "B_n": nb,
                                                              "fisher_p_two_sided": pv}, indent=1))
    if dec:
        out.append("\n### Decisions (all dev jobs)\n")
        out.append("| Slice | n | Bid/skip F1 | Accuracy | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) | USD / job |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for k, m in [("overall", dec["overall"])] + list(dec["by_persona"].items()) + list(dec["by_kind"].items()):
            out.append(f"| {k} | {m['n']} | {f(m['bid_skip_f1'])} | {f(m['accuracy'])} | {f(m['scam_precision'])} | {f(m['scam_recall'])} "
                       f"| {f(m['price_in_fair_band'])} | {f(m['p95_latency_s_per_job'], 1)} | {f(m['mean_usd_per_job'], 5)} |")
    if tools:
        out.append("\n### R&D A — tool granularity (40 tasks)\n\n| Tool set | Tools | Selection accuracy | Argument accuracy | Tokens / task |\n|---|---|---|---|---|")
        for k, s in tools["sets"].items():
            out.append(f"| {k} | {s['n_tools']} | {f(s['tool_selection_accuracy'])} | {f(s['argument_accuracy'])} | {f(s['tokens_per_task'], 0)} |")
    if cmp_:
        out.append("\n### R&D C — single agent vs supervisor vs graph\n")
        out.append("| System | Jobs | Failed runs | Bid/skip accuracy | Scam jobs bid on | Unsupported claims / proposal | Violations caught by guard | Violations left in output | Reply rate | Tokens / job | p50 / p95 latency (s) |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for k, c in cmp_["systems"].items():
            s = c["summary"]
            nerr = sum(r.get("pred") == "error" for r in c["rows"])
            out.append(f"| {k} | {s['n']} | {nerr} | {f(s['bid_skip_accuracy'])} | {f(s['scam_bid_rate'])} | {f(s['unsupported_claims_per_proposal'], 2)} "
                       f"| {s['violations_caught_by_guard']} | {s['violations_left_in_output']} | {f(s['reply_rate'])} | {f(s['tokens_per_job'], 0)} "
                       f"| {f(s['p50_latency_s'], 1)} / {f(s['p95_latency_s'], 1)} |")
    if inj:
        out.append(f"\n### Injection defence\n\nAttack success rate **{inj['attack_success_rate_before']}** before defences → "
                   f"**{inj['attack_success_rate_after']}** after ({inj['n_attacks']} attacks: planted job posts + client messages); detection rate {inj['detection_rate']}.")
    if jc and jc.get("status") == "done":
        out.append(f"\n### Judge calibration\n\nCohen's kappa (quadratic) **{jc['cohen_kappa_quadratic']}**, exact agreement {jc['exact_agreement']}, "
                   f"within ±1 {jc['within_one']} on {jc['n']} human-labelled proposals.")
    text = "\n".join(out) + "\n"
    (RESULTS / "tables.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
