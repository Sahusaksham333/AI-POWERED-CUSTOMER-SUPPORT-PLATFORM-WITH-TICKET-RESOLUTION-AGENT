"""SQLite persistence for local SupportPilot."""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from .config import DB_PATH


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                language TEXT,
                queue TEXT,
                priority TEXT,
                ticket_type TEXT,
                tags_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'classified',
                workflow_status TEXT NOT NULL DEFAULT 'Open',
                escalated INTEGER NOT NULL DEFAULT 0,
                response_draft TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                predictions_json TEXT NOT NULL DEFAULT '{}',
                model_status TEXT,
                requester_name TEXT,
                requester_email TEXT,
                business_impact TEXT NOT NULL DEFAULT 'medium',
                contact_method TEXT NOT NULL DEFAULT 'Email'
            )
        """)
        # Migrate databases created by earlier SupportPilot versions without losing tickets.
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(tickets)")}
        migrations = {
            "workflow_status": "TEXT NOT NULL DEFAULT 'Open'",
            "predictions_json": "TEXT NOT NULL DEFAULT '{}'",
            "requester_name": "TEXT",
            "requester_email": "TEXT",
            "business_impact": "TEXT NOT NULL DEFAULT 'medium'",
            "contact_method": "TEXT NOT NULL DEFAULT 'Email'",
        }
        for column, definition in migrations.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {column} {definition}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_created_at ON tickets(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_queue ON tickets(queue)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tickets_workflow_status ON tickets(workflow_status)")


def save_ticket(ticket: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    init_db()
    with connect() as conn:
        conn.execute("""
            INSERT INTO tickets (
                ticket_id, created_at, subject, body, language, queue, priority,
                ticket_type, tags_json, status, workflow_status, escalated,
                response_draft, sources_json, predictions_json, model_status,
                requester_name, requester_email, business_impact, contact_method
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET
                subject=excluded.subject, body=excluded.body, language=excluded.language,
                queue=excluded.queue, priority=excluded.priority, ticket_type=excluded.ticket_type,
                tags_json=excluded.tags_json, status=excluded.status, escalated=excluded.escalated,
                response_draft=excluded.response_draft, sources_json=excluded.sources_json,
                predictions_json=excluded.predictions_json, model_status=excluded.model_status,
                requester_name=COALESCE(excluded.requester_name, tickets.requester_name),
                requester_email=COALESCE(excluded.requester_email, tickets.requester_email),
                business_impact=excluded.business_impact, contact_method=excluded.contact_method
        """, (
            ticket["ticket_id"], ticket.get("created_at", now), ticket.get("subject", ""),
            ticket.get("body", ""), ticket.get("language", "auto"), ticket.get("queue"),
            ticket.get("priority"), ticket.get("type"),
            json.dumps(ticket.get("tags", []), ensure_ascii=False),
            ticket.get("status", "classified"), ticket.get("workflow_status", "Open"),
            int(bool(ticket.get("escalated", False))), ticket.get("response_draft"),
            json.dumps(ticket.get("sources", []), ensure_ascii=False),
            json.dumps(ticket.get("predictions", {}), ensure_ascii=False),
            ticket.get("model_status", "unknown"), ticket.get("requester_name"),
            ticket.get("requester_email"), ticket.get("business_impact", "medium"),
            ticket.get("contact_method", "Email"),
        ))


def _decode_ticket(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["tags"] = json.loads(result.pop("tags_json", "[]") or "[]")
    result["sources"] = json.loads(result.pop("sources_json", "[]") or "[]")
    result["predictions"] = json.loads(result.pop("predictions_json", "{}") or "{}")
    result["escalated"] = bool(result.get("escalated"))
    return result


def get_ticket(ticket_id: str) -> dict[str, Any] | None:
    init_db()
    with connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    return _decode_ticket(row) if row else None


def list_tickets(limit: int = 250) -> list[dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 1000))
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_decode_ticket(row) for row in rows]


def update_workflow_status(ticket_id: str, status: str) -> bool:
    init_db()
    with connect() as conn:
        cursor = conn.execute(
            "UPDATE tickets SET workflow_status=? WHERE ticket_id=?", (status, ticket_id)
        )
    return cursor.rowcount > 0


def get_analytics() -> dict[str, Any]:
    init_db()
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        escalated = conn.execute("SELECT COUNT(*) FROM tickets WHERE escalated=1").fetchone()[0]
        statuses = [dict(r) for r in conn.execute(
            "SELECT workflow_status AS status, COUNT(*) AS count FROM tickets GROUP BY workflow_status ORDER BY count DESC"
        )]
        queues = [dict(r) for r in conn.execute(
            "SELECT COALESCE(queue, 'unavailable') AS queue, COUNT(*) AS count FROM tickets GROUP BY queue ORDER BY count DESC"
        )]
        priorities = [dict(r) for r in conn.execute(
            "SELECT COALESCE(priority, 'unavailable') AS priority, COUNT(*) AS count FROM tickets GROUP BY priority ORDER BY count DESC"
        )]
        recent = [dict(r) for r in conn.execute(
            "SELECT ticket_id, created_at, subject, queue, priority, workflow_status AS status, escalated FROM tickets ORDER BY created_at DESC LIMIT 25"
        )]
    return {"total_tickets": total, "escalated_tickets": escalated, "statuses": statuses,
            "queues": queues, "priorities": priorities, "recent_tickets": recent}
