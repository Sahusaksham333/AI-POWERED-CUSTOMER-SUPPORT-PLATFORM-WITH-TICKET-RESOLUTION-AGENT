"""Diagnosis agent: classifier signals, risk scan and missing-information detection."""
from __future__ import annotations
import re
from typing import Any
from ...config import MIN_CLASSIFIER_CONFIDENCE
from .policy import detect_risks


def route_team(queue: str | None, risk_flags: list[str]) -> str:
    if any(flag in risk_flags for flag in ("possible_security_incident", "physical_safety_risk")):
        return "Security / Safety Response"
    text = (queue or "").lower()
    if any(x in text for x in ("network", "outage", "vpn", "connect")):
        return "Network Support"
    if any(x in text for x in ("hardware", "device", "printer")):
        return "Endpoint & Hardware Support"
    if any(x in text for x in ("software", "product", "application")):
        return "Applications Support"
    if any(x in text for x in ("account", "access", "identity", "security")):
        return "Identity & Access Support"
    return "IT Service Desk"


def missing_information(subject: str, body: str, queue: str | None) -> list[str]:
    text = f"{subject}\n{body}".lower()
    questions: list[str] = []
    if not re.search(r"\b(error|code|message|failed|failure|timeout|timed out)\b", text):
        questions.append("Please share the exact error message or code, if one appears.")
    if not re.search(r"\b(since|started|yesterday|today|hours?|days?|date)\b", text):
        questions.append("When did the issue first start, and does it happen consistently?")
    category = (queue or "").lower()
    if any(word in category for word in ("network", "vpn", "connect")) and not re.search(
        r"\b(vpn|wifi|wi-fi|ethernet|network)\b", text
    ):
        questions.append("Which network or connection method is affected?")
    if any(word in category for word in ("hardware", "device")) and not re.search(
        r"\b(model|serial|laptop|desktop|printer|monitor)\b", text
    ):
        questions.append("What device model is affected?")
    return questions[:4]


def run_diagnosis(pipeline: Any, subject: str, body: str) -> dict[str, Any]:
    prediction = pipeline.predict(subject, body)
    predictions = prediction.get("predictions", {})
    risk_flags = detect_risks(f"{subject}\n{body}")
    for key in ("queue", "priority", "type"):
        item = predictions.get(key) or {}
        if item.get("available") and item.get("confidence") is not None:
            if float(item["confidence"]) < MIN_CLASSIFIER_CONFIDENCE:
                risk_flags.append(f"low_{key}_confidence")
    risk_flags.extend(prediction.get("escalation_reasons", []))
    queue = (predictions.get("queue") or {}).get("label")
    output = {
        "queue": queue,
        "type": (predictions.get("type") or {}).get("label"),
        "priority": (predictions.get("priority") or {}).get("label"),
        "predictions": predictions,
        "tags": prediction.get("tags", []),
        "risk_flags": sorted(set(risk_flags)),
        "information_to_collect": missing_information(subject, body, queue),
    }
    return {"raw": prediction, "output": output, "risk_flags": sorted(set(risk_flags))}
