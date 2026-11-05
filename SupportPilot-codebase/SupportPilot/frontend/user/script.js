"use strict";

const $ = (id) => document.getElementById(id);

// Same-origin requests work on localhost and through a Cloudflare Tunnel.
// Never hard-code 127.0.0.1 here: on a remote device it points to that device.
const API_BASE = window.location.origin;
const SESSION_KEY = "supportpilot_server_session_v2";

function escapeHTML(value = "") {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[character]);
}

function getSession() {
  try {
    const value = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
    if (!value || typeof value.accessToken !== "string" || !value.accessToken || !value.email) {
      return null;
    }
    return value;
  } catch {
    return null;
  }
}

function saveSession(user, accessToken) {
  const session = {
    name: String(user.name || "Support user"),
    email: String(user.email || "").trim().toLowerCase(),
    accessToken: String(accessToken || "")
  };
  if (!session.email || !session.accessToken) {
    throw new Error("The server did not return a valid account session.");
  }
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}

function showNotice(message, type = "error") {
  const element = $("authNotice");
  element.textContent = message;
  element.className = `notice ${type}`;
}

function showPanel(elementId, html) {
  const element = $(elementId);
  if (!element) return;
  element.innerHTML = html;
  element.classList.remove("hidden");
}

function showWorkspace() {
  $("authScreen").classList.add("hidden");
  $("workspace").classList.remove("hidden");
}

function showAuthentication() {
  $("workspace").classList.add("hidden");
  $("authScreen").classList.remove("hidden");
}

function setWorkspacePanel(panelId) {
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.panel === panelId);
  });
  document.querySelectorAll(".workspace-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== panelId);
  });
  if (panelId === "historyPanel") loadMyTickets();
  if (panelId === "knowledgePanel") refreshKnowledgeStatus();
}

async function api(path, options = {}) {
  const session = getSession();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");

  if (options.body !== undefined && options.body !== null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.accessToken && !["/auth/login", "/auth/register"].includes(path)) {
    headers.set("Authorization", `Bearer ${session.accessToken}`);
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      cache: "no-store"
    });
  } catch {
    throw new Error("Cannot reach SupportPilot. Check that FastAPI and the Cloudflare Tunnel are running.");
  }

  const responseText = await response.text();
  let data = {};
  if (responseText) {
    try {
      data = JSON.parse(responseText);
    } catch {
      data = { detail: responseText };
    }
  }

  if (!response.ok) {
    if (response.status === 401 && getSession()) {
      clearSession();
      showAuthentication();
      showNotice("Your session has expired. Sign in again.");
    }
    const detail = data.detail || data.message || `Request failed with HTTP ${response.status}.`;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || JSON.stringify(item)).join("; ")
      : typeof detail === "object" ? JSON.stringify(detail) : String(detail);
    throw new Error(message);
  }
  return data;
}

function formatDate(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
}

function statusSlug(status) {
  return String(status || "open").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "open";
}

function statusStage(status) {
  const value = String(status || "Open").toLowerCase().replace(/[_-]+/g, " ").trim();
  if (["resolved", "closed", "completed"].includes(value)) return 2;
  if (["in progress", "in review", "assigned", "working"].includes(value)) return 1;
  return 0;
}

function progressMarkup(status) {
  const labels = ["Submitted", "In progress", "Resolved"];
  const activeStage = statusStage(status);
  return `
    <div class="ticket-progress" role="img" aria-label="Ticket progress: ${escapeHTML(status || "Open")}">
      ${labels.map((label, index) => `
        <div class="progress-step ${index <= activeStage ? "complete" : ""} ${index === activeStage ? "current" : ""}">
          <span class="progress-dot">${index < activeStage ? "✓" : index + 1}</span>
          <small>${label}</small>
        </div>`).join("")}
    </div>`;
}

function statusPill(status) {
  const value = status || "Open";
  return `<span class="status-pill status-${statusSlug(value)}">${escapeHTML(value)}</span>`;
}

