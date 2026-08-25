const state = {
  apiKey: localStorage.getItem("aiCompanyApiKey") || "",
  tenantId: localStorage.getItem("aiCompanyTenantId") || "owner",
  tasks: [],
  approvals: [],
  memories: [],
  decisions: [],
  knowledge: [],
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

function headers() {
  return {
    "Content-Type": "application/json",
    "X-API-Key": state.apiKey,
    "X-Tenant-ID": state.tenantId,
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...options.headers } });
  if (response.status === 401) {
    $("#connection").classList.remove("online");
    $("#connection").lastChild.textContent = " 인증 필요";
    $("#settings-dialog").showModal();
    throw new Error("API 키를 확인해 주세요.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `요청 실패 (${response.status})`);
  }
  return response.json();
}

const statusLabels = {
  queued: "대기", dispatched: "전달됨", running: "진행 중", completed: "완료", failed: "실패",
};

function renderTasks() {
  if (!state.tasks.length) {
    $("#task-list").innerHTML = '<p class="empty">첫 업무를 지시해 보세요.</p>';
    return;
  }
  $("#task-list").innerHTML = state.tasks.map((task) => `
    <article class="task-item">
      <div class="task-meta">
        <span class="status-pill ${escapeHtml(task.status)}">${statusLabels[task.status] || task.status}</span>
        <span>우선순위 ${task.priority}</span><span>${new Date(task.created_at).toLocaleString("ko-KR")}</span>
      </div>
      <h3>${escapeHtml(task.title)}</h3>
      ${task.result ? `<div class="task-result">${escapeHtml(task.result)}</div>` : ""}
      ${task.error ? `<div class="task-result">${escapeHtml(task.error)}</div>` : ""}
    </article>`).join("");
}

function renderApprovals() {
  const pending = state.approvals.filter((item) => item.status === "pending");
  $("#metric-approvals").textContent = pending.length;
  if (!pending.length) {
    $("#approval-list").innerHTML = '<p class="empty">승인 요청이 없습니다.</p>';
    return;
  }
  $("#approval-list").innerHTML = pending.map((item) => `
    <article class="approval-card">
      <strong>${escapeHtml(item.action)}</strong>
      <span class="status-pill">위험도 ${escapeHtml(item.risk)}</span>
      <p>${escapeHtml(item.reason)}</p>
      <div class="approval-actions">
        <button data-id="${item.id}" data-approved="false">거절</button>
        <button class="approve" data-id="${item.id}" data-approved="true">승인</button>
      </div>
    </article>`).join("");
}

function renderMetrics() {
  $("#metric-active").textContent = state.tasks.filter((task) => ["queued", "dispatched", "running"].includes(task.status)).length;
  $("#metric-completed").textContent = state.tasks.filter((task) => task.status === "completed").length;
  const tokens = state.tasks.reduce((sum, task) => sum + (task.runs?.reduce((runSum, run) => runSum + run.total_tokens, 0) || 0), 0);
  $("#metric-tokens").textContent = new Intl.NumberFormat("ko-KR").format(tokens);
}

function renderCompanyContext() {
  $("#memory-count").textContent = state.memories.length;
  $("#decision-count").textContent = state.decisions.length;
  $("#knowledge-count").textContent = state.knowledge.length;

  $("#memory-list").innerHTML = state.memories.length ? state.memories.slice(0, 3).map((item) => `
    <div class="context-item"><strong>${escapeHtml(item.category)}</strong><p>${escapeHtml(item.content)}</p></div>
  `).join("") : '<p class="empty">저장된 기억이 없습니다.</p>';
  $("#decision-list").innerHTML = state.decisions.length ? state.decisions.slice(0, 3).map((item) => `
    <div class="context-item"><strong>${escapeHtml(item.subject)}</strong><p>${escapeHtml(item.choice)}</p></div>
  `).join("") : '<p class="empty">기록된 결정이 없습니다.</p>';
  $("#knowledge-list").innerHTML = state.knowledge.length ? state.knowledge.slice(0, 3).map((item) => `
    <div class="context-item"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.content)}</p></div>
  `).join("") : '<p class="empty">아직 축적된 지식이 없습니다.</p>';
}

