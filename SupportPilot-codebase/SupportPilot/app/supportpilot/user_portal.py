"""Server-side customer accounts and owner-scoped ticket history for SupportPilot.

This module is an additive overlay: it reuses the existing TicketPipeline,
TicketRequest schema, SQLite database path, and ticket persistence functions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from .config import DB_PATH
from .db import connect, get_ticket, init_db, save_ticket
from .schemas import TicketRequest


PASSWORD_ITERATIONS = 260_000
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=256)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_email(value: str) -> str:
    email = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _init_portal_tables() -> None:
    init_db()
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supportpilot_users (
                email TEXT PRIMARY KEY COLLATE NOCASE,
                name TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supportpilot_portal_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS supportpilot_ticket_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(ticket_id) REFERENCES tickets(ticket_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_supportpilot_ticket_events "
            "ON supportpilot_ticket_events(ticket_id, created_at, event_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_supportpilot_users_email "
            "ON supportpilot_users(email)"
        )


def _token_secret() -> bytes:
    _init_portal_tables()
    with connect() as conn:
        row = conn.execute(
            "SELECT setting_value FROM supportpilot_portal_settings WHERE setting_key='token_secret'"
        ).fetchone()
        if row:
            return bytes.fromhex(row["setting_value"])
        secret = secrets.token_hex(32)
        conn.execute(
            "INSERT INTO supportpilot_portal_settings(setting_key, setting_value) VALUES('token_secret', ?)",
            (secret,),
        )
        return bytes.fromhex(secret)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _issue_token(user: dict[str, str]) -> str:
    payload = {
        "sub": user["email"],
        "name": user["name"],
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    encoded = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(_token_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64url(signature)}"


def _decode_token(token: str) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = _b64url(hmac.new(
            _token_secret(), encoded.encode("ascii"), hashlib.sha256
        ).digest())
        if not hmac.compare_digest(supplied_signature, expected):
            raise ValueError("Invalid signature")
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("Expired token")
        email = _normalise_email(str(payload.get("sub", "")))
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Your session is invalid or has expired. Sign in again.") from exc

    with connect() as conn:
        row = conn.execute(
            "SELECT email, name FROM supportpilot_users WHERE email=?", (email,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="The account for this session no longer exists.")
    return {"email": row["email"], "name": row["name"]}


def _current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to access your support workspace.")
    return _decode_token(authorization.split(" ", 1)[1].strip())


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return digest.hex()


def _public_user(row: Any) -> dict[str, str]:
    return {"name": row["name"], "email": row["email"]}


def _create_ticket_record(ticket_id: str, ticket: TicketRequest, result: dict[str, Any], *, response: bool = False) -> dict[str, Any]:
    predictions = result.get("predictions") or {}
    return {
        "ticket_id": ticket_id,
        "created_at": _utc_now(),
        "subject": ticket.subject,
        "body": ticket.body,
        "language": ticket.language,
        "queue": (predictions.get("queue") or {}).get("label"),
        "priority": (predictions.get("priority") or {}).get("label"),
        "type": (predictions.get("type") or {}).get("label"),
        "tags": result.get("tags", []),
        "status": result.get("status", "classified"),
        "workflow_status": "Open",
        "escalated": result.get("escalated", False),
        "response_draft": result.get("response_draft") if response else None,
        "sources": result.get("sources", []) if response else [],
        "predictions": predictions,
        "model_status": json.dumps(result.get("model_health", {}), ensure_ascii=False),
        "requester_name": ticket.requester_name,
        "requester_email": ticket.requester_email,
        "business_impact": ticket.business_impact,
        "contact_method": ticket.contact_method,
    }


def _add_event(ticket_id: str, event_type: str, title: str, description: str = "") -> None:
    _init_portal_tables()
    with connect() as conn:
        conn.execute(
            """INSERT INTO supportpilot_ticket_events
               (ticket_id, event_type, title, description, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (ticket_id, event_type, title, description, _utc_now()),
        )


def _record_creation_events(ticket_id: str, result: dict[str, Any]) -> None:
    _init_portal_tables()
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM supportpilot_ticket_events WHERE ticket_id=? AND event_type='ticket_submitted' LIMIT 1",
            (ticket_id,),
        ).fetchone()
    if exists:
        return
    predictions = result.get("predictions") or {}
    category = (predictions.get("queue") or {}).get("label") or "Pending"
    ticket_type = (predictions.get("type") or {}).get("label") or "Pending"
    priority = (predictions.get("priority") or {}).get("label") or "Pending"
    _add_event(ticket_id, "ticket_submitted", "Ticket submitted", "Your support request was received by SupportPilot.")
    _add_event(
        ticket_id,
        "classification_completed",
        "AI classification completed",
        f"Ticket type: {ticket_type}. Category: {category}. Priority: {priority}.",
    )