function renderTicketCard(ticket) {
  const status = ticket.workflow_status || "Open";
  const category = ticket.queue || ticket.category || ticket.type || "Pending classification";
  return `
    <article class="ticket-history-card">
      <div class="ticket-card-top">
        <div class="ticket-card-title">
          <span class="ticket-id-label">${escapeHTML(ticket.ticket_id || "Ticket reference unavailable")}</span>
          <h3>${escapeHTML(ticket.subject || "Support request")}</h3>
        </div>
        ${statusPill(status)}
      </div>
      <p class="ticket-card-description">${escapeHTML(ticket.body || "No description supplied.")}</p>
      <div class="ticket-card-meta">
        <span><small>Created</small><strong>${escapeHTML(formatDate(ticket.created_at))}</strong></span>
        <span><small>Category</small><strong>${escapeHTML(category)}</strong></span>
        <span><small>Priority</small><strong>${escapeHTML(ticket.priority || "Not available")}</strong></span>
      </div>
      ${progressMarkup(status)}
      <div class="ticket-card-actions">
        <button class="btn outline" type="button" data-view-ticket="${escapeHTML(ticket.ticket_id || "")}">View activity &amp; tracker →</button>
      </div>
    </article>`;
}

function renderSummary(tickets) {
  const resolved = tickets.filter((ticket) => statusStage(ticket.workflow_status) === 2).length;
  const active = tickets.length - resolved;
  $("historySummary").innerHTML = `
    <div class="history-metric"><small>Total tickets</small><strong>${tickets.length}</strong></div>
    <div class="history-metric"><small>Active</small><strong>${active}</strong></div>
    <div class="history-metric"><small>Resolved</small><strong>${resolved}</strong></div>`;
  $("historyCount").textContent = String(tickets.length);
}

