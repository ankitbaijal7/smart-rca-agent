"""
ChromaDB Vector Store Manager
Manages two collections:
  - rca_failures : past failure + fix pairs (for semantic memory)
  - rca_docs     : runbooks, keyword guides, architecture docs
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

COLLECTION_FAILURES = os.getenv("CHROMA_COLLECTION_FAILURES", "rca_failures")
COLLECTION_DOCS     = os.getenv("CHROMA_COLLECTION_DOCS",     "rca_docs")
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


class EmbeddingFunction:
    """SentenceTransformers embedding function compatible with ChromaDB 1.x."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        logger.info("Loading embedding model: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self._model_name = model_name

    def name(self) -> str:
        return f"sentence-transformers/{self._model_name}"

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self.model.encode(input, convert_to_numpy=True).tolist()

    def embed_documents(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self.model.encode(input, convert_to_numpy=True).tolist()

    def embed_query(self, input) -> list:  # noqa: A002
        if isinstance(input, str):
            return self.model.encode([input], convert_to_numpy=True).tolist()[0]
        return self.model.encode(input, convert_to_numpy=True).tolist()


class VectorStoreManager:
    """Manages ChromaDB collections for the Smart RCA agent."""

    def __init__(self):
        host = os.getenv("CHROMA_HOST", "localhost")
        port = int(os.getenv("CHROMA_PORT", "8001"))
        try:
            self.client = chromadb.HttpClient(
                host=host, port=port,
                settings=Settings(anonymized_telemetry=False)
            )
            logger.info("Connected to ChromaDB at %s:%s", host, port)
        except Exception:
            logger.warning("ChromaDB remote unavailable, using in-memory client")
            self.client = chromadb.Client()

        self.ef = EmbeddingFunction()
        self.failures = self.client.get_or_create_collection(
            name=COLLECTION_FAILURES,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.docs = self.client.get_or_create_collection(
            name=COLLECTION_DOCS,
            embedding_function=self.ef,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Collections ready: %s, %s", COLLECTION_FAILURES, COLLECTION_DOCS)

    # ── Failures collection ───────────────────────────────────────────────
    def add_failure(
        self,
        failure_text: str,
        fix_text: str,
        suite: str,
        failure_type: str,
        run_id: str = "",
        metadata: dict | None = None,
    ) -> str:
        doc_id = str(uuid.uuid4())
        meta = {
            "suite":        suite,
            "failure_type": failure_type,
            "run_id":       run_id,
            "date":         datetime.utcnow().isoformat(),
            "fix":          fix_text[:500],
            **(metadata or {}),
        }
        self.failures.add(
            ids=[doc_id],
            documents=[f"FAILURE: {failure_text}\nFIX: {fix_text}"],
            metadatas=[meta],
        )
        logger.info("Indexed failure %s (suite=%s)", doc_id, suite)
        return doc_id

    def search_failures(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        results = self.failures.query(
            query_texts=[query],
            n_results=min(top_k, max(1, self.failures.count())),
        )
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            hits.append({
                "id":           results["ids"][0][i],
                "document":     doc,
                "suite":        meta.get("suite", ""),
                "failure_type": meta.get("failure_type", ""),
                "fix":          meta.get("fix", ""),
                "date":         meta.get("date", ""),
                "score":        round(1 - dist, 4),  # cosine similarity
            })
        return sorted(hits, key=lambda x: x["score"], reverse=True)

    # ── Docs collection ───────────────────────────────────────────────────
    def add_document(self, title: str, content: str, doc_type: str = "runbook") -> str:
        doc_id = str(uuid.uuid4())
        self.docs.add(
            ids=[doc_id],
            documents=[f"{title}\n\n{content}"],
            metadatas=[{"title": title, "doc_type": doc_type, "date": datetime.utcnow().isoformat()}],
        )
        logger.info("Indexed doc '%s'", title)
        return doc_id

    def search_docs(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if self.docs.count() == 0:
            return []
        results = self.docs.query(
            query_texts=[query],
            n_results=min(top_k, self.docs.count()),
        )
        hits = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            hits.append({
                "id":       results["ids"][0][i],
                "title":    meta.get("title", ""),
                "content":  doc,
                "doc_type": meta.get("doc_type", ""),
                "score":    round(1 - dist, 4),
            })
        return sorted(hits, key=lambda x: x["score"], reverse=True)

    # ── Combined retrieval (RAG context builder) ──────────────────────────
    def retrieve_context(self, query: str, failure_k: int = 4, doc_k: int = 3) -> str:
        failures = self.search_failures(query, top_k=failure_k)
        docs     = self.search_docs(query, top_k=doc_k)

        parts = []
        if failures:
            parts.append("=== PAST FAILURES & FIXES (from memory) ===")
            for f in failures:
                parts.append(
                    f"[{f['date'][:10]} | {f['suite']} | score={f['score']}]\n"
                    f"{f['document']}"
                )
        if docs:
            parts.append("\n=== RUNBOOKS & DOCUMENTATION ===")
            for d in docs:
                parts.append(f"[{d['title']} | score={d['score']}]\n{d['content']}")

        return "\n\n".join(parts) if parts else "No relevant context found in vector store."

    # ── Stats ─────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        return {
            "failures_indexed": self.failures.count(),
            "docs_indexed":     self.docs.count(),
        }


# Singleton
vector_store = VectorStoreManager()
