"""Jira Cloud API client and ticket synchronisation service."""
from __future__ import annotations
import os
import threading
from typing import Any
import requests

from ...db import connect, get_ticket
from ..settings import jira_configured
from ..utils import now_iso, record_portal_event

_JIRA_LOCK = threading.Lock()


def jira_request(method: str, path: str, *, json_body: dict[str, Any] | None = None) -> requests.Response:
    base = os.getenv("SUPPORTPILOT_JIRA_BASE_URL", "").rstrip("/")
    email = os.getenv("SUPPORTPILOT_JIRA_EMAIL", "")
    token = os.getenv("SUPPORTPILOT_JIRA_API_TOKEN", "")
    if not jira_configured():
        raise RuntimeError("Jira is not configured. Set the Jira base URL, account email, API token and project key in .env.")
    if not base.lower().startswith("https://"):
        raise RuntimeError("Jira Cloud API communication requires an HTTPS base URL.")
    response = requests.request(
        method,
        f"{base}{path}",
        json=json_body,
        auth=(email, token),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=(5, 25),
    )
    if not response.ok:
        raise RuntimeError(f"Jira returned HTTP {response.status_code}: {response.text[:600]}")
    return response


def sync_ticket_to_jira(ticket_id: str, force_status_sync: bool = True) -> dict[str, Any]:
    ticket = get_ticket(ticket_id)
    if not ticket:
        raise LookupError(f"Ticket not found: {ticket_id}")

    with _JIRA_LOCK:
        with connect() as conn:
            row = conn.execute("SELECT * FROM m3_jira_links WHERE ticket_id=?", (ticket_id,)).fetchone()
            existing = dict(row) if row else None

        created = False
        if existing is None:
            base = os.getenv("SUPPORTPILOT_JIRA_BASE_URL", "").rstrip("/")
            project = os.getenv("SUPPORTPILOT_JIRA_PROJECT_KEY", "")
            description_lines = [
                f"SupportPilot reference: {ticket_id}",
                f"Requester: {ticket.get('requester_email') or 'Not supplied'}",
                f"Queue: {ticket.get('queue') or 'Unavailable'}",
                f"Type: {ticket.get('ticket_type') or 'Unavailable'}",
                f"Priority: {ticket.get('priority') or 'Unavailable'}",
                f"Business impact: {ticket.get('business_impact') or 'Medium'}",
                f"SupportPilot status: {ticket.get('workflow_status') or 'Open'}",
                "", "Issue description:", str(ticket.get("body") or "")[:12000],
                "", "AI response draft (advisory; human review required):",
                str(ticket.get("response_draft") or "No draft available.")[:12000],
            ]
            adf = {
                "type": "doc", "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": line[:30000]}]}
                    for line in description_lines if line.strip()
                ],
            }
            payload = {"fields": {
                "project": {"key": project},
                "summary": f"[SupportPilot] {ticket.get('subject') or 'Support ticket'}"[:250],
                "description": adf,
                "issuetype": {"name": os.getenv("SUPPORTPILOT_JIRA_ISSUE_TYPE", "Task")},
                "labels": ["supportpilot", f"priority-{str(ticket.get('priority') or 'unknown').lower().replace(' ', '-')[:30]}"],
            }}
            data = jira_request("POST", "/rest/api/3/issue", json_body=payload).json()
            key = data.get("key")
            if not key:
                raise RuntimeError("Jira created an issue but did not return an issue key.")
            url = f"{base}/browse/{key}"
            with connect() as conn:
                conn.execute(
                    """INSERT INTO m3_jira_links
                       (ticket_id,jira_key,jira_id,jira_url,last_synced_status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (ticket_id, key, str(data.get("id") or ""), url, None, now_iso(), now_iso()),
                )
            existing = {
                "ticket_id": ticket_id, "jira_key": key, "jira_id": data.get("id"),
                "jira_url": url, "last_synced_status": None,
            }
            created = True

        target_status = str(ticket.get("workflow_status") or "Open")
        transition_result = "already_in_sync" if (
            force_status_sync and existing.get("last_synced_status") == target_status
        ) else "not_requested"
        sync_record = False

        if force_status_sync and existing.get("last_synced_status") != target_status:
            aliases = {
                "open": {"open", "to do", "backlog", "selected for development"},
                "in progress": {"in progress", "in development", "started"},
                "resolved": {"done", "resolved", "closed"},
            }
            accepted = aliases.get(target_status.lower(), {target_status.lower()})
            issue = jira_request("GET", f"/rest/api/3/issue/{existing['jira_key']}?fields=status").json()
            current = str(((issue.get("fields") or {}).get("status") or {}).get("name") or "").lower()
            if current in accepted:
                transition_result = "already_in_sync"
                sync_record = True
            else:
                transitions = jira_request(
                    "GET", f"/rest/api/3/issue/{existing['jira_key']}/transitions"
                ).json().get("transitions", [])
                match = next(
                    (item for item in transitions
                     if str((item.get("to") or {}).get("name", "")).lower() in accepted),
                    None,
                )
                if match:
                    jira_request(
                        "POST", f"/rest/api/3/issue/{existing['jira_key']}/transitions",
                        json_body={"transition": {"id": match["id"]}},
                    )
                    transition_result = f"transitioned_to_{target_status}"
                    sync_record = True
                else:
                    transition_result = "no_matching_jira_transition"

        if sync_record:
            with connect() as conn:
                conn.execute(
                    "UPDATE m3_jira_links SET last_synced_status=?,updated_at=? WHERE ticket_id=?",
                    (target_status, now_iso(), ticket_id),
                )

        record_portal_event(ticket_id, "jira_synced", "Jira issue synchronised", f"Linked Jira issue {existing['jira_key']}.")
        return {
            "ticket_id": ticket_id,
            "jira_key": existing["jira_key"],
            "jira_id": existing.get("jira_id"),
            "jira_url": existing["jira_url"],
            "created": created,
            "supportpilot_status": target_status,
            "status_sync": transition_result,
        }
