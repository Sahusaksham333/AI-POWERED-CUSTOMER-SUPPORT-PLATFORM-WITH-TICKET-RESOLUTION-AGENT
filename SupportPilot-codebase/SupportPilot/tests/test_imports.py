"""Import smoke test for all modular M3 service groups."""

def test_m3_public_api_imports():
    from app.supportpilot.m3 import create_m3_router, init_m3_schema, start_m3_worker, stop_m3_worker
    from app.supportpilot.m3.integrations.jira import sync_ticket_to_jira
    from app.supportpilot.m3.communications.worker import process_outbox_once
    assert all((create_m3_router, init_m3_schema, start_m3_worker, stop_m3_worker,
                sync_ticket_to_jira, process_outbox_once))
