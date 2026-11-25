"""Validation agent: deterministic source-presence and unsafe-instruction checks."""
from __future__ import annotations
from typing import Any
from .policy import UNSAFE_DRAFT


def run_validation(draft: str | None, sources: list[dict[str, Any]], risk_flags: list[str]) -> dict[str, Any]:
    findings: list[str] = []
    if draft and UNSAFE_DRAFT.search(draft):
        findings.append("unsafe_security_or_destructive_instruction_detected")
    if not sources:
        findings.append("no_retrieved_evidence")
    if not draft:
        findings.append("no_response_draft")
    requires_review = bool(risk_flags or findings)
    return {
        "source_count": len(sources),
        "has_draft": bool(draft),
        "unsafe_findings": findings,
        "requires_human_approval": requires_review,
        "policy": "No automatic system changes, ticket closure or customer email from this workflow.",
    }