async function loadMyTickets() {
  const list = $("ticketHistoryList");
  if (!list) return;
  list.innerHTML = `<div class="empty-state">Loading your tickets…</div>`;
  $("historyTracker").classList.add("hidden");

  try {
    const data = await api("/user/tickets?limit=100");
    const tickets = Array.isArray(data.tickets) ? data.tickets : [];
    renderSummary(tickets);

    if (tickets.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <strong>No tickets found for this account</strong>
          <p>Submit a support request while signed in with this email address. New tickets will appear here.</p>
          <button class="btn primary" type="button" id="createFirstTicketBtn">Create your first ticket</button>
        </div>`;
      $("createFirstTicketBtn").addEventListener("click", () => setWorkspacePanel("newTicketPanel"));
      return;
    }

    list.innerHTML = tickets.map(renderTicketCard).join("");
  } catch (error) {
    $("historyCount").textContent = "!";
    $("historySummary").innerHTML = "";
    showPanel("ticketHistoryList", `
      <div class="empty-state error-state">
        <strong>Ticket history could not be loaded</strong>
        <p>${escapeHTML(error.message)}</p>
        <button class="btn outline" type="button" id="retryHistoryBtn">Try again</button>
      </div>`);
    $("retryHistoryBtn")?.addEventListener("click", loadMyTickets);
  }
}

function renderTicketTracker(ticket) {
  const events = Array.isArray(ticket.events) ? ticket.events : [];
  const status = ticket.workflow_status || "Open";
  const metadata = [
    ["Ticket type", ticket.type || "Not classified"],
    ["Category", ticket.queue || ticket.category || "Not classified"],
    ["Priority", ticket.priority || "Not available"],
    ["Created", formatDate(ticket.created_at)]
  ];

  const timeline = events.length
    ? `<ol class="activity-timeline">${events.map((event) => `
        <li class="timeline-event">
          <span class="timeline-marker" aria-hidden="true"></span>
          <div class="timeline-content">
            <div class="timeline-heading">
              <strong>${escapeHTML(event.title || event.event_type || "Ticket update")}</strong>
              <time>${escapeHTML(formatDate(event.created_at))}</time>
            </div>
            <p>${escapeHTML(event.description || "")}</p>
          </div>
        </li>`).join("")}</ol>`
    : `<div class="empty-state compact">No activity events have been recorded for this ticket yet.</div>`;

  return `
    <div class="tracker-header">
      <div><span class="ticket-id-label">${escapeHTML(ticket.ticket_id || "")}</span><h3>${escapeHTML(ticket.subject || "Support request")}</h3></div>
      ${statusPill(status)}
    </div>
    <p class="tracker-body">${escapeHTML(ticket.body || "No description supplied.")}</p>
    ${progressMarkup(status)}
    <div class="result-grid tracker-metadata">
      ${metadata.map(([label, value]) => `<div class="result-stat"><small>${escapeHTML(label)}</small><strong>${escapeHTML(value)}</strong></div>`).join("")}
    </div>
    <h4 class="timeline-title">Ticket activity</h4>
    ${timeline}`;
}

async function openTicketTracker(ticketId, targetId = "historyTracker") {
  const target = $(targetId);
  if (!target || !ticketId) return;
  target.innerHTML = `<div class="empty-state">Loading ticket activity…</div>`;
  target.classList.remove("hidden");

  try {
    const ticket = await api(`/user/tickets/${encodeURIComponent(ticketId)}`);
    target.innerHTML = renderTicketTracker(ticket);
    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    target.innerHTML = `
      <div class="empty-state error-state">
        <strong>Ticket details could not be loaded</strong>
        <p>${escapeHTML(error.message)}</p>
      </div>`;
  }
}

function enterWorkspace(user, accessToken) {
  const session = saveSession(user, accessToken);
  showWorkspace();
  $("welcomeName").textContent = session.name.split(/\s+/)[0] || "there";
  $("requesterName").value = session.name;
  $("requesterEmail").value = session.email;
  $("historyEmail").textContent = session.email;
  $("historyCount").textContent = "…";
  loadMyTickets();
}

// Sign-in / sign-up tab controls.
document.querySelectorAll("[data-auth]").forEach((button) => {
  button.addEventListener("click", () => {
    const selected = button.dataset.auth;
    const signup = selected === "signup";
    $("signinForm").classList.toggle("hidden", signup);
    $("signupForm").classList.toggle("hidden", !signup);
    document.querySelectorAll(".auth-tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.auth === selected);
    });
    $("authNotice").classList.add("hidden");
  });
});

// Sign in with the server-side account store.
$("signinForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter || $("signinForm").querySelector('[type="submit"]');
  button.disabled = true;
  button.textContent = "Signing in…";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: $("signinEmail").value.trim().toLowerCase(),
        password: $("signinPassword").value
      })
    });
    enterWorkspace(data.user, data.access_token);
    $("signinPassword").value = "";
    $("authNotice").classList.add("hidden");
  } catch (error) {
    showNotice(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Sign in <span aria-hidden="true">→</span>';
  }
});

// Create a server-side account. The same credentials can be used on another device.
$("signupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter || $("signupForm").querySelector('[type="submit"]');
  const password = $("signupPassword").value;
  if (password !== $("signupConfirm").value) {
    showNotice("The passwords do not match.");
    return;
  }
  if (password.length < 8) {
    showNotice("Use a password containing at least 8 characters.");
    return;
  }

  button.disabled = true;
  button.textContent = "Creating account…";
  try {
    const data = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        name: $("signupName").value.trim(),
        email: $("signupEmail").value.trim().toLowerCase(),
        password
      })
    });
    enterWorkspace(data.user, data.access_token);
    $("signupPassword").value = "";
    $("signupConfirm").value = "";
    $("authNotice").classList.add("hidden");
  } catch (error) {
    showNotice(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Create account <span aria-hidden="true">→</span>';
  }
});

// Sign out only clears this browser session; the server-side account and tickets remain.
$("signoutBtn").addEventListener("click", () => {
  clearSession();
  showAuthentication();
  $("signinPassword").value = "";
  showNotice("You have signed out.", "success");
});

// Workspace navigation.
document.querySelectorAll(".workspace-tab").forEach((button) => {
  button.addEventListener("click", () => setWorkspacePanel(button.dataset.panel));
});
$("refreshHistoryBtn").addEventListener("click", loadMyTickets);

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-view-ticket]");
  if (button) openTicketTracker(button.dataset.viewTicket);
});

// Create a ticket under the identity contained in the signed server token.
$("ticketForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("submitTicketBtn");
  const session = getSession();
  if (!session) {
    showAuthentication();
    showNotice("Sign in before submitting a ticket.");
    return;
  }

  const payload = {
    requester_name: session.name,
    requester_email: session.email,
    subject: $("subject").value.trim(),
    body: $("body").value.trim(),
    business_impact: $("impact").value,
    language: $("language").value,
    contact_method: "Email"
  };

  button.disabled = true;
  button.textContent = "Submitting…";
  $("ticketResult").classList.add("hidden");

  try {
    const result = await api("/user/tickets/predict", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    const ticketId = result.ticket_id;
    if (!ticketId) throw new Error("The server created a response but did not return a ticket ID.");

    const predictions = result.predictions || {};
    const metric = (label, value) => `
      <div class="result-stat"><small>${escapeHTML(label)}</small><strong>${escapeHTML(value || "Not available")}</strong></div>`;

    showPanel("ticketResult", `
      <h3>Your ticket has been submitted</h3>
      <p>Your request is linked to <strong>${escapeHTML(session.email)}</strong>.</p>
      <div class="ticket-reference">${escapeHTML(ticketId)}</div>
      <div class="result-grid">
        ${metric("Category", predictions.queue?.label)}
        ${metric("Ticket type", predictions.type?.label)}
        ${metric("Priority", predictions.priority?.label)}
      </div>
      <p>Save the ticket reference. You can also find it later under <strong>My tickets</strong>.</p>
      <div class="result-actions">
        <button class="btn outline" type="button" id="openNewTicketTrackerBtn">View ticket tracker</button>
        <button class="btn primary" type="button" id="draftResponseBtn">Get AI-assisted next steps</button>
      </div>
      <div id="draftResponseArea"></div>`);

    $("lookupId").value = ticketId;
    $("openNewTicketTrackerBtn").addEventListener("click", async () => {
      setWorkspacePanel("historyPanel");
      await openTicketTracker(ticketId);
    });

    $("draftResponseBtn").addEventListener("click", async () => {
      const responseButton = $("draftResponseBtn");
      responseButton.disabled = true;
      responseButton.textContent = "Preparing suggestions…";
      try {
        const response = await api(`/user/tickets/${encodeURIComponent(ticketId)}/resolve`, {
          method: "POST",
          body: JSON.stringify({ ...payload, ticket_id: ticketId })
        });
        $("draftResponseArea").innerHTML = `
          <h4>Suggested next steps</h4>
          <div class="draft-box">${escapeHTML(response.response_draft || "The support team can review your ticket.")}</div>`;
        setWorkspacePanel("historyPanel");
        await loadMyTickets();
        await openTicketTracker(ticketId);
      } catch (error) {
        $("draftResponseArea").innerHTML = `<p class="inline-error">${escapeHTML(error.message)}</p>`;
      } finally {
        responseButton.disabled = false;
        responseButton.textContent = "Get AI-assisted next steps";
      }
    });

    $("ticketForm").reset();
    $("requesterName").value = session.name;
    $("requesterEmail").value = session.email;
    await loadMyTickets();
  } catch (error) {
    showPanel("ticketResult", `
      <div class="empty-state error-state"><strong>Ticket submission failed</strong><p>${escapeHTML(error.message)}</p></div>`);
  } finally {
    button.disabled = false;
    button.innerHTML = 'Submit ticket <span aria-hidden="true">→</span>';
  }
});

// Lookup is owner-scoped: the API returns only tickets belonging to this account.
$("lookupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("lookupButton");
  const ticketId = $("lookupId").value.trim();
  if (!ticketId) return;

  button.disabled = true;
  button.textContent = "Searching…";
  showPanel("lookupResult", `<div class="empty-state">Looking up your ticket…</div>`);
  try {
    const ticket = await api(`/user/tickets/${encodeURIComponent(ticketId)}`);
    $("lookupResult").innerHTML = renderTicketTracker(ticket);
  } catch (error) {
    $("lookupResult").innerHTML = `
      <div class="empty-state error-state"><strong>Ticket not found</strong><p>${escapeHTML(error.message)}</p></div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Find ticket";
  }
});

