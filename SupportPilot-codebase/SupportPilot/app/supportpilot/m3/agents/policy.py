"""Deterministic risk and content safety checks shared by specialist agents."""
from __future__ import annotations
import re

SECURITY_RISK = re.compile(
    r"\b(ransomware|malware|phishing|data breach|security incident|unauthori[sz]ed access|"
    r"account compromised|credential theft|lost or stolen device|data exfiltration)\b", re.I
)
WIDESPREAD_RISK = re.compile(
    r"\b(company[- ]wide|all users|entire network|production outage|system[- ]wide outage|"
    r"multiple departments|many employees)\b", re.I
)
PHYSICAL_RISK = re.compile(
    r"\b(smoke|burning smell|electric shock|swollen battery|liquid damage|sparking)\b", re.I
)
UNSAFE_DRAFT = re.compile(
    r"\b(disable (?:the )?(?:firewall|antivirus|endpoint protection)|turn off (?:the )?"
    r"(?:firewall|antivirus)|bypass mfa|share your password|send your password|"
    r"delete system files|format (?:the )?drive|wipe (?:the )?disk)\b", re.I
)


def detect_risks(text: str) -> list[str]:
    flags: list[str] = []
    if SECURITY_RISK.search(text):
        flags.append("possible_security_incident")
    if WIDESPREAD_RISK.search(text):
        flags.append("possible_widespread_outage")
    if PHYSICAL_RISK.search(text):
        flags.append("physical_safety_risk")
    return flags
