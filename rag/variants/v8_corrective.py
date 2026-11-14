"""V8 (agentic group): corrective RAG in LangGraph — grade evidence, re-query when weak, refuse when none."""
from rag.variants.base import RAGConfig

CONFIG = RAGConfig(name="v8_corrective", decompose=True, hybrid=True, corrective=True)
