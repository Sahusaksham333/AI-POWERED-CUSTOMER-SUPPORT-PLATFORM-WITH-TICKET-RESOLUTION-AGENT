# SupportPilot Frontend

This frontend contains the portal selector, administrator interface, and customer support workspace.

## Customer workspace additions

- Backend-backed email/password account creation and sign-in.
- Cross-device ticket history under **My tickets**.
- A status progress tracker and chronological ticket activity timeline.
- Owner-scoped ticket lookup and AI-assisted response generation.
- Same-origin API requests (`API = ""`) so the UI works through a public HTTPS reverse tunnel without pointing remote browsers at their own `localhost`.

## Installation

Copy this `frontend/` directory into the SupportPilot project root, replacing the old `frontend/` directory after making a backup. The FastAPI application must serve this directory at `/`.

The user interface requires the additive backend module `app/supportpilot/user_portal.py` and the small `app/main.py` registration patch supplied in `README_USER_HISTORY.md`. Copying only the frontend is insufficient for server-side registration, ticket history, and activity events.

## Security boundary

Customer accounts are stored server-side and user ticket routes require a signed bearer token. This prototype does not verify email ownership, implement Google OAuth, or authenticate administrators. The existing admin and legacy ticket API routes must be protected before the public tunnel is used with real customer data.
