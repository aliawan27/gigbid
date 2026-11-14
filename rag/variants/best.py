"""Shipped configuration, chosen by measurement (evals/results/rag_variants.json): V5 multi-vector indexing +
hybrid BM25/dense fusion had the best Recall@5 and nDCG@10; decomposition and the outcome boost lowered both
on this corpus, and the cross-encoder added latency without a gain (see README 'What ships')."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="best", chunking="multivector", hybrid=True)
