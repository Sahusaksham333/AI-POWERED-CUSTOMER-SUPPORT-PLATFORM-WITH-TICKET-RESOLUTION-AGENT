"""Escalation agent: choose a support group and human-review disposition."""
from __future__ import annotations
from typing import Any
from .diagnosis import route_team


def run_escalation(queue: str | None, risk_flags: list[str], unsafe_findings: list[str],
                   classifier_escalated: bool, information_to_collect: list[str],
                   requires_review: bool) -> dict[str, Any]:
    assigned_team = route_team(queue, risk_flags)
    escalated = requires_review or classifier_escalated
    return {
        "assigned_team": assigned_team,
        "escalated": escalated,
        "decision": "human_review" if escalated else "draft_ready_for_review",
        "reasons": sorted(set(risk_flags + unsafe_findings)),
        "information_to_collect": information_to_collect,
    }
