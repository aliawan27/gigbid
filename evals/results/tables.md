### B5 results table (dev set)

| Variant | Evidence Recall@5 | nDCG@10 | Unsupported claims / proposal (after verification) | Judge score (1-5) | GigSim reply rate | p95 latency / proposal (s) | Cost / proposal (USD) |
|---|---|---|---|---|---|---|---|
| V0 (naive dense) | 0.790 | 0.841 | 0 | 5 | 0.700 | 119.9 | 0.0027 |
| Your best (V5 + hybrid, shipped) | 0.851 | 0.916 | 0 | 4.91 | 0.455 | 163.1 | 0.0032 |

### All retrieval variants (465 dev jobs with gold evidence)

| Variant | Recall@5 | MRR | nDCG@10 | multi-req R@5 | vague R@5 | p95 query latency (s) |
|---|---|---|---|---|---|---|
| v0_naive | 0.790 | 1.000 | 0.841 | 0.586 | 0.768 | 0.040 |
| v1_decompose | 0.813 | 0.999 | 0.893 | 0.600 | 0.831 | 0.059 |
| v2_hybrid | 0.850 | 1.000 | 0.914 | 0.656 | 0.814 | 0.054 |
| v3_rerank | 0.835 | 1.000 | 0.898 | 0.611 | 0.822 | 3.051 |
| v4_outcome | 0.844 | 0.974 | 0.892 | 0.664 | 0.786 | 0.048 |
| v5_multivector | 0.851 | 1.000 | 0.916 | 0.657 | 0.812 | 0.040 |
| best | 0.851 | 1.000 | 0.916 | 0.657 | 0.812 | 0.035 |
| v8_corrective (dev40 subset) | 0.802 | 0.989 | 0.853 | 0.532 | 0.863 | 3.348 |

**Ablation of the shipped pipeline**

| Change | Recall@5 | nDCG@10 |
|---|---|---|
| shipped (V5 + hybrid) | 0.851 | 0.916 |
| -multivector | 0.850 | 0.914 |
| -hybrid | 0.800 | 0.857 |
| +decompose | 0.832 | 0.916 |
| +outcome_boost | 0.842 | 0.899 |
| +rerank | 0.837 | 0.905 |

**By persona (shipped)**

| Persona | Recall@5 | nDCG@10 |
|---|---|---|
| ai_ml | 0.845 | 0.907 |
| fullstack | 0.865 | 0.931 |
| data_analyst | 0.843 | 0.909 |

### Proposal configurations on the fixed GigSim job set

| Config | Submitted | Unsupported claims before → after | Judge | Reply rate | Hire rate | p50 / p95 latency (s) | USD / proposal | Revisions |
|---|---|---|---|---|---|---|---|---|
| v0_open | 10/12 | 0.40 → 0 | 5 | 0.700 | 0.000 | 66.1 / 119.9 | 0.0027 | 0.90 |
| best_open | 11/12 | 0.27 → 0 | 4.91 | 0.455 | 0.000 | 112.3 / 163.1 | 0.0032 | 1.55 |
| best_qwen | 11/12 | 0.64 → 0 | 4.91 | 0.545 | 0.000 | 174.6 / 273.6 | 0.0038 | 1.82 |
| best_open_B | 12/12 | 0.08 → 0 | 5 | 0.833 | 0.000 | 47.5 / 74.5 | 0.0033 | 1.50 |

**X2 A/B test** — A (evidence-led) 5/11 replies vs B (question-led) 10/12; Fisher exact two-sided p = 0.0894.

### Decisions (original 120 dev jobs; thresholds were then tuned on these, see failure analysis)

| Slice | n | Bid/skip F1 | Accuracy | Scam precision | Scam recall | Price in fair band | p95 latency / job (s) | USD / job |
|---|---|---|---|---|---|---|---|---|
| overall | 120 | 0.922 | 0.900 | 0.818 | 1.000 | 0.507 | 21.5 | 0.00030 |
| ai_ml | 40 | 0.923 | 0.900 | 1.000 | 1.000 | 0.625 | 19.7 | 0.00020 |
| fullstack | 40 | 0.923 | 0.900 | 0.750 | 1.000 | 0.417 | 22.0 | 0.00030 |
| data_analyst | 40 | 0.920 | 0.900 | 0.750 | 1.000 | 0.478 | 22.4 | 0.00030 |
| fit | 72 | 0.957 | 0.917 | — | — | 0.545 | 22.0 | 0.00030 |
| inject | 9 | 0.714 | 0.556 | 0.000 | — | 0 | 19.8 | 0.00040 |
| lowball | 12 | 0.000 | 1 | — | — | — | 20.2 | 0.00030 |
| off | 18 | 0.000 | 0.889 | — | — | — | 21.4 | 0.00030 |
| scam | 9 | 0.000 | 1 | 1.000 | 1.000 | — | 20.8 | 0.00030 |

### R&D A — tool granularity (40 tasks)

| Tool set | Tools | Selection accuracy | Argument accuracy | Tokens / task |
|---|---|---|---|---|
| fine | 19 | 0.800 | 0.725 | 577 |
| coarse | 2 | 0.575 | 0.100 | 255 |
| best | 9 | 0.950 | 0.950 | 518 |

### R&D C — single agent vs supervisor vs graph

| System | Jobs | Failed runs | Bid/skip accuracy | Scam jobs bid on | Unsupported claims / proposal | Violations caught by guard | Violations left in output | Reply rate | Tokens / job | p50 / p95 latency (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| c_graph | 18 | 0 | 0.944 | 0 | 0 | 9 | 0 | 0.250 | 7089 | 42.2 / 142.1 |
| a_single_react | 18 | 10 | 0.778 | 0 | 0.20 | 0 | 2 | 0.400 | 3800 | 17.4 / 50.6 |
| b_supervisor | 18 | 18 | 0.500 | 0 | — | 0 | 0 | — | 0 | 1.2 / 141.3 |

### Injection defence

Attack success rate **0.417** before defences → **0.0** after (12 attacks: planted job posts + client messages); detection rate 1.0.

### Judge calibration

Cohen's kappa (quadratic) **0.091**, exact agreement 0.2, within ±1 0.733 on 30 proposals; reference labels by Ali. The judge is not calibrated, so its scores are not used for decisions.
