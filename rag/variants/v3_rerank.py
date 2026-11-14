"""V3 (retrieval group): hybrid candidates re-ranked by an open cross-encoder (ms-marco-MiniLM-L-6-v2)."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v3_rerank", hybrid=True, rerank=True)
