# M3 module map

| Module | Responsibility | Should not do |
|---|---|---|
| `api.py` | Defines authenticated FastAPI endpoints and delegates to services | Hold Jira/SMTP implementation details |
| `security.py` | Validates the M3 admin API key | Store credentials in source code |
| `settings.py` | Reads environment flags and checks integration configuration | Mutate ticket data |
| `storage.py` | Creates M3 tables and stores runs, events, outbox records | Call external APIs |
| `utils.py` | UTC timestamps, JSON serialization and optional portal timeline bridge | Run agents |
| `agents/diagnosis.py` | Reuses the ticket classifier and determines missing context/routing | Call an LLM |
| `agents/retrieval.py` | Reuses existing knowledge retriever | Generate answers |
| `agents/resolution.py` | Calls the existing local generator when sources exist | Email customers |
| `agents/validation.py` | Performs deterministic evidence and unsafe-text checks | Claim model-based verification |
| `agents/escalation.py` | Recommends team and review disposition | Change real IT infrastructure |
| `agents/orchestrator.py` | Runs specialist agents in order and persists execution trace | Integrate directly with Jira/SMTP |
| `integrations/jira.py` | Creates/reuses Jira issue and syncs workflow status | Send customer email |
| `communications/email.py` | Builds messages and sends through SMTP | Decide whether an AI draft is approved |
| `communications/worker.py` | Claims outbox events, retries and calls the selected adapter | Expose unauthenticated admin endpoints |

## Workflow

```text
Ticket
  -> Diagnosis Agent
  -> Knowledge Retrieval Agent
  -> Resolution Agent
  -> Validation Agent
  -> Escalation Agent
  -> Persisted run + optional Jira/approved-email actions
```

The agents share the existing `TicketPipeline`; the XLM-R classifier, Chroma index and Ollama model are not retrained or copied into this package.
