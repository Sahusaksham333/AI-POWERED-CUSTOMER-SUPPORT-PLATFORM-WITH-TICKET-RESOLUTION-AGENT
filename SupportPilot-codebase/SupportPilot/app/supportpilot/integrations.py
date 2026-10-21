"""Opt-in Jira and SMTP integrations. Nothing is sent automatically."""
from __future__ import annotations
import os
import smtplib
from email.message import EmailMessage
from typing import Any
import requests
from .db import connect


def read_ticket(ticket_id: str) -> dict[str, Any] | None:
    import json
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["tags"] = json.loads(result.pop("tags_json", "[]"))
    result["sources"] = json.loads(result.pop("sources_json", "[]"))
    result["escalated"] = bool(result["escalated"])
    return result


def create_jira_issue(ticket_id: str) -> dict[str, Any]:
    base_url = os.getenv("SUPPORTPILOT_JIRA_BASE_URL", "").rstrip("/")
    email = os.getenv("SUPPORTPILOT_JIRA_EMAIL", "")
    token = os.getenv("SUPPORTPILOT_JIRA_API_TOKEN", "")
    project_key = os.getenv("SUPPORTPILOT_JIRA_PROJECT_KEY", "")
    if not all((base_url, email, token, project_key)):
        raise RuntimeError("Jira is not configured. Set SUPPORTPILOT_JIRA_BASE_URL, SUPPORTPILOT_JIRA_EMAIL, SUPPORTPILOT_JIRA_API_TOKEN, and SUPPORTPILOT_JIRA_PROJECT_KEY in .env.")
    ticket = read_ticket(ticket_id)
    if ticket is None:
        raise LookupError(f"Ticket not found: {ticket_id}")
    description_text = (
        f"SupportPilot ticket ID: {ticket_id}\n"
        f"Predicted queue: {ticket.get('queue') or 'unavailable'}\n"
        f"Predicted priority: {ticket.get('priority') or 'unavailable'}\n\n"
        f"Original ticket body:\n{ticket.get('body', '')}\n\n"
        f"AI response draft (requires human review):\n{ticket.get('response_draft') or 'No response draft available.'}"
    )
    # Jira Cloud REST API v3 expects Atlassian Document Format for descriptions.
    adf = {"type": "doc", "version": 1, "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line[:30000]}]}
        for line in description_text.splitlines() if line.strip()
    ]}
    payload = {"fields": {"project": {"key": project_key},
        "summary": f"[SupportPilot] {ticket.get('subject', 'Support ticket')}"[:250],
        "description": adf, "issuetype": {"name": os.getenv("SUPPORTPILOT_JIRA_ISSUE_TYPE", "Task")},
        "labels": ["supportpilot", f"priority-{(ticket.get('priority') or 'unknown').lower()}"]}}
    response = requests.post(f"{base_url}/rest/api/3/issue", json=payload,
                             auth=(email, token), headers={"Accept": "application/json"}, timeout=20)
    if not response.ok:
        raise RuntimeError(f"Jira returned HTTP {response.status_code}: {response.text[:500]}")
    data = response.json()
    return {"key": data.get("key"), "id": data.get("id"), "url": f"{base_url}/browse/{data.get('key')}", "created": True}


def send_ticket_email(ticket_id: str, recipient: str) -> dict[str, Any]:
    host = os.getenv("SUPPORTPILOT_SMTP_HOST", "")
    username = os.getenv("SUPPORTPILOT_SMTP_USERNAME", "")
    password = os.getenv("SUPPORTPILOT_SMTP_PASSWORD", "")
    sender = os.getenv("SUPPORTPILOT_SMTP_FROM", username)
    if not all((host, username, password, sender)):
        raise RuntimeError("SMTP is not configured. Set SUPPORTPILOT_SMTP_HOST, SUPPORTPILOT_SMTP_USERNAME, SUPPORTPILOT_SMTP_PASSWORD, and SUPPORTPILOT_SMTP_FROM in .env.")
    ticket = read_ticket(ticket_id)
    if ticket is None:
        raise LookupError(f"Ticket not found: {ticket_id}")
    message = EmailMessage()
    message["Subject"] = f"Support ticket update: {ticket.get('subject', '')}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "This message contains an AI-generated draft and must be reviewed before sending in a production workflow.\n\n"
        f"Ticket ID: {ticket_id}\nStatus: {ticket.get('status')}\n\n"
        f"Draft:\n{ticket.get('response_draft') or 'No response draft is available.'}\n\n"
        "This email was sent through the explicitly invoked SupportPilot integration."
    )
    port = int(os.getenv("SUPPORTPILOT_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(username, password)
        server.send_message(message)
    return {"sent": True, "recipient": recipient, "ticket_id": ticket_id}
