# ADR 0002 — Ship V5 multi-vector + hybrid retrieval
**Decision.** The deployed RAG variant (`rag.variant: best`) is V5 multi-vector indexing with BM25+dense RRF.
**Why.** Highest Recall@5 and nDCG@10 on the dev sets; decomposition and the outcome boost lowered nDCG, the cross-encoder
added latency without a gain (`evals/results/rag_variants.json`, ablation section).
