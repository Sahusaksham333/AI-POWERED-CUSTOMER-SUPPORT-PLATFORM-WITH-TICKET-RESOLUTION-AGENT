"""Multilingual Chroma retriever. Run scripts/index_knowledge_base.py first."""
from __future__ import annotations
from typing import Any
import chromadb
from sentence_transformers import SentenceTransformer
from .config import CHROMA_DIR, EMBEDDING_MODEL, TOP_K


class KnowledgeRetriever:
    def __init__(self):
        self._client = None
        self._collection = None
        self._embedder = None
        self._attempted = False
        self._error: str | None = None

    def _initialize(self) -> bool:
        if self._collection is not None:
            return True
        # If we previously found an empty collection, retry: the indexer may have
        # populated it while the API process was running. Do not retry other
        # persistent initialization errors on every request.
        if self._attempted and self._error and not self._error.startswith("Knowledge index is empty"):
            return False
        self._attempted = True
        try:
            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            collection = client.get_or_create_collection(
                name="supportpilot_knowledge",
                metadata={"hnsw:space": "cosine", "description": "SupportPilot knowledge base"},
            )
            if collection.count() == 0:
                self._error = "Knowledge index is empty. Add trusted files to knowledge_base/ and run scripts/index_knowledge_base.py."
                return False
            self._embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            self._client, self._collection = client, collection
            return True
        except Exception as exc:  # surface in health output rather than break every endpoint
            self._error = f"Knowledge retrieval initialization failed: {exc}"
            return False

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        if not self._initialize():
            return []
        assert self._embedder is not None and self._collection is not None
        vector = self._embedder.encode([query], normalize_embeddings=True).tolist()
        result = self._collection.query(
            query_embeddings=vector, n_results=max(1, min(top_k or TOP_K, self._collection.count())),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        sources = []
        for i, document in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) and metadatas[i] else {}
            distance = float(distances[i]) if i < len(distances) and distances[i] is not None else None
            sources.append({
                "source": meta.get("source", "unknown"),
                "chunk": meta.get("chunk", i),
                "distance": round(distance, 4) if distance is not None else None,
                "text": document,
            })
        return sources

    def health(self) -> dict[str, Any]:
        ok = self._initialize()
        count = self._collection.count() if ok and self._collection is not None else 0
        return {"ready": bool(ok), "document_chunks": count, "error": self._error,
                "embedding_model": EMBEDDING_MODEL}