def record_status_event(ticket_id: str, old_status: str, new_status: str) -> None:
    """Called by the existing administrator status endpoint after a successful update."""
    if old_status == new_status:
        return
    _add_event(
        ticket_id,
        "workflow_status_changed",
        f"Status changed to {new_status}",
        f"The support workflow moved from {old_status} to {new_status}.",
    )


def _ticket_events(ticket_id: str) -> list[dict[str, Any]]:
    _init_portal_tables()
    with connect() as conn:
        rows = conn.execute(
            """SELECT event_type, title, description, created_at
               FROM supportpilot_ticket_events
               WHERE ticket_id=? ORDER BY created_at ASC, event_id ASC""",
            (ticket_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_user_portal_router(pipeline: Any) -> APIRouter:
    router = APIRouter(tags=["User portal"])

    @router.post("/auth/register")
    def register(request: RegisterRequest):
        _init_portal_tables()
        email = _normalise_email(request.email)
        name = request.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="Name must contain at least 2 characters.")
        salt = secrets.token_bytes(16)
        password_hash = _hash_password(request.password, salt)
        try:
            with connect() as conn:
                conn.execute(
                    """INSERT INTO supportpilot_users(email, name, password_salt, password_hash, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (email, name, salt.hex(), password_hash, _utc_now()),
                )
        except Exception as exc:
            if "UNIQUE" in str(exc).upper() or "PRIMARY KEY" in str(exc).upper():
                raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.") from exc
            raise
        user = {"name": name, "email": email}
        return {"access_token": _issue_token(user), "token_type": "bearer", "user": user}

    @router.post("/auth/login")
    def login(request: LoginRequest):
        _init_portal_tables()
        email = _normalise_email(request.email)
        with connect() as conn:
            row = conn.execute(
                "SELECT email, name, password_salt, password_hash FROM supportpilot_users WHERE email=?",
                (email,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=401, detail="Email address or password is incorrect.")
        calculated = _hash_password(request.password, bytes.fromhex(row["password_salt"]))
        if not hmac.compare_digest(calculated, row["password_hash"]):
            raise HTTPException(status_code=401, detail="Email address or password is incorrect.")
        user = _public_user(row)
        return {"access_token": _issue_token(user), "token_type": "bearer", "user": user}

    @router.get("/auth/me")
    def who_am_i(user: dict[str, str] = Depends(_current_user)):
        return {"user": user}

    @router.post("/user/tickets/predict")
    def predict_for_user(ticket: TicketRequest, user: dict[str, str] = Depends(_current_user)):
        ticket_id = f"SP-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"
        owned_ticket = ticket.model_copy(update={
            "ticket_id": ticket_id,
            "requester_name": user["name"],
            "requester_email": user["email"],
        })
        result = pipeline.predict(owned_ticket.subject, owned_ticket.body)
        save_ticket(_create_ticket_record(ticket_id, owned_ticket, result))
        _record_creation_events(ticket_id, result)
        return {"ticket_id": ticket_id, **result}

    @router.get("/user/tickets")
    def my_tickets(
        limit: int = Query(default=100, ge=1, le=250),
        user: dict[str, str] = Depends(_current_user),
    ):
        _init_portal_tables()
        with connect() as conn:
            rows = conn.execute(
                """SELECT ticket_id FROM tickets
                   WHERE lower(requester_email)=lower(?)
                   ORDER BY created_at DESC LIMIT ?""",
                (user["email"], limit),
            ).fetchall()
        tickets = [get_ticket(row["ticket_id"]) for row in rows]
        return {"tickets": [ticket for ticket in tickets if ticket is not None], "count": len(tickets)}

    @router.get("/user/tickets/{ticket_id}")
    def my_ticket_by_id(ticket_id: str, user: dict[str, str] = Depends(_current_user)):
        ticket = get_ticket(ticket_id)
        if ticket is None or str(ticket.get("requester_email") or "").lower() != user["email"].lower():
            # Do not reveal whether another user's ticket ID exists.
            raise HTTPException(status_code=404, detail="Ticket not found in your account.")
        ticket["events"] = _ticket_events(ticket_id)
        return ticket

    @router.post("/user/tickets/{ticket_id}/resolve")
    def resolve_for_user(ticket_id: str, ticket: TicketRequest, user: dict[str, str] = Depends(_current_user)):
        existing = get_ticket(ticket_id)
        if existing is None or str(existing.get("requester_email") or "").lower() != user["email"].lower():
            raise HTTPException(status_code=404, detail="Ticket not found in your account.")
        owned_ticket = ticket.model_copy(update={
            "ticket_id": ticket_id,
            "requester_name": user["name"],
            "requester_email": user["email"],
        })
        result = pipeline.resolve(owned_ticket.subject, owned_ticket.body, owned_ticket.language)
        save_ticket(_create_ticket_record(ticket_id, owned_ticket, result, response=True))
        if result.get("response_draft"):
            _add_event(ticket_id, "ai_response_prepared", "AI-assisted response prepared", "A draft response and suggested next steps are available for review.")
        return {"ticket_id": ticket_id, **result}

    return router
