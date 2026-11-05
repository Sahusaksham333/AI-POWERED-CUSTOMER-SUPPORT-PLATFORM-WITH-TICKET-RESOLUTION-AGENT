"""Authenticated customer endpoints for knowledge retrieval and AI assistance."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .user_portal import _current_user


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=5000)
    top_k: int = Field(default=4, ge=1, le=10)


class KnowledgeAssistRequest(BaseModel):
    query: str = Field(min_length=5, max_length=12000)
    language: str = Field(default="auto", max_length=20)


def create_knowledge_assistance_router(pipeline: Any) -> APIRouter:
    router = APIRouter(tags=["User knowledge and AI assistance"])

    def _retriever():
        retriever = getattr(pipeline, "retriever", None)
        if retriever is None:
            raise HTTPException(
                status_code=503,
                detail="RAG retrieval is not installed in this SupportPilot backend. Install the Milestone 2 retrieval components first.",
            )
        return retriever

    @router.get("/user/knowledge/status")
    def user_knowledge_status(user: dict[str, str] = Depends(_current_user)):
        status = _retriever().health()
        return status

    @router.post("/user/knowledge/search")
    def user_knowledge_search(
        request: KnowledgeSearchRequest,
        user: dict[str, str] = Depends(_current_user),
    ):
        retriever = _retriever()
        status = retriever.health()
        if not status.get("ready"):
            raise HTTPException(
                status_code=503,
                detail=status.get("error") or "Knowledge retrieval is not ready.",
            )
        sources = retriever.search(request.query, top_k=request.top_k)
        return {"query": request.query, "count": len(sources), "sources": sources}

    @router.post("/user/knowledge/assist")
    def user_knowledge_assist(
        request: KnowledgeAssistRequest,
        user: dict[str, str] = Depends(_current_user),
    ):
        retriever = _retriever()
        status = retriever.health()
        if not status.get("ready"):
            raise HTTPException(
                status_code=503,
                detail=status.get("error") or "Knowledge retrieval is not ready.",
            )
        resolve = getattr(pipeline, "resolve", None)
        if not callable(resolve):
            raise HTTPException(
                status_code=503,
                detail="The RAG response-generation pipeline is not available.",
            )
        result = resolve(
            subject="Customer self-service assistance",
            body=request.query,
            language=request.language,
        )
        return {
            "response_draft": result.get("response_draft", ""),
            "sources": result.get("sources", []),
            "escalated": bool(result.get("escalated", False)),
            "escalation_reasons": result.get("escalation_reasons", []),
            "generation_error": result.get("generation_error"),
            "status": result.get("status", "pending_human_review"),
        }

    return router
