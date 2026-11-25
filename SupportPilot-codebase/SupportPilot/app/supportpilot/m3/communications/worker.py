"""Durable outbox claiming, retry scheduling and background worker lifecycle."""
from __future__ import annotations
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from ...db import connect
from ..integrations.jira import sync_ticket_to_jira
from ..settings import email_configured, jira_configured
from ..utils import now_iso, record_portal_event
from .email import send_smtp

_WORKER_STOP = threading.Event()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()


def claim_outbox_item() -> dict[str, Any] | None:
    now = now_iso()
    email_ready = email_configured()
    jira_ready = jira_configured()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT * FROM m3_outbox WHERE status='pending' AND next_attempt_at<=? ORDER BY event_id ASC LIMIT 25",
            (now,),
        ).fetchall()
        selected = next(
            (dict(row) for row in rows if
             ((row["event_type"].startswith("ticket_") or row["event_type"] == "ai_response_approved") and email_ready)
             or (row["event_type"] == "jira_sync" and jira_ready)),
            None,
        )
        if not selected:
            return None
        cursor = conn.execute(
            "UPDATE m3_outbox SET status='sending',attempt_count=attempt_count+1 WHERE event_id=? AND status='pending'",
            (selected["event_id"],),
        )
        if not cursor.rowcount:
            return None
        selected["attempt_count"] = int(selected.get("attempt_count", 0)) + 1
        selected["status"] = "sending"
        return selected


def finish_outbox_item(
    row: dict[str, Any], *, success: bool,
    provider_message_id: str | None = None, error: str | None = None,
) -> None:
    attempts = int(row.get("attempt_count", 1))
    if success:
        status, next_time = "sent", now_iso()
    elif attempts >= 5:
        status, next_time = "failed", now_iso()
    else:
        status = "pending"
        delay = min(3600, 15 * (2 ** max(0, attempts - 1)))
        next_time = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
    with connect() as conn:
        conn.execute(
            """UPDATE m3_outbox SET status=?,next_attempt_at=?,last_error=?,
               provider_message_id=?,sent_at=? WHERE event_id=?""",
            (status, next_time, (error or "")[:700] or None, provider_message_id,
             now_iso() if success else None, row["event_id"]),
        )
    if success:
        record_portal_event(
            row["ticket_id"], "communication_accepted", "Support email accepted by SMTP",
            f"A {row['event_type'].replace('_', ' ')} email was accepted by the SMTP server.",
        )


def process_outbox_once() -> bool:
    row = claim_outbox_item()
    if not row:
        return False
    try:
        if row["event_type"] == "jira_sync":
            sync_ticket_to_jira(row["ticket_id"], force_status_sync=True)
            provider_id = None
        else:
            provider_id = send_smtp(row)
        finish_outbox_item(row, success=True, provider_message_id=provider_id)
    except Exception as exc:
        finish_outbox_item(row, success=False, error=f"{type(exc).__name__}: {str(exc)[:600]}")
    return True


def _worker_loop() -> None:
    while not _WORKER_STOP.is_set():
        try:
            processed = process_outbox_once()
        except Exception:
            processed = False
        if not processed:
            _WORKER_STOP.wait(2.0)


def start_m3_worker() -> None:
    global _WORKER_THREAD
    with _WORKER_LOCK:
        if _WORKER_THREAD and _WORKER_THREAD.is_alive():
            return
        _WORKER_STOP.clear()
        _WORKER_THREAD = threading.Thread(
            target=_worker_loop, name="supportpilot-m3-outbox", daemon=True,
        )
        _WORKER_THREAD.start()


def stop_m3_worker() -> None:
    global _WORKER_THREAD
    _WORKER_STOP.set()
    thread = _WORKER_THREAD
    if thread and thread.is_alive():
        thread.join(timeout=5)
    _WORKER_THREAD = None


def worker_is_running() -> bool:
    return bool(_WORKER_THREAD and _WORKER_THREAD.is_alive())
