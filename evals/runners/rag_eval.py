"""B2/B4 retrieval evaluation + ablation: Recall@5, MRR, nDCG@10 per variant, per persona and per job type.
Gold = evidence items of the project(s) each dev job was built from. Run: python evals/runners/rag_eval.py"""
from __future__ import annotations

import time
from dataclasses import replace

from _common import JOBS, PERSONAS, dev, mean, ndcg_at, mrr, pct, public_job, recall_at, write

from rag.variants.base import Pipeline, load_variant

VARIANTS = ["v0_naive", "v1_decompose", "v2_hybrid", "v3_rerank", "v4_outcome", "v5_multivector", "v8_corrective", "best"]
HYPOTHESIS = ("Requirement decomposition plus hybrid BM25+dense retrieval raises evidence Recall@5 by >= 15 points over "
              "V0 on jobs with four or more requirements.")


def job_type(j: dict) -> str:
    if len(j["description"]) < 200:
        return "vague"
    return "multi_req(>=4)" if len(j["skills"]) >= 4 else "few_req(<4)"


def evaluate(pipe: Pipeline, items: list[tuple[str, dict, set]]) -> dict:
    rows = []
    for persona, job, gold in items:
        t0 = time.time()
        res = pipe.search(persona, job=public_job(job), k=10)
        lat = time.time() - t0
        ranked = [r["id"] for r in res]
        rows.append({"persona": persona, "job_id": job["job_id"], "type": job_type(job), "r5": recall_at(ranked, gold, 5),
                     "mrr": mrr(ranked, gold), "ndcg10": ndcg_at(ranked, gold, 10), "lat": lat})

    def agg(rs):
        return {"n": len(rs), "recall@5": mean(r["r5"] for r in rs), "mrr": mean(r["mrr"] for r in rs),
                "ndcg@10": mean(r["ndcg10"] for r in rs), "p95_latency_s": pct([r["lat"] for r in rs], 0.95)}
    out = agg(rows)
    out["by_persona"] = {p: agg([r for r in rows if r["persona"] == p]) for p in PERSONAS}
    out["by_job_type"] = {t: agg([r for r in rows if r["type"] == t]) for t in sorted({r["type"] for r in rows})}
    return out


def main():
    items = []
    for p in PERSONAS:
        for g in dev(p):
            if g["decision"] == "bid" or g["kind"] == "lowball":
                items.append((p, JOBS[g["job_id"]], set(g["evidence"])))
    results = {v: evaluate(load_variant(v), items) for v in VARIANTS}
    for v, r in results.items():
        print(f"{v:16} R@5 {r['recall@5']:.3f}  MRR {r['mrr']:.3f}  nDCG@10 {r['ndcg@10']:.3f}")
    # ablation of the shipped pipeline: remove one component at a time
    best = load_variant("best").cfg
    ablation = {}
    for comp, change in [("-multivector", {"chunking": "structural"}), ("-hybrid", {"hybrid": False}),
                         ("+decompose", {"decompose": True}),
                         ("+outcome_boost", {"outcome_boost": 1.0}), ("+rerank", {"rerank": True})]:
        ablation[comp] = evaluate(Pipeline(replace(best, name=f"best{comp}", **change)), items)
        print(f"ablation {comp:15} R@5 {ablation[comp]['recall@5']:.3f}  nDCG@10 {ablation[comp]['ndcg@10']:.3f}")
    v0m = results["v0_naive"]["by_job_type"].get("multi_req(>=4)", {}).get("recall@5") or 0
    bm = results["best"]["by_job_type"].get("multi_req(>=4)", {}).get("recall@5") or 0
    write("rag_variants", {"hypothesis": HYPOTHESIS, "n_jobs": len(items), "variants": results, "ablation_of_best": ablation,
                           "hypothesis_check": {"v0_recall@5_multi_req": v0m, "best_recall@5_multi_req": bm,
                                                "delta_points": round(100 * (bm - v0m), 1), "supported": (bm - v0m) >= 0.15}})


if __name__ == "__main__":
    main()
