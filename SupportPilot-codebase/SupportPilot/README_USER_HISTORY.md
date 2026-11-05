# SupportPilot — Cross-device Ticket History & Tracker

This overlay adds three customer-facing capabilities to the supplied frontend:

1. **Server-side customer accounts** — a user can create an account once and sign in from another device with the same email and password.
2. **My tickets** — the signed-in user sees only tickets linked to that account email.
3. **Per-ticket tracking** — each ticket shows its current workflow state and a chronological activity timeline, including ticket submission, AI classification, generated response drafts, and administrator status transitions.

It also fixes cross-device API addressing: the browser now calls relative URLs on the same host that served the page. This prevents `127.0.0.1` on a phone from pointing at the phone instead of the laptop hosting the Cloudflare Tunnel.

## What this is — and what it is not

- This is **email-and-password account sign-in**, not Google OAuth.
- Email ownership is **not verified**. A person can register an address they do not own. Add an email OTP or Google OAuth flow before treating the email as a verified identity.
- Passwords are stored server-side using PBKDF2-HMAC-SHA256 with a per-user random salt. API access tokens are HMAC-signed and expire after seven days.
- The first token-signing secret is generated and retained in the existing SupportPilot SQLite database. Keep that database private and backed up.
- Existing administrator endpoints have not been given administrator authentication by this overlay. Do not expose the public admin dashboard or legacy unprotected `/tickets` endpoints to untrusted users. Add admin authorization before production deployment.

## Installation into an existing SupportPilot project

1. Stop Uvicorn.
2. Back up your existing `frontend` directory and `app/main.py`.
3. Extract this overlay into the **SupportPilot project root**, the folder containing `app/`, `training/`, `artifacts/`, and `requirements.txt`. Allow the included `frontend/` folder and `app/supportpilot/user_portal.py` to be added/replaced.
4. From that same project root, run:

   ```powershell
   python install_user_history_patch.py
   ```

   The installer makes `app/main.py.pre_user_history.bak` and adds the customer router plus status-event hook. It is idempotent and does not replace your existing `main.py` wholesale.
5. Restart the backend:

   ```powershell
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

6. In another terminal, start the Quick Tunnel:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8000
   ```

7. Open the new HTTPS URL on the second device. Create one account, then sign in with the same email and password on the other device. Submit a test ticket and confirm it appears under **My tickets**.

## New API routes

| Method | Route | Purpose |
|---|---|---|
| POST | `/auth/register` | Create a server-side user account |
| POST | `/auth/login` | Sign in and issue a bearer token |
| GET | `/auth/me` | Return the current account |
| POST | `/user/tickets/predict` | Create a ticket owned by the signed-in account |
| GET | `/user/tickets` | Return the signed-in user's ticket history |
| GET | `/user/tickets/{ticket_id}` | Return one owned ticket plus its activity events |
| POST | `/user/tickets/{ticket_id}/resolve` | Generate an AI response for an owned ticket |

The authenticated user routes filter by the account identity in the signed bearer token; they do not accept an arbitrary email query parameter from the browser. Ticket records remain in the existing SQLite database. Activity events are stored in an additional table in that same database, so no model retraining or artifact changes are required.

## Verification checklist

- `GET /health` returns `200` on the same public HTTPS origin.
- Create an account from Device A; sign in from Device B with the same credentials.
- Submit a ticket on Device B; confirm it appears on Device A after refreshing **My tickets**.
- Open **View activity & tracker** and confirm the ticket ID, status, model labels, and activity timeline are displayed.
- Change the ticket status from the administrator workflow; confirm a status-transition event appears after refreshing the user tracker.
- Confirm an account cannot retrieve another account's ticket using `/user/tickets/{ticket_id}`.

## Important public-tunnel warning

A Cloudflare Quick Tunnel makes the application reachable from the public internet while it is running. The new customer routes enforce bearer-token account ownership, but the existing administrator and legacy ticket routes in your current backend may remain unauthenticated. Use synthetic test data until administrator authorization, email verification, rate limiting, and deployment hardening are in place.
