"""Environment-backed configuration helpers for Milestone 3."""
from __future__ import annotations
import os


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def email_configured() -> bool:
    return env_bool("SUPPORTPILOT_EMAIL_AUTOMATION_ENABLED") and all(
        os.getenv(key, "").strip()
        for key in (
            "SUPPORTPILOT_SMTP_HOST",
            "SUPPORTPILOT_SMTP_USERNAME",
            "SUPPORTPILOT_SMTP_PASSWORD",
            "SUPPORTPILOT_SMTP_FROM",
        )
    )


def jira_configured() -> bool:
    return all(
        os.getenv(key, "").strip()
        for key in (
            "SUPPORTPILOT_JIRA_BASE_URL",
            "SUPPORTPILOT_JIRA_EMAIL",
            "SUPPORTPILOT_JIRA_API_TOKEN",
            "SUPPORTPILOT_JIRA_PROJECT_KEY",
        )
    )


def jira_auto_create() -> bool:
    return env_bool("SUPPORTPILOT_JIRA_AUTO_CREATE")


def jira_auto_sync() -> bool:
    return env_bool("SUPPORTPILOT_JIRA_AUTO_SYNC")


def email_automation_enabled() -> bool:
    return env_bool("SUPPORTPILOT_EMAIL_AUTOMATION_ENABLED")
