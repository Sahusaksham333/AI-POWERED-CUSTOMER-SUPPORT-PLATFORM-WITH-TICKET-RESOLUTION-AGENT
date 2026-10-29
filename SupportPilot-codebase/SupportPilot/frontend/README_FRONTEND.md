# SupportPilot Frontend Update

This folder is designed to replace the existing `SupportPilot/frontend/` directory. The backend, database, models, API endpoints, and other project files are not modified.

## Folder layout

- `index.html` — portal selector (User or Administrator)
- `portal.css` — styling for the portal selector
- `user/` — user sign-in/sign-up prototype and support ticket interface
- `admin/` — the existing admin ticket dashboard, moved into its own folder with a portal-switch link

## Install into the project

1. Extract this ZIP.
2. Open the extracted `frontend` folder.
3. Copy the contents of this `frontend` folder into:
   `SupportPilot-codebase/SupportPilot/frontend/`
4. Replace the old frontend files when prompted. Keep a backup of the old folder first if you want to restore it later.
5. Start the API from the `SupportPilot` project directory:

   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

6. Open `http://127.0.0.1:8000/`.

The FastAPI app already serves the `frontend` directory at `/`, so the new paths should be available at `/`, `/user/`, and `/admin/`. No backend route changes are required for this navigation structure.

## Important authentication note

The provided backend currently has no user registration, user login, or administrator authentication endpoints. To keep this task limited to the frontend, the user sign-up/sign-in experience is a **browser-only demonstration**; it does not provide real account security. The admin dashboard is also directly accessible at `/admin/`. Do not deploy this publicly or use real/reused passwords until server-side authentication, authorization, and user-specific ticket access are implemented.

The user ticket form calls the existing `/tickets/predict` and `/tickets/resolve` API endpoints. Ticket lookup uses the existing `/tickets/{ticket_id}` endpoint. Since the backend does not currently enforce ticket ownership, ticket IDs should be treated as references, not private access tokens.
