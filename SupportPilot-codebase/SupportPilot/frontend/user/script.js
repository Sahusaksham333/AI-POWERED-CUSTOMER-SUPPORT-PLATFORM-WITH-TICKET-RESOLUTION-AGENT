const $ = id => document.getElementById(id);
const API = "http://127.0.0.1:8000";
const ACCOUNT = "supportpilot_demo_account_v1";
const SESSION = "supportpilot_demo_session_v1";

function safe(v = "") {
  return String(v).replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]
  );
}

function show(id, html) {
  const el = $(id);
  el.innerHTML = html;
  el.classList.remove("hidden");
}

function notice(message, type = "error") {
  const el = $("authNotice");
  el.textContent = message;
  el.className = `notice ${type}`;
}

function getSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION) || "null");
  } catch {
    return null;
  }
}

function getAccount() {
  try {
    return JSON.parse(localStorage.getItem(ACCOUNT) || "null");
  } catch {
    return null;
  }
}

async function hash(password) {
  if (crypto.subtle && isSecureContext) {
    const data = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(password)
    );
    return [...new Uint8Array(data)]
      .map(n => n.toString(16).padStart(2, "0")).join("");
  }
  return "demo:" + password;
}

function enter(user) {
  sessionStorage.setItem(SESSION, JSON.stringify({
    name: user.name,
    email: user.email
  }));

  $("authScreen").classList.add("hidden");
  $("workspace").classList.remove("hidden");
  $("welcomeName").textContent = user.name.split(/\s+/)[0];
  $("requesterName").value = user.name;
  $("requesterEmail").value = user.email;
}

async function api(path, options = {}) {
  const response = await fetch(API + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || data.message || `Request failed (${response.status})`
    );
  }

  return data;
}

function showError(id, err) {
  show(id, `<h3>Request failed</h3><p>${safe(err.message)}</p>`);
}

// Switch between sign-in and sign-up
document.querySelectorAll("[data-auth]").forEach(button => {
  button.addEventListener("click", () => {
    const signup = button.dataset.auth === "signup";
    $("signinForm").classList.toggle("hidden", signup);
    $("signupForm").classList.toggle("hidden", !signup);

    document.querySelectorAll(".auth-tab").forEach(b =>
      b.classList.toggle("active", b === button)
    );
  });
});

// Sign in
$("signinForm").addEventListener("submit", async e => {
  e.preventDefault();

  const user = getAccount();
  const email = $("signinEmail").value.trim().toLowerCase();
  const password = $("signinPassword").value;

  if (!user || user.email !== email ||
      user.passwordHash !== await hash(password)) {
    notice("Account not found. Please sign up first.");
    return;
  }

  enter(user);
});

// Sign up
$("signupForm").addEventListener("submit", async e => {
  e.preventDefault();

  const name = $("signupName").value.trim();
  const email = $("signupEmail").value.trim().toLowerCase();
  const password = $("signupPassword").value;

  if (password !== $("signupConfirm").value) {
    notice("Passwords do not match.");
    return;
  }

  if (password.length < 8) {
    notice("Password must contain at least 8 characters.");
    return;
  }

  const user = {
    name,
    email,
    passwordHash: await hash(password)
  };

  localStorage.setItem(ACCOUNT, JSON.stringify(user));
  enter(user);
});

// Sign out
$("signoutBtn").addEventListener("click", () => {
  sessionStorage.removeItem(SESSION);
  $("workspace").classList.add("hidden");
  $("authScreen").classList.remove("hidden");
});

// Workspace tabs
document.querySelectorAll(".workspace-tab").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".workspace-tab").forEach(b =>
      b.classList.toggle("active", b === button)
    );

    document.querySelectorAll(".workspace-panel").forEach(panel =>
      panel.classList.toggle("hidden", panel.id !== button.dataset.panel)
    );
  });
});

// Submit a ticket
$("ticketForm").addEventListener("submit", async e => {
  e.preventDefault();

  const button = $("submitTicketBtn");

  const payload = {
    requester_name: $("requesterName").value.trim(),
    requester_email: $("requesterEmail").value.trim(),
    subject: $("subject").value.trim(),
    body: $("body").value.trim(),
    business_impact: $("impact").value,
    language: $("language").value,
    contact_method: "Email"
  };

  button.disabled = true;
  button.textContent = "Submitting...";

  try {
    const result = await api("/tickets/predict", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    const id = result.ticket_id || "Not returned by server";
    const p = result.predictions || {};

    const stat = (label, value) =>
      `<div class="result-stat"><small>${label}</small><strong>${safe(value || "Not available")}</strong></div>`;

    show("ticketResult", `
      <h3>Your ticket has been submitted</h3>
      <p>Save this reference to track your ticket.</p>
      <div class="ticket-reference">${safe(id)}</div>
      <div class="result-grid">
        ${stat("Category", p.queue?.label)}
        ${stat("Ticket type", p.type?.label)}
        ${stat("Priority", p.priority?.label)}
      </div>
      <p>The support team can review your ticket.</p>
      <button type="button" class="btn outline" id="draftResponseBtn">
        Get AI-assisted next steps
      </button>
      <div id="draftResponseArea"></div>
    `);

    $("lookupId").value = result.ticket_id || "";

    // This popup stays until OK is clicked.
    alert(
      `Ticket created successfully!\n\nTicket ID: ${id}\n\nPlease save this ID to track your ticket.`
    );

    $("draftResponseBtn").addEventListener("click", async () => {
      const b = $("draftResponseBtn");
      b.disabled = true;
      b.textContent = "Preparing suggestions...";

      try {
        const data = await api("/tickets/resolve", {
          method: "POST",
          body: JSON.stringify({
            ...payload,
            ticket_id: result.ticket_id
          })
        });

        $("draftResponseArea").innerHTML =
          `<h3>Suggested next steps</h3>
           <div class="draft-box">${safe(data.response_draft || "The support team can review your ticket.")}</div>`;
      } catch (err) {
        $("draftResponseArea").innerHTML =
          `<p>${safe(err.message)}</p>`;
      } finally {
        b.disabled = false;
        b.textContent = "Get AI-assisted next steps";
      }
    });

    $("ticketForm").reset();

    const user = getSession();
    if (user) {
      $("requesterName").value = user.name;
      $("requesterEmail").value = user.email;
    }
  } catch (err) {
    showError("ticketResult", err);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Submit ticket <span>→</span>';
  }
});

// Track a ticket using its ID
$("lookupForm").addEventListener("submit", async e => {
  e.preventDefault();

  const id = $("lookupId").value.trim();
  if (!id) return;

  try {
    const t = await api(`/tickets/${encodeURIComponent(id)}`);

    show("lookupResult", `
      <h3>Ticket details</h3>
      <div class="ticket-reference">${safe(t.ticket_id || id)}</div>
      <p><strong>${safe(t.subject || "Support request")}</strong></p>
      <p>${safe(t.body || "")}</p>
      <p>Status: <span class="status-pill">${safe(t.workflow_status || "Open")}</span></p>
      <div class="result-grid">
        ${[
          ["Category", t.queue || "Not classified"],
          ["Priority", t.priority || "Not available"],
          ["Created", t.created_at ? new Date(t.created_at).toLocaleString() : "Not available"]
        ].map(([a, b]) =>
          `<div class="result-stat"><small>${a}</small><strong>${safe(b)}</strong></div>`
        ).join("")}
      </div>
    `);
  } catch (err) {
    showError("lookupResult", err);
  }
});

// Restore an existing demo session
const user = getSession();
if (user) enter(user);