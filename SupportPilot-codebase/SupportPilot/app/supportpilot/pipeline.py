"""Ticket prediction, retrieval, draft generation and escalation policy."""
from __future__ import annotations
from typing import Any
from .classifier import ClassifierService
from .retriever import KnowledgeRetriever
from .generator import OllamaGenerator
from .policy import escalation_reason


class TicketPipeline:
    def __init__(self):
        self.classifier = ClassifierService()
        self.retriever = KnowledgeRetriever()
        self.generator = OllamaGenerator()

    def predict(self, subject: str, body: str) -> dict[str, Any]:
        text = f"{subject.strip()}\n\n{body.strip()}".strip()
        predictions = {target: self.classifier.predict(target, text) for target in ("queue", "type", "priority")}
        tags = self.classifier.predict_tags(text, top_k=3)
        reasons = escalation_reason(subject, body, predictions.get("priority", {}), predictions)
        return {"predictions": predictions, "tags": tags, "escalated": bool(reasons), "escalation_reasons": reasons,
                "model_health": self.classifier.health()}

    def resolve(self, subject: str, body: str, language: str = "auto") -> dict[str, Any]:
        prediction = self.predict(subject, body)
        query = f"{subject}\n\n{body}"
        sources = self.retriever.search(query)
        # Re-evaluate escalation after model predictions; no automatic side effects are performed.
        reasons = list(prediction["escalation_reasons"])
        if not sources:
            reasons.append("no_knowledge_sources_retrieved")
        draft = None
        generation_error = None
        try:
            draft = self.generator.draft(
                subject=subject, body=body, language=language,
                predicted=prediction["predictions"], sources=sources,
            )
        except Exception as exc:
            generation_error = str(exc)
        if draft is None:
            draft = (
                "SupportPilot could not generate a grounded response because the local LLM is unavailable. "
                "Please review the ticket manually and confirm the appropriate troubleshooting steps."
            )
            reasons.append("response_generation_unavailable")
        return {**prediction, "sources": sources, "response_draft": draft,
                "escalated": bool(reasons), "escalation_reasons": sorted(set(reasons)),
                "generation_error": generation_error,
                "status": "pending_human_review" if reasons else "draft_ready_for_review"}

    def health(self) -> dict[str, Any]:
        return {"classifier": self.classifier.health(), "retriever": self.retriever.health(),
                "ollama": self.generator.health()}
