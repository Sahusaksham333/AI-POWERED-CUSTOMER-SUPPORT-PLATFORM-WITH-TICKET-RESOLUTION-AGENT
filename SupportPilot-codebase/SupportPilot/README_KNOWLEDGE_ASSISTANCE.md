# SupportPilot — Knowledge Retrieval + AI Assistance (User Portal)

This overlay adds two side-by-side self-service capabilities to the authenticated customer workspace:

1. **Knowledge Retrieval** — searches the indexed Chroma knowledge base and displays matching source excerpts without invoking the LLM.
2. **AI Assistance** — sends the user's issue through the existing `TicketPipeline.resolve()` flow, which retrieves knowledge and asks the configured Ollama model to draft grounded next steps. It does not create or alter a support ticket.

Both features are placed under one **Knowledge & AI** workspace tab. Existing ticket creation, account sign-in, ticket history, tracking, and ticket-specific AI resolution remain in place.

## Installation

1. Extract this archive.
2. Open PowerShell in the existing SupportPilot project root (the directory containing `app/` and `frontend/`).
3. Activate the same virtual environment used by the project.
4. Run:

```powershell
python install_knowledge_assistance.py
```

The installer backs up the existing `app/main.py` and the three customer frontend files. It adds one route module and registers it alongside the existing authenticated user-portal router. It does not alter model artifacts, training scripts, or the SQLite database.

## Required backend prerequisites

Your current project must already have:

- `app/supportpilot/user_portal.py` with server-side account authentication and `_current_user`;
- `app/supportpilot/pipeline.py` with `pipeline.retriever`, `pipeline.resolve()`, and the RAG components;
- the Milestone 2 dependencies installed;
- the Chroma index built and populated.

If RAG has not been installed, the installer deliberately stops rather than pretending these frontend controls can work without a retriever.

## Added authenticated API routes

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/user/knowledge/status` | Reports index readiness and indexed chunk count |
| POST | `/user/knowledge/search` | Retrieves source passages only |
| POST | `/user/knowledge/assist` | Retrieves sources and generates an AI-assisted response |

The routes depend on the existing bearer-token account authentication. Example request bodies:

```json
{"query":"VPN connection fails after login","top_k":4}
```

```json
{"query":"My laptop cannot connect to VPN after login. I have restarted it and still see a timeout.","language":"en"}
```

## Run and verify

Restart FastAPI, then sign in to the customer portal. Open **Knowledge & AI**.

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Verify route registration:

```powershell
$paths = (Invoke-RestMethod http://127.0.0.1:8000/openapi.json).paths
$paths.PSObject.Properties.Name | Where-Object { $_ -like '/user/knowledge/*' }
```

Expected:

- `/user/knowledge/status`
- `/user/knowledge/search`
- `/user/knowledge/assist`

After signing in, the browser should call `GET /user/knowledge/status` when the Knowledge & AI tab opens. Knowledge search calls `POST /user/knowledge/search`; assistance calls `POST /user/knowledge/assist`.

## Important behaviour and limitations

- The search card does **not** generate an answer; it shows retrieved passages and source metadata.
- The assistance card uses the existing RAG prompt and Ollama model. It returns the draft, source excerpts, escalation flag, and any generation error.
- If the Chroma index is empty, `/user/knowledge/status` reports not-ready and search/assistance return HTTP 503 with the backend readiness error.
- If Ollama is unavailable, the pipeline may return its safe fallback draft and a `generation_error`; the UI surfaces this condition.
- This is self-service guidance, not a substitute for approved IT policy or human support. The knowledge documents should be reviewed for accuracy and organisation-specific procedures.
