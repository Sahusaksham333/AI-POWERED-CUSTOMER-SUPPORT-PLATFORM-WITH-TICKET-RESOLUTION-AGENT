"""Multi-agent orchestrator: coordinates specialist agents and persists execution trace."""
from __future__ import annotations
from typing import Any
from uuid import uuid4

from ...db import connect
from ..storage import (
    complete_agent_run, fail_agent_run, insert_agent_event, start_agent_run,
)
from ..utils import now_iso, record_portal_event, to_json
from .diagnosis import run_diagnosis
from .retrieval import run_retrieval
from .resolution import run_resolution
from .validation import run_validation
from .escalation import run_escalation


class MultiAgentOrchestrator:
    """Run diagnosis → retrieval → resolution → validation → escalation."""
    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def _event(self, run_id: str, ticket_id: str, name: str, message: str,
               output: dict[str, Any] | None = None) -> None:
        insert_agent_event(run_id, ticket_id, name, "completed", message, output or {})

    def run(self, ticket: dict[str, Any]) -> dict[str, Any]:
        ticket_id = str(ticket["ticket_id"])
        run_id = f"M3-{uuid4().hex[:12].upper()}"
        start_agent_run(run_id, ticket_id)
        stages: list[dict[str, Any]] = []
        try:
            subject = str(ticket.get("subject") or "")
            body = str(ticket.get("body") or "")
            language = str(ticket.get("language") or "auto")

            insert_agent_event(run_id, ticket_id, "diagnosis", "running", "Inspecting ticket and classifier signals.")
            diagnosis = run_diagnosis(self.pipeline, subject, body)
            dx = diagnosis["output"]
            stages.append({"agent": "Diagnosis Agent", "status": "completed", "output": dx})
            self._event(run_id, ticket_id, "diagnosis", "Ticket classification and risk scan completed.", dx)

            insert_agent_event(run_id, ticket_id, "knowledge_retrieval", "running", "Searching approved support knowledge.")
            retrieval = run_retrieval(self.pipeline, subject, body, dx.get("queue"))
            sources = retrieval["sources"]
            stages.append({"agent": "Knowledge Retrieval Agent", "status": "completed", "output": retrieval})
            self._event(run_id, ticket_id, "knowledge_retrieval", f"Retrieved {len(sources)} knowledge passage(s).", {"count": len(sources), "sources": sources})

            risk_flags = list(diagnosis["risk_flags"])
            if not sources:
                risk_flags.append("no_knowledge_sources_retrieved")

            insert_agent_event(run_id, ticket_id, "resolution", "running", "Preparing a source-grounded response draft.")
            resolution = run_resolution(
                self.pipeline, subject, body, language, dx.get("predictions", {}), sources,
            )
            draft = resolution["draft"]
            stages.append({"agent": "Resolution Agent", "status": "completed", "output": resolution})
            self._event(run_id, ticket_id, "resolution", "Response draft prepared." if draft else "No grounded response draft was produced.", resolution)
            if not draft:
                risk_flags.append("response_generation_unavailable")

            insert_agent_event(run_id, ticket_id, "validation", "running", "Checking grounding and unsafe recommendations.")
            validation = run_validation(draft, sources, risk_flags)
            stages.append({"agent": "Validation Agent", "status": "completed", "output": validation})
            self._event(run_id, ticket_id, "validation", "Evidence and safety policy checks completed.", validation)

            insert_agent_event(run_id, ticket_id, "escalation", "running", "Selecting support team and next action.")
            escalation = run_escalation(
                dx.get("queue"), risk_flags, validation["unsafe_findings"],
                bool(diagnosis["raw"].get("escalated")), dx.get("information_to_collect", []),
                validation["requires_human_approval"],
            )
            stages.append({"agent": "Escalation Agent", "status": "completed", "output": escalation})
            self._event(run_id, ticket_id, "escalation", f"Recommended route: {escalation['assigned_team']}.", escalation)

            result = {
                "run_id": run_id,
                "ticket_id": ticket_id,
                "status": "completed",
                "decision": escalation["decision"],
                "requires_human_approval": validation["requires_human_approval"],
                "diagnosis": dx,
                "sources": sources,
                "response_draft": draft,
                "validation": validation,
                "escalation": escalation,
                "agents": stages,
                "completed_at": now_iso(),
            }
            complete_agent_run(
                run_id, ticket_id, result, escalation["decision"], draft, sources,
                bool(escalation["escalated"]),
            )
            record_portal_event(
                ticket_id, "multi_agent_completed", "Multi-agent investigation completed",
                f"Decision: {escalation['decision']}. Routed to: {escalation['assigned_team']}.",
            )
            return result
        except Exception as exc:
            failure = {
                "run_id": run_id,
                "ticket_id": ticket_id,
                "status": "failed",
                "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                "agents": stages,
            }
            fail_agent_run(run_id, failure)
            insert_agent_event(run_id, ticket_id, "orchestrator", "failed", failure["error"], {})
            raise
