"""V2 (retrieval group): BM25 + dense with reciprocal rank fusion (exact tool names like 'Celery', 'dbt')."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v2_hybrid", hybrid=True)
