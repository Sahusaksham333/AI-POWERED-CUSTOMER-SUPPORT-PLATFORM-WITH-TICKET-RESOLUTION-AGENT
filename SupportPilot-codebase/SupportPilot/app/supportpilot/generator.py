"""Grounded response drafting through the local Ollama API."""
from __future__ import annotations
import requests
from typing import Any
from .config import OLLAMA_URL, OLLAMA_MODEL, MAX_NEW_TOKENS


class OllamaGenerator:
    def __init__(self):
        self.base_url = OLLAMA_URL
        self.model = OLLAMA_MODEL

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=3)
            response.raise_for_status()
            names = [m.get("name") for m in response.json().get("models", [])]
            return {"ready": True, "model": self.model, "model_present": any(
                n == self.model or (n and n.split(":")[0] == self.model.split(":")[0]) for n in names
            ), "available_models": names}
        except requests.RequestException as exc:
            return {"ready": False, "model": self.model, "error": str(exc)}

    def draft(self, *, subject: str, body: str, language: str, predicted: dict[str, Any],
              sources: list[dict[str, Any]]) -> str:
        source_text = "\n\n".join(
            f"[SOURCE {i + 1}: {src['source']} | chunk {src.get('chunk')} ]\n{src['text']}"
            for i, src in enumerate(sources)
        )
        if not source_text:
            source_text = "No approved knowledge-base sources were retrieved. Do not invent company-specific instructions. Ask for clarification or recommend human support."
        priority = predicted.get("priority", {}).get("label") or "unknown"
        queue = predicted.get("queue", {}).get("label") or "unknown"
        ticket_type = predicted.get("type", {}).get("label") or "unknown"
        prompt = f"""You are SupportPilot, an IT/customer support response-drafting assistant.
Produce a concise response draft in the ticket's language ({language or 'the language used by the requester'}).
Use the retrieved sources as the primary evidence. Never claim a ticket is fixed, a system was changed, or an action was completed.
Do not invent policies, URLs, credentials, commands, or source citations. If the sources are insufficient, say what is unknown and recommend human review.
For suspected security incidents, data breaches, malware, or broad outages, advise immediate escalation and avoid risky remediation steps.
Return only the message draft, with numbered steps when appropriate. You may refer to source names in a short internal note outside the customer message, but do not fabricate citations.

Predicted metadata (may be wrong; treat as hints, not facts): queue={queue}; priority={priority}; type={ticket_type}.
Ticket subject: {subject}
Ticket body:
{body}

Retrieved knowledge-base material:
{source_text}
"""
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={"model": self.model, "stream": False,
                  "messages": [{"role": "user", "content": prompt}],
                  "options": {"temperature": 0.2, "num_predict": MAX_NEW_TOKENS}},
            timeout=180,
        )
        response.raise_for_status()
        answer = response.json().get("message", {}).get("content", "").strip()
        if not answer:
            raise RuntimeError("Ollama returned an empty response")
        return answer