// Knowledge retrieval and standalone AI assistance share the authenticated user portal.
function renderKnowledgeSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) {
    return `<div class="empty-state compact">No matching knowledge passages were retrieved. Try different wording or contact the support team.</div>`;
  }
  return `<div class="source-list">${sources.map((source, index) => `
    <article class="source-card">
      <div class="source-card-heading">
        <strong>Source ${index + 1}: ${escapeHTML(source.source || "Knowledge base")}</strong>
        <span>Chunk ${escapeHTML(source.chunk ?? index)}</span>
      </div>
      <p>${escapeHTML(source.text || "No source excerpt was returned.")}</p>
    </article>`).join("")}</div>`;
}

async function refreshKnowledgeStatus() {
  const badge = $("knowledgeStatus");
  if (!badge) return;
  badge.textContent = "CHECKING KNOWLEDGE BASE";
  badge.className = "step-chip status-checking";
  try {
    const status = await api("/user/knowledge/status");
    if (status.ready) {
      const count = Number(status.document_chunks || 0);
      badge.textContent = `READY · ${count} INDEXED CHUNKS`;
      badge.className = "step-chip status-ready";
    } else {
      badge.textContent = "KNOWLEDGE BASE NOT READY";
      badge.className = "step-chip status-unavailable";
      $("knowledgeResults").innerHTML = `<div class="empty-state error-state"><strong>Knowledge retrieval is unavailable</strong><p>${escapeHTML(status.error || "The knowledge index has not been configured.")}</p></div>`;
      $("assistanceResults").innerHTML = `<div class="empty-state error-state"><strong>AI assistance is unavailable</strong><p>Index the approved knowledge base and verify the RAG service before requesting grounded guidance.</p></div>`;
    }
  } catch (error) {
    badge.textContent = "STATUS UNAVAILABLE";
    badge.className = "step-chip status-unavailable";
    if (error.message) {
      $("knowledgeResults").innerHTML = `<div class="empty-state error-state"><strong>Could not check knowledge service</strong><p>${escapeHTML(error.message)}</p></div>`;
    }
  }
}

