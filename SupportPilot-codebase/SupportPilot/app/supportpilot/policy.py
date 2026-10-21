"""Conservative escalation policy, independent of model dependencies."""
from __future__ import annotations
from typing import Any
import re
from .config import MIN_CLASSIFIER_CONFIDENCE

SECURITY_TERMS = re.compile(
    r"\b(data breach|ransomware|malware|phishing|unauthori[sz]ed access|security incident|cyberattack|kompromittiert|datenverletzung)\b",
    re.IGNORECASE,
)
OUTAGE_TERMS = re.compile(r"\b(all users|company[- ]wide|production outage|entire network|system[- ]wide outage)\b", re.I)


def escalation_reason(subject: str, body: str, priority: dict[str, Any], predictions: dict[str, Any]) -> list[str]:
    combined = f"{subject}\n{body}"
    reasons = []
    if SECURITY_TERMS.search(combined):
        reasons.append("possible_security_incident")
    if OUTAGE_TERMS.search(combined):
        reasons.append("possible_widespread_outage")
    if (priority.get("label") or "").lower() == "high":
        reasons.append("high_predicted_priority")
    for target in ("queue", "priority", "type"):
        pred = predictions.get(target, {})
        if pred.get("available") and pred.get("confidence") is not None and pred["confidence"] < MIN_CLASSIFIER_CONFIDENCE:
            reasons.append(f"low_{target}_confidence")
    if not any(p.get("available") for p in predictions.values() if isinstance(p, dict)):
        reasons.append("classification_models_not_trained")
    return reasons
