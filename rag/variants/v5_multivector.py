"""V5 (indexing group): summary, README sections and code indexed as separate views, returned as one item."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v5_multivector", chunking="multivector", hybrid=True)