async function loadDashboard() {
  try {
    const [tasks, approvals, events, memories, decisions, knowledge] = await Promise.all([
      api("/api/v1/tasks"), api("/api/v1/approvals"), api("/api/v1/audit-events?limit=9"),
      api("/api/v1/memories"), api("/api/v1/decisions"), api("/api/v1/knowledge"),
    ]);
    state.tasks = await Promise.all(tasks.map((task) => api(`/api/v1/tasks/${task.id}`)));
    state.approvals = approvals;
    state.memories = memories;
    state.decisions = decisions;
    state.knowledge = knowledge;
    renderTasks(); renderApprovals(); renderMetrics(); renderCompanyContext();
    $("#activity-list").innerHTML = events.length ? events.map((event) => `
      <div class="activity-item"><strong>${escapeHtml(event.action)}</strong>
      <span>${escapeHtml(event.resource_type)}</span><time>${new Date(event.created_at).toLocaleString("ko-KR")}</time></div>`).join("") : '<p class="empty">아직 활동이 없습니다.</p>';
    $("#connection").classList.add("online");
    $("#connection").lastChild.textContent = " 연결됨";
  } catch (error) {
    console.error(error);
  }
}

$("#task-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const request = $("#task-request").value.trim();
  if (!request) return;
  const button = $("#submit-task");
  button.disabled = true;
  $("#form-status").textContent = "비서실장에게 전달 중입니다…";
  try {
    const task = await api("/api/v1/tasks", { method: "POST", body: JSON.stringify({
      title: request.replace(/\s+/g, " ").slice(0, 80), request,
      priority: Number($("#task-priority").value), idempotency_key: crypto.randomUUID(),
    }) });
    await api(`/api/v1/tasks/${task.id}/run`, { method: "POST" });
    $("#task-request").value = "";
    $("#form-status").textContent = "업무를 접수했습니다.";
    await loadDashboard();
  } catch (error) {
    $("#form-status").textContent = error.message;
  } finally { button.disabled = false; }
});

$("#approval-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-id]");
  if (!button) return;
  await api(`/api/v1/approvals/${button.dataset.id}/decide`, { method: "POST", body: JSON.stringify({
    approved: button.dataset.approved === "true", decided_by: "CEO", note: "CEO Desk에서 결정",
  }) });
  await loadDashboard();
});

$("#refresh-button").addEventListener("click", loadDashboard);
$("#add-memory-button").addEventListener("click", () => $("#memory-dialog").showModal());
$("#add-decision-button").addEventListener("click", () => $("#decision-dialog").showModal());
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => $(`#${button.dataset.closeDialog}`).close());
});

$("#memory-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#memory-status").textContent = "저장 중입니다…";
  try {
    await api("/api/v1/memories", { method: "POST", body: JSON.stringify({
      category: $("#memory-category").value,
      content: $("#memory-content").value.trim(),
    }) });
    $("#memory-form").reset();
    $("#memory-status").textContent = "";
    $("#memory-dialog").close();
    await loadDashboard();
  } catch (error) { $("#memory-status").textContent = error.message; }
});

$("#decision-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#decision-status").textContent = "저장 중입니다…";
  try {
    await api("/api/v1/decisions", { method: "POST", body: JSON.stringify({
      subject: $("#decision-subject").value.trim(),
      choice: $("#decision-choice").value.trim(),
      rationale: $("#decision-rationale").value.trim(),
      decided_by: "CEO",
    }) });
    $("#decision-form").reset();
    $("#decision-status").textContent = "";
    $("#decision-dialog").close();
    await loadDashboard();
  } catch (error) { $("#decision-status").textContent = error.message; }
});

$("#settings-button").addEventListener("click", () => $("#settings-dialog").showModal());
$("#settings-form").addEventListener("submit", () => {
  state.apiKey = $("#api-key").value;
  state.tenantId = $("#tenant-id").value || "owner";
  localStorage.setItem("aiCompanyApiKey", state.apiKey);
  localStorage.setItem("aiCompanyTenantId", state.tenantId);
  setTimeout(loadDashboard, 0);
});

$("#api-key").value = state.apiKey;
$("#tenant-id").value = state.tenantId;
loadDashboard();
setInterval(loadDashboard, 8000);
