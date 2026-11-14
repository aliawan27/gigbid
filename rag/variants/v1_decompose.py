"""V1 (query group): one retrieval per extracted requirement, merged with reciprocal rank fusion."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v1_decompose", decompose=True)
