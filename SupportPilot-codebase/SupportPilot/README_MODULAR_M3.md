# SupportPilot Milestone 3 — Modular Code

This is a **module refactor** of the previous M3 overlay. It preserves the existing M3 HTTP routes and admin UI contract while decomposing the 40 KB `milestone3.py` implementation into smaller, focused Python modules.

## Module layout

```text
app/supportpilot/
├── milestone3.py                 # 4-line compatibility shim
└── m3/
    ├── __init__.py               # Public lifecycle exports
    ├── api.py                    # FastAPI route definitions and request schemas
    ├── settings.py               # Jira / SMTP configuration helpers
    ├── security.py               # M3 admin-key dependency
    ├── storage.py                # M3 SQLite schema, outbox and agent-run persistence
    ├── utils.py                  # UTC timestamps, JSON, portal event bridge
    ├── agents/
    │   ├── policy.py             # Deterministic risk and unsafe-text rules
    │   ├── diagnosis.py          # Existing classifier + routing/triage signals
    │   ├── retrieval.py          # Existing Chroma retrieval adapter
    │   ├── resolution.py         # Existing local Ollama response generator
    │   ├── validation.py         # Source/unsafe-content checks
    │   ├── escalation.py         # Team routing and human-review decision
    │   └── orchestrator.py       # Coordinates five agents and persists run trace
    ├── integrations/
    │   └── jira.py               # Jira Cloud REST client and ticket sync
    └── communications/
        ├── email.py              # Email composition and SMTP adapter
        └── worker.py             # Durable outbox, retry and worker lifecycle
```

## Install / migrate

This installer is intended for a project where the **previous M3 overlay is already installed**. Stop Uvicorn, extract the ZIP outside the project, then run from the existing project root:

```powershell
cd "S:\A Projects\AI-Powered Customer Support Platform with Ticket Resolution Agent\SupportPilot-codebase\SupportPilot"
.\.venv\Scripts\Activate.ps1
python "C:\Path\To\SupportPilot_Milestone_3_Modular\install_m3_modular.py"
```

The installer backs up the existing `app/supportpilot/m3/` package (if present) and `milestone3.py`. It then installs the modular package and leaves `milestone3.py` as a compatibility shim, so the existing imports in `app/main.py` continue to work. It does not modify the ticket schema or frontend files.

If the installer reports that `main.py` has no M3 lifecycle/router imports, do not force the installation. Install the original M3 overlay first or share the current `app/main.py` so the integration can be adapted safely.

## Run

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

M3 routes remain unchanged:

- `GET /m3/status`
- `POST /m3/tickets/{ticket_id}/agents/run`
- `GET /m3/tickets/{ticket_id}/agents/latest`
- `GET /m3/tickets/{ticket_id}/jira`
- `POST /m3/tickets/{ticket_id}/jira/sync`
- `POST /m3/tickets/{ticket_id}/email/ai-response`
- `GET /m3/outbox`
- `POST /m3/outbox/{event_id}/retry`
- `POST /m3/outbox/process-once`

All routes require `X-SupportPilot-Admin-Key`, sourced from `SUPPORTPILOT_ADMIN_API_KEY`. Copy only the relevant variables from `.env.m3.example` into your current `.env`; do not replace the existing `.env`.

## Responsibilities

- **Agents** only diagnose, retrieve, generate, validate and route. No agent directly emails users, closes tickets or performs system changes.
- **Jira service** owns HTTP calls and local issue mapping. Jira credentials are read only from environment variables.
- **Email service** owns message construction and SMTP. It never runs on the FastAPI event loop directly; the outbox worker performs delivery.
- **Outbox** stores durable events and retries transient failures. A `sent` event means SMTP accepted the message, not that the recipient read it.
- **API** validates requests, applies the admin-key dependency and delegates to the focused service modules.

## Validation / boundaries

The package is syntax-checked and its module imports and pure agent policy functions are smoke-tested. Jira and SMTP are external dependencies and must be tested with a non-production Jira project and dedicated test mailbox. The single-process SQLite worker is intended for local development; multi-process deployment should use a shared worker queue. No model training files or classifier artifacts are included in this package.
