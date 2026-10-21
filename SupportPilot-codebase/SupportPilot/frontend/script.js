/* SupportPilot production-style frontend integration.
 * This UI uses the FastAPI + SQLite backend; it does not store tickets in localStorage
 * and does not substitute keyword rules when a trained model is missing.
 */
const API_BASE = "";
const $ = (id) => document.getElementById(id);
let tickets = [];
let activeTicketId = null;
let toastTimer = null;
let lastHealth = null;
let performanceReport = null;

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || payload.message || response.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function escapeHTML(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[char]);
}

function titleCase(value) {
  if (!value || value === "—") return value || "—";
  return String(value).replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function normalizeStatus(raw) {
  const value = raw?.workflow_status || raw?.workflowStatus;
  if (["Open", "In Progress", "Resolved"].includes(value)) return value;
  return "Open";
}

function normalizeTicket(raw) {
  const predictions = raw.predictions || {};
  const queuePrediction = predictions.queue || {};
  const typePrediction = predictions.type || {};
  const priorityPrediction = predictions.priority || {};
  const rawTags = raw.tags || [];
  const tags = rawTags.map((item) => typeof item === "string" ? { tag: item, confidence: null } : item);
  const priority = raw.priority || priorityPrediction.label || "Unavailable";
  return {
    id: raw.ticket_id || raw.id,
    requesterName: raw.requester_name || raw.requesterName || "Requester not provided",
    requesterEmail: raw.requester_email || raw.requesterEmail || "—",
    subject: raw.subject || "Untitled ticket",
    description: raw.body || raw.description || "",
    category: raw.queue || queuePrediction.label || "Unclassified",
    type: raw.ticket_type || raw.type || typePrediction.label || "Unclassified",
    priority: titleCase(priority),
    priorityConfidence: priorityPrediction.confidence ?? raw.priority_confidence ?? null,
    queueConfidence: queuePrediction.confidence ?? null,
    typeConfidence: typePrediction.confidence ?? null,
    severity: titleCase(raw.business_impact || raw.impact || "Medium"),
    impact: raw.business_impact || raw.impact || "medium",
    status: normalizeStatus(raw),
    processingStatus: raw.status || "unknown",
    contact: raw.contact_method || raw.contact || "Email",
    language: raw.language || "auto",
    createdAt: raw.created_at || raw.createdAt || new Date().toISOString(),
    reasoning: buildReasoning(predictions, raw),
    tags,
    predictions,
    escalated: Boolean(raw.escalated),
    escalationReasons: raw.escalation_reasons || [],
    responseDraft: raw.response_draft || raw.responseDraft || "",
    sources: raw.sources || [],
    modelHealth: raw.model_health || {},
  };
}

function buildReasoning(predictions, raw) {
  const available = Object.entries(predictions)
    .filter(([, result]) => result && result.available && result.label)
    .map(([key, result]) => `${titleCase(key)}: ${result.label} (${Math.round((result.confidence || 0) * 100)}% confidence)`);
  const unavailable = Object.entries(predictions)
    .filter(([, result]) => result && result.available === false)
    .map(([key]) => titleCase(key));
  const reasons = raw.escalation_reasons || [];
  let text = available.length ? available.join(" · ") : "No trained classifier prediction was available for this ticket.";
  if (unavailable.length) text += ` Models unavailable: ${unavailable.join(", ")}.`;
  if (reasons.length) text += ` Escalation flags: ${reasons.join(", ")}.`;
  return text;
}

function formatDate(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
function formatDateTime(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
function statusClass(status) { return String(status || "open").toLowerCase().replace(/\s+/g, "-"); }
function priorityClass(priority) { return String(priority || "unknown").toLowerCase().replace(/\s+/g, "-"); }
function categoryIcon(category) {
  const text = String(category || "").toLowerCase();
  if (/network|outage|maintenance|connect/.test(text)) return "⌁";
  if (/software|product|bug|application/.test(text)) return "▣";
  if (/access|account|identity|security/.test(text)) return "♙";
  if (/hardware|device/.test(text)) return "▰";
  if (/billing|payment|finance/.test(text)) return "$";
  return "✧";
}

function ticketRow(ticket) {
  return `<tr>
    <td><span class="ticket-id">${escapeHTML(String(ticket.id).slice(0, 20))}</span></td>
    <td><div class="subject-cell"><span class="subject-icon">${categoryIcon(ticket.category)}</span><div><div class="subject-text" title="${escapeHTML(ticket.subject)}">${escapeHTML(ticket.subject)}</div><span class="requester-line">${escapeHTML(ticket.requesterName)}</span></div></div></td>
    <td><span class="category-label"><span class="category-dot"></span>${escapeHTML(ticket.category)}</span></td>
    <td><span class="priority-badge ${priorityClass(ticket.priority)}">${escapeHTML(ticket.priority)}</span></td>
    <td><span class="status-badge ${statusClass(ticket.status)}">${escapeHTML(ticket.status)}</span></td>
    <td>${formatDate(ticket.createdAt)}</td>
    <td><button class="row-menu" data-open-ticket="${escapeHTML(ticket.id)}" aria-label="View ${escapeHTML(ticket.id)}">⋯</button></td>
  </tr>`;
}

function renderTable(tbodyId, emptyId, summaryId, list) {
  const tbody = $(tbodyId);
  if (!tbody) return;
  tbody.innerHTML = list.map(ticketRow).join("");
  const empty = $(emptyId);
  if (empty) empty.classList.toggle("hidden", list.length > 0);
  if (summaryId && $(summaryId)) $(summaryId).textContent = `Showing ${list.length} ticket${list.length === 1 ? "" : "s"}`;
}

function filteredTickets(search, status) {
  const q = (search || "").trim().toLowerCase();
  return [...tickets]
    .filter((ticket) => status === "all" || ticket.status === status)
    .filter((ticket) => !q || [ticket.id, ticket.subject, ticket.requesterName, ticket.requesterEmail, ticket.category, ticket.type]
      .some((value) => String(value || "").toLowerCase().includes(q)))
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

function renderCategoryBars() {
  if (!$('categoryBars')) return;
  const counts = new Map();
  tickets.forEach((ticket) => counts.set(ticket.category || "Unclassified", (counts.get(ticket.category || "Unclassified") || 0) + 1));
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (!top.length) top.push(["No categories yet", 0]);
  const max = Math.max(1, ...top.map((item) => item[1]));
  $("categoryBars").innerHTML = top.map(([category, count]) => `
    <div><div class="bar-label"><span>${escapeHTML(category)}</span><strong>${count}</strong></div>
    <div class="bar-track"><div class="bar-fill" style="width:${(count / max) * 100}%"></div></div></div>`).join("");
}

function renderDashboard() {
  const openCount = tickets.filter((ticket) => ticket.status !== "Resolved").length;
  $("totalMetric").textContent = tickets.length;
  $("openMetric").textContent = openCount;
  $("highMetric").textContent = tickets.filter((ticket) => ["High", "Critical"].includes(ticket.priority) && ticket.status !== "Resolved").length;
  $("resolvedMetric").textContent = tickets.filter((ticket) => ticket.status === "Resolved").length;
  $("navTicketCount").textContent = tickets.length;
  const homeSearch = $("ticketSearch")?.value || "";
  const homeStatus = $("statusFilter")?.value || "all";
  renderTable("ticketTableBody", "emptyState", "tableSummary", filteredTickets(homeSearch, homeStatus).slice(0, 6));
  renderTable("allTicketTableBody", "allEmptyState", "allTableSummary", filteredTickets($("allTicketSearch")?.value, $("allStatusFilter")?.value || "all"));
  const priorityList = [...tickets].filter((ticket) => ["High", "Critical", "Urgent"].includes(ticket.priority) && ticket.status !== "Resolved");
  renderTable("priorityTableBody", "priorityEmptyState", null, priorityList);
  renderCategoryBars();
}

function showToast(message, isError = false) {
  const toast = $("toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.toggle("error-toast", isError);
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show", "error-toast"), 3800);
}

function setApiStatus(ok, label) {
  const pill = $("apiStatusPill");
  if (!pill) return;
  pill.innerHTML = `<span></span>${escapeHTML(label)}`;
  pill.classList.toggle("connection-error", !ok);
  pill.title = ok ? "FastAPI backend is responding" : "The API connection failed. Start the FastAPI server.";
}

async function refreshTickets() {
  const payload = await api("/tickets?limit=500");
  tickets = (Array.isArray(payload) ? payload : payload.tickets || []).map(normalizeTicket);
  renderDashboard();
}

async function refreshHealth() {
  try {
    lastHealth = await api("/health");
    setApiStatus(true, "API connected");
  } catch (error) {
    lastHealth = null;
    setApiStatus(false, "API unavailable");
    throw error;
  }
}

function confidenceText(value) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
}

function openTicket(id) {
  const ticket = tickets.find((item) => String(item.id) === String(id));
  if (!ticket) return;
  activeTicketId = ticket.id;
  $("modalTitle").textContent = ticket.subject;
  $("modalId").textContent = `${ticket.id} · Created ${formatDateTime(ticket.createdAt)}`;
  const p = ticket.predictions || {};
  const queue = p.queue || {};
  const type = p.type || {};
  const priority = p.priority || {};
  const availability = [queue, type, priority, p.textcnn_queue || {}].some((x) => x.available);
  $("modalResults").innerHTML = `
    <div class="result-box"><span>Predicted queue</span><strong>${escapeHTML(queue.label || ticket.category || "Unavailable")}</strong><div class="confidence-line">Confidence: ${confidenceText(queue.confidence)}</div></div>
    <div class="result-box"><span>Ticket type</span><strong>${escapeHTML(type.label || ticket.type || "Unavailable")}</strong><div class="confidence-line">Confidence: ${confidenceText(type.confidence)}</div></div>
    <div class="result-box"><span>Predicted priority</span><strong><span class="priority-badge ${priorityClass(priority.label || ticket.priority)}">${escapeHTML(titleCase(priority.label || ticket.priority))}</span></strong><div class="confidence-line">Confidence: ${confidenceText(priority.confidence)}</div></div>
    <div class="result-box"><span>TextCNN queue benchmark</span><strong>${escapeHTML((p.textcnn_queue || {}).label || "Unavailable")}</strong><div class="confidence-line">Confidence: ${confidenceText((p.textcnn_queue || {}).confidence)} · comparison only</div></div>
    <div class="result-box"><span>Workflow status</span><strong>${escapeHTML(ticket.status)}</strong></div>
    <div class="result-box"><span>Business impact</span><strong>${escapeHTML(titleCase(ticket.impact))}</strong><div class="confidence-line">User-provided input, not a trained severity label</div></div>
    <div class="result-box"><span>Escalation review</span><strong>${ticket.escalated ? "Review recommended" : "No automatic flag"}</strong></div>`;
  const tagContainer = $("modalTags");
  if (tagContainer) tagContainer.innerHTML = ticket.tags.length ? ticket.tags.map((tag) => `<span class="tag-pill">${escapeHTML(tag.tag)}${typeof tag.confidence === "number" ? ` · ${(tag.confidence * 100).toFixed(1)}%` : ""}</span>`).join("") : '<span class="model-source-note">No tag predictions available. Check that artifacts/tags is configured.</span>';
  $("modalDescription").textContent = ticket.description;
  $("modalReasoning").textContent = availability ? ticket.reasoning : "No trained prediction was available. Check Model performance for artifact status and configure SUPPORTPILOT_ARTIFACTS_DIR to the directory containing your trained checkpoints.";
  $("modalRequester").textContent = `${ticket.requesterName} · ${ticket.requesterEmail} · Preferred contact: ${ticket.contact || "Email"} · Language: ${ticket.language || "auto"}`;
  $("modalStatus").value = ticket.status;
  renderResolution(ticket);
  const resolutionButton = $("generateResolution");
  resolutionButton.disabled = false;
  resolutionButton.textContent = ticket.responseDraft ? "↻ Regenerate AI response" : "✧ Draft AI response";
  $("resolutionStatus").textContent = ticket.responseDraft ? "Saved draft available" : "Retrieval and Ollama must be configured";
  $("ticketModal").classList.remove("hidden");
}

function renderResolution(ticket) {
  const section = $("resolutionSection");
  if (!section) return;
  const hasDraft = Boolean(ticket.responseDraft);
  section.classList.toggle("hidden", !hasDraft);
  $("modalResponse").textContent = ticket.responseDraft || "";
  const sources = ticket.sources || [];
  $("modalSources").innerHTML = sources.length ? sources.map((source) => `
    <div class="source-item"><strong>${escapeHTML(source.source || source.title || "Knowledge source")}</strong>
    ${escapeHTML((source.text || "").slice(0, 900))}</div>`).join("") : (hasDraft ? '<p class="model-source-note">No retrieved source was attached. Review the draft carefully before sending.</p>' : "");
}

function closeModal() {
  $("ticketModal").classList.add("hidden");
  activeTicketId = null;
}
function resetTicketForm() {
  $("ticketForm").reset();
  $("requesterName").focus();
}

async function handleTicketSubmit(event) {
  event.preventDefault();
  const submit = $("ticketForm").querySelector('button[type="submit"]');
  const requesterName = $("requesterName").value.trim();
  const requesterEmail = $("requesterEmail").value.trim();
  const subject = $("ticketSubject").value.trim();
  const body = $("ticketDescription").value.trim();
  if (!requesterName || !requesterEmail || subject.length < 3 || body.length < 5) {
    showToast("Please complete all required fields.", true);
    return;
  }
  const payload = {
    requester_name: requesterName,
    requester_email: requesterEmail,
    subject,
    body,
    language: $("ticketLanguage")?.value || "auto",
    business_impact: $("businessImpact").value,
    contact_method: $("contactMethod").value,
  };
  submit.disabled = true;
  submit.dataset.originalText = submit.innerHTML;
  submit.textContent = "Analyzing with trained models…";
  try {
    const result = await api("/tickets/predict", { method: "POST", body: JSON.stringify(payload) });
    await refreshTickets();
    resetTicketForm();
    showView("dashboard");
    openTicket(result.ticket_id);
    const preds = result.predictions || {};
    const available = Object.values(preds).some((item) => item && item.available);
    showToast(available ? "Ticket saved and analyzed by available model artifacts." : "Ticket saved; trained artifacts were not found, so predictions are unavailable.", !available);
  } catch (error) {
    showToast(`Ticket submission failed: ${error.message}`, true);
  } finally {
    submit.disabled = false;
    submit.innerHTML = submit.dataset.originalText || "＋ Submit & classify ticket";
  }
}

async function saveStatus() {
  if (!activeTicketId) return;
  const status = $("modalStatus").value;
  $("saveStatus").disabled = true;
  try {
    await api(`/tickets/${encodeURIComponent(activeTicketId)}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
    await refreshTickets();
    closeModal();
    showToast(`Ticket status updated to ${status}.`);
  } catch (error) {
    showToast(`Status update failed: ${error.message}`, true);
  } finally {
    $("saveStatus").disabled = false;
  }
}

async function generateResolution() {
  if (!activeTicketId) return;
  const ticket = tickets.find((item) => String(item.id) === String(activeTicketId));
  if (!ticket) return;
  const button = $("generateResolution");
  button.disabled = true;
  button.textContent = "Drafting response…";
  $("resolutionStatus").textContent = "Querying knowledge sources and local LLM";
  try {
    const result = await api("/tickets/resolve", {
      method: "POST",
      body: JSON.stringify({
        ticket_id: ticket.id,
        requester_name: ticket.requesterName,
        requester_email: ticket.requesterEmail === "—" ? null : ticket.requesterEmail,
        subject: ticket.subject,
        body: ticket.description,
        language: ticket.language || "auto",
        business_impact: ticket.impact,
        contact_method: ticket.contact,
      }),
    });
    await refreshTickets();
    const updated = tickets.find((item) => String(item.id) === String(activeTicketId));
    if (updated) {
      // Return payload may contain a just-created draft before the following GET finishes.
      updated.responseDraft = result.response_draft || updated.responseDraft;
      updated.sources = result.sources || updated.sources;
      updated.escalated = Boolean(result.escalated);
    }
    if (updated) {
      renderResolution(updated);
      $("modalReasoning").textContent = updated.reasoning;
      $("resolutionStatus").textContent = result.generation_error ? `Fallback used: ${result.generation_error}` : (result.sources?.length ? `${result.sources.length} source(s) retrieved · review before sending` : "No knowledge sources retrieved · human review required");
    }
    showToast(result.generation_error ? "Fallback response returned. Review carefully." : "AI response draft created; human review is required.", Boolean(result.generation_error));
  } catch (error) {
    $("resolutionStatus").textContent = error.message;
    showToast(`Could not draft resolution: ${error.message}`, true);
  } finally {
    button.disabled = false;
    const current = tickets.find((item) => String(item.id) === String(activeTicketId));
    button.textContent = current?.responseDraft ? "↻ Regenerate AI response" : "✧ Draft AI response";
  }
}

function renderModelPerformance(report) {
  performanceReport = report;
  const models = report.models || [];
  const primaryCards = ["queue", "priority", "type", "tags"].map((key) => models.find((model) => model.key === key)).filter(Boolean);
  $("modelMetricCards").innerHTML = primaryCards.map((model) => {
    const isTags = model.key === "tags";
    const score = isTags ? model.top3_hit_rate : model.accuracy;
    const scoreLabel = isTags ? "Top-3 hit rate" : "Held-out accuracy";
    const f1 = typeof model.macro_f1 === "number" ? `Macro-F1 ${(model.macro_f1 * 100).toFixed(1)}%` : `Overlap ${(model.top3_overlap_ratio * 100).toFixed(1)}%`;
    const iconClass = score >= 0.8 ? "green" : score >= 0.5 ? "orange" : "purple";
    return `<article class="metric-card">
      <div class="metric-top"><span>${escapeHTML(model.name)}</span><span class="metric-icon ${iconClass}">◈</span></div>
      <div class="metric-value">${(score * 100).toFixed(1)}%</div>
      <div class="metric-foot"><span class="metric-neutral">${scoreLabel} · ${f1}</span></div>
    </article>`;
  }).join("");
  $("testSetSize").textContent = `Test set: ${(report.test_samples || 0).toLocaleString()} rows`;
  $("modelMetricsSource").textContent = report.source || "Source: uploaded training logs";
  $("modelMetricsBody").innerHTML = models.map((model) => {
    const isTags = model.key === "tags";
    const primary = isTags ? `${(model.top3_hit_rate * 100).toFixed(2)}% top-3 hit` : `${(model.accuracy * 100).toFixed(1)}% accuracy`;
    const f1 = typeof model.macro_f1 === "number" ? `${(model.macro_f1 * 100).toFixed(1)}%` : "Not applicable";
    const rightMetric = typeof model.weighted_f1 === "number" ? `${(model.weighted_f1 * 100).toFixed(1)}% weighted F1` : `${(model.top3_overlap_ratio * 100).toFixed(2)}% overlap`;
    const available = Boolean(model.artifact_available);
    const artifact = `<span class="model-status-chip ${available ? "available" : "missing"}">${available ? "Found" : "Not found"}</span><div class="confidence-line">${escapeHTML(model.artifact_path || "")}</div>`;
    const scorePct = isTags ? model.top3_hit_rate : model.accuracy;
    return `<tr>
      <td><strong>${escapeHTML(model.name)}</strong><div class="confidence-line">${escapeHTML(model.source_log || "Recorded report")}</div></td>
      <td>${escapeHTML(model.architecture)}</td>
      <td><span class="model-primary-score">${primary}</span><div class="model-mini-meter"><span style="width:${Math.max(0, Math.min(100, scorePct * 100))}%"></span></div></td>
      <td>${f1}</td><td>${rightMetric}</td><td>${artifact}</td>
    </tr>`;
  }).join("");
  $("modelInsights").innerHTML = models.map((model) => `<div class="model-insight"><strong>${escapeHTML(model.name)} · ${escapeHTML(model.architecture)}</strong>${escapeHTML(model.assessment || "No interpretation supplied.")}</div>`).join("");
}

async function refreshModels() {
  const button = $("refreshModels");
  if (button) { button.disabled = true; button.textContent = "Checking artifacts…"; }
  try {
    const report = await api("/models/performance");
    renderModelPerformance(report);
  } catch (error) {
    $("modelMetricsBody").innerHTML = `<tr><td colspan="6">Could not load metrics: ${escapeHTML(error.message)}</td></tr>`;
    showToast(`Could not refresh models: ${error.message}`, true);
  } finally {
    if (button) { button.disabled = false; button.textContent = "↻ Refresh model status"; }
  }
}

function showView(view) {
  const views = { dashboard: "dashboardView", create: "createView", tickets: "ticketsView", priority: "priorityView", models: "modelsView" };
  Object.entries(views).forEach(([key, id]) => $(id)?.classList.toggle("hidden", key !== view));
  document.querySelectorAll(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  const names = { dashboard: "Overview", create: "Create ticket", tickets: "All tickets", priority: "Priority queue", models: "Model performance" };
  $("breadcrumbCurrent").textContent = names[view] || "Overview";
  $("sidebar").classList.remove("open");
  if (view !== "create") renderDashboard();
  if (view === "models") refreshModels();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function bindEvents() {
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  ["createTicketTop", "emptyCreateButton", "createFromTickets", "createFromPriority"].forEach((id) => $(id)?.addEventListener("click", () => showView("create")));
  $("viewAllTickets").addEventListener("click", () => showView("tickets"));
  $("cancelCreate").addEventListener("click", () => showView("dashboard"));
  $("resetForm").addEventListener("click", resetTicketForm);
  $("ticketForm").addEventListener("submit", handleTicketSubmit);
  $("ticketSearch").addEventListener("input", renderDashboard);
  $("statusFilter").addEventListener("change", renderDashboard);
  $("allTicketSearch").addEventListener("input", renderDashboard);
  $("allStatusFilter").addEventListener("change", renderDashboard);
  $("modalClose").addEventListener("click", closeModal);
  $("ticketModal").addEventListener("click", (event) => { if (event.target === $("ticketModal")) closeModal(); });
  $("saveStatus").addEventListener("click", saveStatus);
  $("generateResolution")?.addEventListener("click", generateResolution);
  $("refreshModels")?.addEventListener("click", refreshModels);
  $("clearSearch").addEventListener("click", () => {
    $("ticketSearch").value = "";
    $("allTicketSearch").value = "";
    $("statusFilter").value = "all";
    $("allStatusFilter").value = "all";
    renderDashboard();
    showToast("Search filters cleared.");
  });
  $("mobileMenu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-ticket]");
    if (button) openTicket(button.dataset.openTicket);
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
}

async function init() {
  bindEvents();
  renderDashboard();
  try {
    await refreshHealth();
    await refreshTickets();
    await refreshModels();
  } catch (error) {
    setApiStatus(false, "API unavailable");
    showToast(`SupportPilot API is unavailable: ${error.message}. Start uvicorn and open this app through http://127.0.0.1:8000/`, true);
  }
}

init();
