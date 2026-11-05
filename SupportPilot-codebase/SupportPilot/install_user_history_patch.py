"""Idempotently register the SupportPilot customer account/history API routes.

Run from the SupportPilot project root after extracting this overlay.
The script backs up app/main.py and leaves existing pipeline/model files untouched.
"""
from __future__ import annotations

from pathlib import Path
import shutil

main_path = Path("app/main.py")
if not main_path.is_file():
    raise SystemExit(
        "Run this script from the SupportPilot project root (the folder containing app/main.py)."
    )

source = main_path.read_text(encoding="utf-8")
original = source

import_line = "from .supportpilot.user_portal import create_user_portal_router, record_status_event"
if import_line not in source:
    anchor = "from .supportpilot.config import ARTIFACTS_DIR"
    if anchor not in source:
        raise SystemExit("Could not locate the expected config import in app/main.py; no changes made.")
    source = source.replace(anchor, anchor + "\n" + import_line, 1)

router_registration = "app.include_router(create_user_portal_router(pipeline))"
if router_registration not in source:
    anchor = "\ndef _new_ticket_id() -> str:"
    if anchor not in source:
        raise SystemExit("Could not locate _new_ticket_id() in app/main.py; no changes made.")
    source = source.replace(
        anchor,
        "\n\n# Authenticated customer portal routes: registration, login, ticket history and tracking.\n"
        + router_registration
        + anchor,
        1,
    )

old_status_handler = '''@app.patch("/tickets/{ticket_id}/status")
def set_ticket_status(ticket_id: str, request: TicketStatusRequest):
    if not update_workflow_status(ticket_id, request.status):
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"ticket_id": ticket_id, "workflow_status": request.status}
'''
new_status_handler = '''@app.patch("/tickets/{ticket_id}/status")
def set_ticket_status(ticket_id: str, request: TicketStatusRequest):
    previous = get_ticket(ticket_id)
    if not update_workflow_status(ticket_id, request.status):
        raise HTTPException(status_code=404, detail="Ticket not found")
    previous_status = str((previous or {}).get("workflow_status") or "Open")
    record_status_event(ticket_id, previous_status, request.status)
    return {"ticket_id": ticket_id, "workflow_status": request.status}
'''
if new_status_handler not in source:
    if old_status_handler not in source:
        raise SystemExit("Could not locate the expected ticket status handler; no changes made.")
    source = source.replace(old_status_handler, new_status_handler, 1)

if source == original:
    print("SupportPilot customer history routes are already registered; no changes needed.")
else:
    backup = main_path.with_name("main.py.pre_user_history.bak")
    if not backup.exists():
        shutil.copy2(main_path, backup)
    main_path.write_text(source, encoding="utf-8")
    print(f"Updated {main_path}. Backup: {backup}")
    print("No classifier artifacts, training scripts, or model files were modified.")
