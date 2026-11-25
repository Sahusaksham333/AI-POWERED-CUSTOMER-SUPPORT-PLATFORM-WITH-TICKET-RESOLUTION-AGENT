"""Knowledge retrieval agent: query the existing Chroma-backed retriever."""
from __future__ import annotations
from typing import Any


def run_retrieval(pipeline: Any, subject: str, body: str, queue: str | None) -> dict[str, Any]:
    query = f"{subject}\n\n{body}\nCategory: {queue or 'unknown'}"
    sources = pipeline.retriever.search(query)
    health = pipeline.retriever.health()
    return {
        "count": len(sources),
        "ready": bool(health.get("ready")),
        "embedding_model": health.get("embedding_model"),
        "sources": sources,
    }
