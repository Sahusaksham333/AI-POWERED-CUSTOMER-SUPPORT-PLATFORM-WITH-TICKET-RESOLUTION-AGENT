from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class TicketRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ticket_id: str | None = Field(default=None, min_length=8, max_length=100)
    subject: str = Field(min_length=3, max_length=500)
    body: str = Field(min_length=5, max_length=20000)
    language: str = Field(default="auto", max_length=20)
    requester_name: str | None = Field(default=None, max_length=120)
    requester_email: str | None = Field(default=None, max_length=320)
    business_impact: Literal["low", "medium", "high", "critical"] = "medium"
    contact_method: Literal["Email", "Phone", "Chat"] = "Email"


class TicketStatusRequest(BaseModel):
    status: Literal["Open", "In Progress", "Resolved"]


class IntegrationTicketRequest(BaseModel):
    ticket_id: str = Field(min_length=8, max_length=100)


class EmailTicketRequest(IntegrationTicketRequest):
    recipient: str = Field(min_length=5, max_length=320)


class TicketPrediction(BaseModel):
    ticket_id: str
    queue: dict
    type: dict
    priority: dict
    tags: list[dict]
    escalated: bool
    escalation_reasons: list[str]
    model_health: dict


class TicketResolution(TicketPrediction):
    sources: list[dict]
    response_draft: str
    generation_error: str | None = None
    status: str