$("knowledgeSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("knowledgeSearchBtn");
  const query = $("knowledgeQuery").value.trim();
  if (query.length < 3) return;
  button.disabled = true;
  button.textContent = "Searching…";
  $("knowledgeResults").innerHTML = `<div class="empty-state">Searching approved knowledge sources…</div>`;
  try {
    const data = await api("/user/knowledge/search", {
      method: "POST",
      body: JSON.stringify({ query, top_k: Number($("knowledgeTopK").value) })
    });
    $("knowledgeResults").innerHTML = `
      <div class="retrieval-summary"><strong>${Number(data.count || 0)} relevant source(s) found</strong><span>Knowledge retrieval only · No AI answer generated</span></div>
      ${renderKnowledgeSources(data.sources)}`;
  } catch (error) {
    $("knowledgeResults").innerHTML = `<div class="empty-state error-state"><strong>Knowledge search failed</strong><p>${escapeHTML(error.message)}</p></div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Search knowledge";
  }
});

$("assistanceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("assistanceBtn");
  const query = $("assistanceQuery").value.trim();
  if (query.length < 5) return;
  button.disabled = true;
  button.textContent = "Preparing guidance…";
  $("assistanceResults").innerHTML = `<div class="empty-state">Retrieving knowledge and preparing an AI-assisted response. This may take a little longer.</div>`;
  try {
    const data = await api("/user/knowledge/assist", {
      method: "POST",
      body: JSON.stringify({ query, language: $("assistanceLanguage").value })
    });
    const warning = data.generation_error
      ? `<p class="inline-error">The response generator reported an issue: ${escapeHTML(data.generation_error)}</p>`
      : "";
    $("assistanceResults").innerHTML = `
      <div class="assistance-answer">
        <div class="answer-heading"><h4>AI-assisted guidance</h4><span>${data.escalated ? "Human review recommended" : "Source-grounded draft"}</span></div>
        <div class="draft-box">${escapeHTML(data.response_draft || "No response was generated.")}</div>
        ${warning}
      </div>
      <h4 class="sources-title">Knowledge sources used</h4>
      ${renderKnowledgeSources(data.sources)}`;
  } catch (error) {
    $("assistanceResults").innerHTML = `<div class="empty-state error-state"><strong>AI assistance failed</strong><p>${escapeHTML(error.message)}</p><p>Check the knowledge index and local Ollama service, then retry.</p></div>`;
  } finally {
    button.disabled = false;
    button.textContent = "Generate assistance";
  }
});

// Restore and validate the server-issued session after a page reload.
(async function restoreSession() {
  const session = getSession();
  if (!session) return;

  try {
    const data = await api("/auth/me");
    enterWorkspace(data.user, session.accessToken);
  } catch {
    clearSession();
    showAuthentication();
  }
})();
