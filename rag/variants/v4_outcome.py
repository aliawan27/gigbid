"""V4 (ranking group): outcome-aware boost for projects/proposals that won or got replies."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v4_outcome", hybrid=True, outcome_boost=1.0)
