"""SQLite persistence for M3 runs, events, Jira links and durable email outbox."""
from __future__ import annotations
import json
from typing import Any
from ..db import connect
from .utils import now_iso, to_json


def init_m3_schema() -> None:
    """Create additive M3 tables. Existing ticket and model tables are untouched."""
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS m3_agent_runs (
                run_id TEXT PRIMARY KEY,
                ticket_id TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                result_json TEXT NOT NULL DEFAULT '{}',
                started_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_m3_agent_runs_ticket ON m3_agent_runs(ticket_id, started_at)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS m3_agent_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ticket_id TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                output_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_m3_agent_events_run ON m3_agent_events(run_id, event_id)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS m3_jira_links (
                ticket_id TEXT PRIMARY KEY,
                jira_key TEXT NOT NULL,
                jira_id TEXT,
                jira_url TEXT NOT NULL,
                last_synced_status TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS m3_outbox (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                ticket_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                recipient_email TEXT,
                subject TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT,
                provider_message_id TEXT,
                created_at TEXT NOT NULL,
                sent_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_m3_outbox_due ON m3_outbox(status, next_attempt_at)")
        # A process restart may occur while a message was in-flight. Requeueing is
        # at-least-once: duplicate delivery remains possible after ambiguous SMTP acceptance.
        conn.execute(
            "UPDATE m3_outbox SET status='pending', next_attempt_at=? WHERE status='sending'",
            (now_iso(),),
        )


def enqueue_outbox(
    *, event_key: str, ticket_id: str, event_type: str,
    recipient: str | None, subject: str, payload: dict[str, Any],
) -> int | None:
    with connect() as conn:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO m3_outbox
               (event_key,ticket_id,event_type,recipient_email,subject,payload_json,
                status,attempt_count,next_attempt_at,created_at)
               VALUES(?,?,?,?,?,?,'pending',0,?,?)""",
            (event_key, ticket_id, event_type, recipient, subject, to_json(payload), now_iso(), now_iso()),
        )
        if cursor.rowcount:
            return int(cursor.lastrowid)
        row = conn.execute("SELECT event_id FROM m3_outbox WHERE event_key=?", (event_key,)).fetchone()
        return int(row["event_id"]) if row else None


def insert_agent_event(
    run_id: str, ticket_id: str, agent: str, status: str, message: str, output: Any = None,
) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO m3_agent_events
               (run_id,ticket_id,agent_name,status,message,output_json,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (run_id, ticket_id, agent, status, message, to_json(output or {}), now_iso()),
        )


def start_agent_run(run_id: str, ticket_id: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO m3_agent_runs(run_id,ticket_id,status,result_json,started_at) VALUES(?,?,'running','{}',?)",
            (run_id, ticket_id, now_iso()),
        )


def complete_agent_run(run_id: str, ticket_id: str, result: dict[str, Any], decision: str,
                       draft: str | None, sources: list[dict[str, Any]], escalated: bool) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE m3_agent_runs SET status='completed',decision=?,result_json=?,completed_at=? WHERE run_id=?",
            (decision, to_json(result), now_iso(), run_id),
        )
        # Preserve existing ticket intake/classification fields while updating M3 outputs.
        conn.execute(
            "UPDATE tickets SET response_draft=?,sources_json=?,escalated=?,status=? WHERE ticket_id=?",
            (draft, to_json(sources), int(escalated),
             "pending_human_review" if escalated else "draft_ready_for_review", ticket_id),
        )


def fail_agent_run(run_id: str, failure: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE m3_agent_runs SET status='failed',decision='error',result_json=?,completed_at=? WHERE run_id=?",
            (to_json(failure), now_iso(), run_id),
        )


def latest_agent_run(ticket_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT run_id,status,decision,result_json,started_at,completed_at
               FROM m3_agent_runs WHERE ticket_id=? ORDER BY started_at DESC LIMIT 1""",
            (ticket_id,),
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    try:
        result["result"] = json.loads(result.pop("result_json") or "{}")
    except json.JSONDecodeError:
        result["result"] = {}
    return result
