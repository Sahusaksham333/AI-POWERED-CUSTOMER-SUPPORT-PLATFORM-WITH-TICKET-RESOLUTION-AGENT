"""FastAPI entry point and static frontend for SupportPilot."""
from __future__ import annotations
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .supportpilot.schemas import (
    TicketRequest, TicketStatusRequest, IntegrationTicketRequest, EmailTicketRequest,
)
from .supportpilot.pipeline import TicketPipeline
from .supportpilot.db import init_db, save_ticket, get_analytics, get_ticket, list_tickets, update_workflow_status
from .supportpilot.config import ARTIFACTS_DIR

pipeline = TicketPipeline()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
METRICS_FILE = PROJECT_ROOT / "training" / "model_metrics.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="SupportPilot API",
    description="Local-first multilingual support-ticket classification, RAG and human-reviewed response drafting.",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


def _new_ticket_id() -> str:
    return f"SP-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:6].upper()}"


def _ticket_record(ticket_id: str, ticket: TicketRequest, result: dict, *, response: bool = False) -> dict:
    predictions = result["predictions"]
    return {
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "subject": ticket.subject,
        "body": ticket.body,
        "language": ticket.language,
        "queue": predictions.get("queue", {}).get("label"),
        "priority": predictions.get("priority", {}).get("label"),
        "type": predictions.get("type", {}).get("label"),
        "tags": result.get("tags", []),
        "status": result.get("status", "classified" if any(x.get("available") for x in predictions.values()) else "models_not_trained"),
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


@app.get("/health")
def health():
    return {"status": "ok", "services": pipeline.health()}


@app.post("/tickets/predict")
def predict_ticket(ticket: TicketRequest):
    ticket_id = ticket.ticket_id or _new_ticket_id()
    result = pipeline.predict(ticket.subject, ticket.body)
    save_ticket(_ticket_record(ticket_id, ticket, result))
    return {"ticket_id": ticket_id, **result}


@app.post("/tickets/resolve")
def resolve_ticket(ticket: TicketRequest):
    # A supplied ticket_id updates the existing record rather than creating a duplicate.
    ticket_id = ticket.ticket_id or _new_ticket_id()
    result = pipeline.resolve(ticket.subject, ticket.body, ticket.language)
    save_ticket(_ticket_record(ticket_id, ticket, result, response=True))
    return {"ticket_id": ticket_id, **result}


@app.get("/tickets")
def tickets(limit: int = Query(default=250, ge=1, le=1000)):
    return {"tickets": list_tickets(limit)}


@app.get("/tickets/{ticket_id}")
def get_ticket_by_id(ticket_id: str):
    record = get_ticket(ticket_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return record


@app.patch("/tickets/{ticket_id}/status")
def set_ticket_status(ticket_id: str, request: TicketStatusRequest):
    if not update_workflow_status(ticket_id, request.status):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket_id": ticket_id, "workflow_status": request.status}


@app.get("/analytics")
def analytics():
    return get_analytics()


@app.get("/models/performance")
def model_performance():
    if not METRICS_FILE.exists():
        raise HTTPException(status_code=404, detail="Training metrics file was not found")
    report = json.loads(METRICS_FILE.read_text(encoding="utf-8"))
    classifier_targets = pipeline.classifier.health().get("available_models", {})
    annotated = []
    for item in report.get("models", []):
        model = dict(item)
        key = model["key"]
        if key.startswith("textcnn_"):
            artifact_path = ARTIFACTS_DIR / key
            available = (artifact_path / "textcnn.pt").is_file() and (artifact_path / "tokenizer").is_dir()
        else:
            artifact_path = ARTIFACTS_DIR / key
            available = bool(classifier_targets.get(key, False))
        model["artifact_available"] = available
        model["artifact_path"] = str(artifact_path)
        annotated.append(model)
    report["models"] = annotated
    report["artifacts_directory"] = str(ARTIFACTS_DIR)
    report["classifier_device"] = pipeline.classifier.health().get("device", "unknown")
    return report


@app.post("/integrations/jira")
def jira_create(request: IntegrationTicketRequest):
    from .supportpilot.integrations import create_jira_issue
    try:
        return create_jira_issue(request.ticket_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Jira request failed: {exc}") from exc


@app.post("/integrations/email")
def email_send(request: EmailTicketRequest):
    from .supportpilot.integrations import send_ticket_email
    try:
        return send_ticket_email(request.ticket_id, request.recipient)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Email delivery failed: {exc}") from exc


# Serve the user-supplied, responsive HTML/CSS/JS application from the same origin as the API.
# This mount must remain after API routes so /docs and /tickets/* reach FastAPI first.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
