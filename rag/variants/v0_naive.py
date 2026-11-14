"""V0 baseline: fixed 400-char chunks, top-k cosine on the whole job post."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v0_naive", chunking="fixed")
