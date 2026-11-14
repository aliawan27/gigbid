
### All retrieval variants

| Variant | Recall@5 | MRR | nDCG@10 | multi-req R@5 | vague R@5 | p95 query latency (s) |
|---|---|---|---|---|---|---|
| v0_naive | 0.798 | 1.000 | 0.848 | 0.598 | 0.752 | 0.030 |
| v1_decompose | 0.803 | 1.000 | 0.889 | 0.583 | 0.826 | 0.046 |
| v2_hybrid | 0.833 | 1.000 | 0.912 | 0.615 | 0.821 | 0.039 |
| v3_rerank | 0.828 | 1.000 | 0.901 | 0.582 | 0.842 | 2.916 |
| v4_outcome | 0.842 | 0.962 | 0.889 | 0.652 | 0.801 | 0.043 |
| v5_multivector | 0.843 | 1.000 | 0.917 | 0.620 | 0.833 | 0.043 |
| v8_corrective | 0.802 | 0.989 | 0.853 | 0.532 | 0.863 | 3.348 |
| best | 0.843 | 1.000 | 0.917 | 0.620 | 0.833 | 0.031 |

**Ablation of the shipped pipeline**

| Change | Recall@5 | nDCG@10 |
|---|---|---|
| shipped (V5 + hybrid) | 0.843 | 0.917 |
| -multivector | 0.833 | 0.912 |
| -hybrid | 0.811 | 0.865 |
| +decompose | 0.819 | 0.909 |
| +outcome_boost | 0.850 | 0.904 |
| +rerank | 0.835 | 0.907 |

**By persona (shipped)**

| Persona | Recall@5 | nDCG@10 |
|---|---|---|
| ai_ml | 0.842 | 0.921 |
| fullstack | 0.859 | 0.938 |
| data_analyst | 0.829 | 0.891 |

### Decisions (all dev jobs)

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
