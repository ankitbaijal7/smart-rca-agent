"""
Pain 2 — Recurring Failure Memory Agent
Semantic search over ChromaDB + LLM-augmented answer with past fixes.
"""
import json
import logging
from backend.models.llm_router import llm_router
from backend.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


async def search_failure_memory(query: str, top_k: int = 5) -> dict:
    """Search vector DB for similar failures and generate augmented answer."""
    # Semantic search
    failure_hits = vector_store.search_failures(query, top_k=top_k)
    doc_hits      = vector_store.search_docs(query, top_k=3)

    rag_context = vector_store.retrieve_context(query)

    system = """You are a senior network automation engineer with deep memory of every CI failure and fix on the Vodafone Ready Networks programme.
Use the RAG context to give precise, actionable answers.
Lead with the exact fix (command/config/code) if you know it.
Mention if you've seen this issue before and how many times.
Be concise — max 4 paragraphs."""

    user = f"""Query: "{query}"

RAG CONTEXT:
{rag_context}

Respond with JSON:
{{
  "answer": "detailed answer with exact fix",
  "seen_before": true|false,
  "occurrence_count": 0,
  "fix_command": "exact command or code if applicable",
  "prevention": "how to prevent recurrence",
  "confidence": 0.0-1.0
}}"""

    try:
        raw = await llm_router.invoke(system, user)
        clean = raw.replace("```json", "").replace("```", "").strip()
        llm_result = json.loads(clean)
    except Exception as e:
        llm_result = {"answer": f"Search error: {e}", "confidence": 0}

    return {
        "query":         query,
        "vector_hits":   failure_hits,
        "doc_hits":      doc_hits,
        "llm_answer":    llm_result,
        "total_indexed": vector_store.stats(),
    }


async def index_document(title: str, content: str, doc_type: str = "runbook") -> dict:
    """Index a new document into the vector store."""
    doc_id = vector_store.add_document(title, content, doc_type)
    return {"doc_id": doc_id, "title": title, "status": "indexed"}


async def index_failure(failure_text: str, fix_text: str, suite: str, failure_type: str) -> dict:
    """Manually index a failure+fix pair."""
    doc_id = vector_store.add_failure(failure_text, fix_text, suite, failure_type)
    return {"doc_id": doc_id, "status": "indexed"}
