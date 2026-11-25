"""Plain-text email composition and SMTP delivery adapter."""
from __future__ import annotations
import hashlib
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any
from ...db import get_ticket
from ..settings import email_configured


def build_email_body(row: dict[str, Any]) -> str:
    payload = json.loads(row.get("payload_json") or "{}")
    ticket = get_ticket(row["ticket_id"]) or {}
    event_type = row["event_type"]
    ticket_id = row["ticket_id"]
    status = ticket.get("workflow_status") or "Open"

    if event_type == "ticket_created":
        return (
            f"Hello {ticket.get('requester_name') or 'there'},\n\n"
            "SupportPilot has received your support request.\n\n"
            f"Ticket: {ticket_id}\nIssue: {ticket.get('subject') or row['subject']}\n"
            f"Priority: {ticket.get('priority') or 'Pending classification'}\nStatus: {status}\n\n"
            "You can follow the ticket in the SupportPilot portal. Do not reply with passwords, MFA codes or access tokens.\n\n"
            "SupportPilot Support Team"
        )
    if event_type == "ticket_status_changed":
        return (
            f"Hello {ticket.get('requester_name') or 'there'},\n\n"
            f"Your SupportPilot ticket {ticket_id} has been updated.\n"
            f"Issue: {ticket.get('subject') or row['subject']}\nCurrent status: {status}\n\n"
            "Sign in to the SupportPilot portal to review the latest progress.\n\nSupportPilot Support Team"
        )
    if event_type == "ai_response_approved":
        body = str(payload.get("body_text") or "").strip()
        return (
            f"Hello {ticket.get('requester_name') or 'there'},\n\n"
            f"SupportPilot support has reviewed the following guidance for ticket {ticket_id}:\n\n"
            f"{body}\n\n"
            "These steps are based on the referenced support knowledge and may require support-team follow-up. "
            "Please report whether they resolved the issue through the SupportPilot portal.\n\nSupportPilot Support Team"
        )
    return f"Your SupportPilot ticket {ticket_id} has an update. Current status: {status}."


def send_smtp(row: dict[str, Any]) -> str:
    if not email_configured():
        raise RuntimeError("Email automation is disabled or SMTP credentials are incomplete.")
    host = os.getenv("SUPPORTPILOT_SMTP_HOST", "")
    port = int(os.getenv("SUPPORTPILOT_SMTP_PORT", "587"))
    username = os.getenv("SUPPORTPILOT_SMTP_USERNAME", "")
    password = os.getenv("SUPPORTPILOT_SMTP_PASSWORD", "")
    sender = os.getenv("SUPPORTPILOT_SMTP_FROM", username)
    use_ssl = os.getenv("SUPPORTPILOT_SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    use_tls = os.getenv("SUPPORTPILOT_SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

    message = EmailMessage()
    message["From"] = sender
    message["To"] = row["recipient_email"]
    message["Subject"] = row["subject"]
    stable_id = hashlib.sha256(row["event_key"].encode()).hexdigest()[:28]
    message["Message-ID"] = f"<supportpilot-{stable_id}@local.supportpilot>"
    message.set_content(build_email_body(row))

    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            if use_tls:
                server.starttls(context=context)
            server.login(username, password)
            server.send_message(message)
    return message["Message-ID"]
