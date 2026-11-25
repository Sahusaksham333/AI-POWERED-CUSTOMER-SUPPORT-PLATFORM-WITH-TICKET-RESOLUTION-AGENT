"""Shared utilities and compatibility bridge to the customer ticket timeline."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any
from ..db import connect

UTC = timezone.utc


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def to_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def record_portal_event(ticket_id: str, event_type: str, title: str, description: str = "") -> None:
    """Write to the optional customer-history table without blocking M3."""
    try:
        with connect() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "supportpilot_ticket_events" not in tables:
                return
            conn.execute(
                """INSERT INTO supportpilot_ticket_events
                   (ticket_id,event_type,title,description,created_at)
                   VALUES(?,?,?,?,?)""",
                (ticket_id, event_type, title, description, now_iso()),
            )
    except Exception:
        # The M3 agent/Jira workflow must not fail because the optional portal history
        # overlay is not installed in this particular deployment.
        return
