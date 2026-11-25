"""FastAPI router for M3 operations. All routes require the M3 admin key."""
from __future__ import annotations
import json
import os
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..db import connect, get_ticket
from .agents.orchestrator import MultiAgentOrchestrator
from .communications.worker import process_outbox_once, worker_is_running
from .integrations.jira import sync_ticket_to_jira
from .security import require_m3_admin
from .settings import email_automation_enabled, email_configured, jira_auto_create, jira_auto_sync, jira_configured
from .storage import enqueue_outbox, latest_agent_run
from .utils import record_portal_event


class AIEmailApprovalRequest(BaseModel):
    approved: bool = False
    edited_body: str | None = Field(default=None, max_length=12000)


class JiraSyncRequest(BaseModel):
    force_status_sync: bool = True


def create_m3_router(pipeline: Any) -> APIRouter:
    router = APIRouter(
        prefix="/m3",
        tags=["Milestone 3 - Agents and Integrations"],
        dependencies=[Depends(require_m3_admin)],
    )
    orchestrator = MultiAgentOrchestrator(pipeline)

    @router.get("/status")
    def m3_status() -> dict[str, Any]:
        with connect() as conn:
            counts = {
                row["status"]: row["n"]
                for row in conn.execute("SELECT status,COUNT(*) n FROM m3_outbox GROUP BY status")
            }
            runs = conn.execute("SELECT COUNT(*) FROM m3_agent_runs").fetchone()[0]
            linked = conn.execute("SELECT COUNT(*) FROM m3_jira_links").fetchone()[0]
        try:
            knowledge_status = pipeline.retriever.health()
        except Exception as exc:
            knowledge_status = {"ready": False, "error": f"{type(exc).__name__}: {str(exc)[:250]}"}
        try:
            ollama_status = pipeline.generator.health()
        except Exception as exc:
            ollama_status = {"ready": False, "error": f"{type(exc).__name__}: {str(exc)[:250]}"}
        return {
            "milestone": 3,
            "agents": [
                "Diagnosis Agent", "Knowledge Retrieval Agent", "Resolution Agent",
                "Validation Agent", "Escalation Agent",
            ],
            "knowledge": knowledge_status,
            "ollama": ollama_status,
            "jira": {
                "configured": jira_configured(),
                "linked_tickets": linked,
                "auto_create": jira_auto_create(),
                "auto_sync": jira_auto_sync(),
            },
            "email": {
                "enabled": email_automation_enabled(),
                "configured": email_configured(),
                "outbox": counts,
            },
            "agent_runs": runs,
            "worker_running": worker_is_running(),
        }

    @router.post("/tickets/{ticket_id}/agents/run")
    def run_agents(ticket_id: str) -> dict[str, Any]:
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        try:
            return orchestrator.run(ticket)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Multi-agent workflow failed: {type(exc).__name__}: {str(exc)[:400]}",
            ) from exc

    @router.get("/tickets/{ticket_id}/agents/latest")
    def latest_agents(ticket_id: str) -> dict[str, Any]:
        if not get_ticket(ticket_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        return latest_agent_run(ticket_id) or {"ticket_id": ticket_id, "status": "not_run"}

    @router.get("/tickets/{ticket_id}/jira")
    def jira_link(ticket_id: str) -> dict[str, Any]:
        if not get_ticket(ticket_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        with connect() as conn:
            row = conn.execute("SELECT * FROM m3_jira_links WHERE ticket_id=?", (ticket_id,)).fetchone()
        return dict(row) if row else {"ticket_id": ticket_id, "linked": False}

    @router.post("/tickets/{ticket_id}/jira/sync")
    def jira_sync(ticket_id: str, request: JiraSyncRequest = JiraSyncRequest()) -> dict[str, Any]:
        try:
            return sync_ticket_to_jira(ticket_id, request.force_status_sync)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Jira synchronisation failed: {type(exc).__name__}: {str(exc)[:400]}",
            ) from exc

    @router.post("/tickets/{ticket_id}/email/ai-response")
    def approve_ai_email(ticket_id: str, request: AIEmailApprovalRequest) -> dict[str, Any]:
        if not request.approved:
            raise HTTPException(status_code=400, detail="Explicit human approval is required before sending an AI response.")
        ticket = get_ticket(ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        recipient = str(ticket.get("requester_email") or "").strip()
        if not recipient or "@" not in recipient:
            raise HTTPException(status_code=422, detail="This ticket does not have a valid requester email address.")
        sources = ticket.get("sources") or []
        draft = str(request.edited_body or ticket.get("response_draft") or "").strip()
        if not sources:
            raise HTTPException(status_code=409, detail="Cannot queue an AI troubleshooting email without retrieved knowledge sources.")
        if not draft:
            raise HTTPException(status_code=409, detail="No AI response draft exists. Run the multi-agent workflow first.")
        event_id = enqueue_outbox(
            event_key=f"ai-response-approved:{ticket_id}:{__import__('hashlib').sha256(draft.encode()).hexdigest()[:16]}",
            ticket_id=ticket_id,
            event_type="ai_response_approved",
            recipient=recipient,
            subject=f"SupportPilot guidance for ticket {ticket_id}",
            payload={"body_text": draft, "approved": True},
        )
        record_portal_event(
            ticket_id, "ai_response_approved", "AI response approved for email",
            "A support operator approved the response for delivery.",
        )
        return {"queued": True, "event_id": event_id, "recipient": recipient, "status": "pending"}

    @router.get("/outbox")
    def list_outbox(limit: int = Query(default=100, ge=1, le=500), status: str | None = None) -> dict[str, Any]:
        columns = (
            "event_id,event_key,ticket_id,event_type,recipient_email,subject,status,attempt_count,"
            "next_attempt_at,last_error,created_at,sent_at"
        )
        with connect() as conn:
            if status:
                rows = conn.execute(
                    f"SELECT {columns} FROM m3_outbox WHERE status=? ORDER BY event_id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {columns} FROM m3_outbox ORDER BY event_id DESC LIMIT ?", (limit,)
                ).fetchall()
        return {"events": [dict(row) for row in rows]}

    @router.post("/outbox/{event_id}/retry")
    def retry_outbox(event_id: int) -> dict[str, Any]:
        from .utils import now_iso
        with connect() as conn:
            cursor = conn.execute(
                """UPDATE m3_outbox SET status='pending',attempt_count=0,next_attempt_at=?,last_error=NULL
                   WHERE event_id=? AND status IN ('failed','pending')""",
                (now_iso(), event_id),
            )
            if not cursor.rowcount:
                row = conn.execute("SELECT status FROM m3_outbox WHERE event_id=?", (event_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Outbox event not found")
                raise HTTPException(status_code=409, detail=f"Event cannot be retried from status {row['status']}.")
        return {"event_id": event_id, "status": "pending"}

    @router.post("/outbox/process-once")
    def process_outbox() -> dict[str, bool]:
        return {"processed": process_outbox_once()}

    return router
