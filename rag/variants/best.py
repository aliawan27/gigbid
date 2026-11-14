"""Shipped configuration (chosen by evals/results/rag_variants.json — see README 'What ships')."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="best", decompose=True, hybrid=True, outcome_boost=1.0)
