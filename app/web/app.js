const state = {
  apiKey: localStorage.getItem("aiCompanyApiKey") || "",
  tenantId: localStorage.getItem("aiCompanyTenantId") || "owner",
  tasks: [],
  approvals: [],
  memories: [],
  decisions: [],
  commitments: [],
  attention: { total: 0, counts: {}, items: [] },
  briefingSchedule: { enabled: false, last_delivery: null },
  knowledge: [],
  provenance: [],
  goals: [],
  projects: [],
  portfolioHealth: { summary: { health_counts: {} }, goals: [], projects: [] },
  agents: [],
  contextSearch: { query: "", total: 0, items: [] },
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
    const detail = body.detail;
    const message = typeof detail === "string" ? detail : detail?.message;
    throw new Error(message || `요청 실패 (${response.status})`);
  }
  return response.json();
}

const statusLabels = {
  queued: "대기", dispatched: "전달됨", running: "진행 중", completed: "완료", failed: "실패",
};

const decisionStatusLabels = {
  proposed: "검토 중", active: "활성", superseded: "대체됨", expired: "만료", revoked: "철회",
};

const commitmentStatusLabels = {
  open: "대기", in_progress: "진행 중", completed: "완료", cancelled: "취소",
};

const attentionLevelLabels = {
  info: "정보", watch: "관찰", action: "행동", decision: "결정", critical: "긴급",
};

const attentionKindLabels = {
  overdue_commitment: "지연 약속",
  long_running_task: "장기 실행",
  task_failure: "업무 실패",
  pending_approval: "승인 대기",
};

const projectStatusLabels = {
  planned: "계획", active: "진행 중", on_hold: "보류", completed: "완료", archived: "보관",
};

const goalStatusLabels = {
  planned: "계획", active: "진행 중", on_hold: "보류", achieved: "달성",
  cancelled: "취소", archived: "보관",
};

const portfolioHealthLabels = {
  healthy: "정상", watch: "관찰", action: "조치 필요", critical: "긴급", closed: "종료",
};

const portfolioHealthReasonLabels = {
  on_track: "계획대로 진행 중",
  target_date_overdue: "목표일 초과",
  target_date_due_soon: "14일 이내 목표일",
  goal_on_hold: "목표 보류 중",
  project_on_hold: "프로젝트 보류 중",
  failed_tasks: "실패 업무 확인 필요",
  goal_not_started: "목표 시작 전",
  project_not_started: "프로젝트 시작 전",
  active_without_projects: "연결 프로젝트 없음",
  active_without_tasks: "등록 업무 없음",
  goal_closed: "종료된 목표",
  project_closed: "종료된 프로젝트",
};

const goalTransitionOptions = {
  planned: [["active", "시작"], ["cancelled", "취소"]],
  active: [["on_hold", "보류"], ["achieved", "달성"], ["cancelled", "취소"]],
  on_hold: [["active", "재개"], ["cancelled", "취소"]],
  achieved: [["archived", "보관"]],
  cancelled: [["archived", "보관"]],
  archived: [],
};

const projectTransitionOptions = {
  planned: [["active", "시작"], ["archived", "보관"]],
  active: [["on_hold", "보류"], ["completed", "완료"]],
  on_hold: [["active", "재개"], ["archived", "보관"]],
  completed: [["archived", "보관"]],
  archived: [],
};

function portfolioActions(kind, id, currentStatus) {
  const options = kind === "goal"
    ? goalTransitionOptions[currentStatus] || []
    : projectTransitionOptions[currentStatus] || [];
  if (!options.length) return "";
  return `<div class="portfolio-actions">${options.map(([status, label]) => (
    `<button type="button" data-${kind}-id="${escapeHtml(id)}" data-status="${escapeHtml(status)}">${escapeHtml(label)}</button>`
  )).join("")}</div>`;
}

const evaluationStatusLabels = {
  untested: "미평가", baseline: "기준 검증", pilot: "파일럿", approved: "운영 승인",
};

const contextResourceLabels = {
  memory: "기억", decision: "대표 결정", knowledge: "지식",
};

const provenanceSubjectLabels = { knowledge: "연구 지식", decision: "대표 결정" };
const provenanceStatusLabels = {
  unverified: "미검증", observed: "출처 관찰", verified: "검증 완료", rejected: "근거 제외",
};

function projectTitle(projectId) {
  return state.projects.find((project) => project.id === projectId)?.title || "";
}

function goalTitle(goalId) {
  return state.goals.find((goal) => goal.id === goalId)?.title || "";
}

function portfolioHealthItem(kind, id) {
  return (state.portfolioHealth[kind] || []).find((item) => item.id === id);
}

function portfolioProgress(item) {
  if (!item) return "";
  const percent = Number(item.completion_percent || 0);
  return `
    <div class="portfolio-progress" aria-label="업무 완료율 ${percent}%">
      <span style="width: ${Math.min(100, Math.max(0, percent))}%"></span>
    </div>`;
}

function portfolioHealthChip(item) {
  if (!item) return "";
  const label = portfolioHealthLabels[item.health_level] || item.health_level;
  const reason = portfolioHealthReasonLabels[item.health_reason] || item.health_reason;
  return `<span class="portfolio-health-chip health-${escapeHtml(item.health_level)}" title="${escapeHtml(reason)}">${escapeHtml(label)}</span>`;
}

function renderPortfolioHealth() {
  const summary = state.portfolioHealth.summary || {};
  const counts = summary.health_counts || {};
  $("#portfolio-health").innerHTML = `
    <div class="portfolio-health-stat"><span>전체 완료율</span><strong>${Number(summary.completion_percent || 0)}%</strong></div>
    <div class="portfolio-health-stat"><span>열린 목표</span><strong>${Number(summary.open_goals || 0)}</strong></div>
    <div class="portfolio-health-stat health-critical"><span>기한 초과</span><strong>${Number(summary.overdue_goals || 0)}</strong></div>
    <div class="portfolio-health-stat health-watch"><span>마감 임박</span><strong>${Number(summary.due_soon_goals || 0)}</strong></div>
    <div class="portfolio-health-stat health-action"><span>조치 필요</span><strong>${Number(counts.action || 0) + Number(counts.critical || 0)}</strong></div>
  `;
}

function renderTasks() {
  if (!state.tasks.length) {
    $("#task-list").innerHTML = '<p class="empty">첫 업무를 지시해 보세요.</p>';
    return;
  }
  $("#task-list").innerHTML = state.tasks.map((task) => `
    <article class="task-item">
      <div class="task-meta">
        <span class="status-pill ${escapeHtml(task.status)}">${statusLabels[task.status] || task.status}</span>
        ${task.project_id ? `<span class="task-project">${escapeHtml(projectTitle(task.project_id) || "프로젝트")}</span>` : ""}
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
  $("#metric-overdue").textContent = state.commitments.filter((item) => item.is_overdue).length;
  $("#metric-attention").textContent = (state.attention.counts.decision || 0) + (state.attention.counts.critical || 0);
  const tokens = state.tasks.reduce((sum, task) => sum + (task.runs?.reduce((runSum, run) => runSum + run.total_tokens, 0) || 0), 0);
  $("#metric-tokens").textContent = new Intl.NumberFormat("ko-KR").format(tokens);
}

function renderProjects() {
  const select = $("#task-project");
  const selectedProject = select.value;
  const selectableProjects = state.projects.filter((project) => !["completed", "archived"].includes(project.status));
  select.innerHTML = '<option value="">프로젝트 미지정</option>' + selectableProjects.map((project) => (
    `<option value="${project.id}">${escapeHtml(project.title)}</option>`
  )).join("");
  if (selectableProjects.some((project) => project.id === selectedProject)) select.value = selectedProject;

  if (!state.projects.length) {
    $("#project-list").innerHTML = '<p class="empty">첫 프로젝트를 만들어 업무를 목표별로 묶어보세요.</p>';
    return;
  }
  $("#project-list").innerHTML = state.projects.slice(0, 8).map((project) => {
    const health = portfolioHealthItem("projects", project.id);
    const tasks = state.tasks.filter((task) => task.project_id === project.id);
    const active = tasks.filter((task) => ["queued", "dispatched", "running"].includes(task.status)).length;
    const completed = tasks.filter((task) => task.status === "completed").length;
    return `
      <article class="project-card">
        <div class="project-heading">
          <strong>${escapeHtml(project.title)}</strong>
          <div class="portfolio-badges">
            ${portfolioHealthChip(health)}
            <span class="project-status ${escapeHtml(project.status)}">${escapeHtml(projectStatusLabels[project.status] || project.status)}</span>
          </div>
        </div>
        ${project.goal_id ? `<span class="project-goal">목표 · ${escapeHtml(goalTitle(project.goal_id) || "연결됨")}</span>` : ""}
        ${project.description ? `<p>${escapeHtml(project.description)}</p>` : ""}
        <div class="project-stats">
          <span class="project-stat">전체 업무 ${tasks.length}</span>
          <span class="project-stat">진행 ${active}</span>
          <span class="project-stat">완료 ${completed}</span>
        </div>
        ${portfolioProgress(health)}
        ${portfolioActions("project", project.id, project.status)}
      </article>`;
  }).join("");
}

function renderGoals() {
  const select = $("#project-goal-id");
  const selectedGoal = select.value;
  const selectableGoals = state.goals.filter(
    (goal) => !["achieved", "cancelled", "archived"].includes(goal.status),
  );
  select.innerHTML = '<option value="">목표 미지정</option>' + selectableGoals.map((goal) => (
    `<option value="${goal.id}">${escapeHtml(goal.title)}</option>`
  )).join("");
  if (selectableGoals.some((goal) => goal.id === selectedGoal)) select.value = selectedGoal;

  if (!state.goals.length) {
    $("#goal-list").innerHTML = '<p class="empty">첫 회사 목표를 등록해 프로젝트의 방향을 정해보세요.</p>';
    return;
  }
  $("#goal-list").innerHTML = state.goals.slice(0, 6).map((goal) => {
    const health = portfolioHealthItem("goals", goal.id);
    const projects = state.projects.filter((project) => project.goal_id === goal.id);
    const projectIds = new Set(projects.map((project) => project.id));
    const tasks = state.tasks.filter((task) => projectIds.has(task.project_id));
    const completed = tasks.filter((task) => task.status === "completed").length;
    const target = goal.target_date
      ? new Date(`${goal.target_date}T00:00:00`).toLocaleDateString("ko-KR")
      : "목표일 미정";
    return `
      <article class="goal-card">
        <div class="project-heading">
          <strong>${escapeHtml(goal.title)}</strong>
          <div class="portfolio-badges">
            ${portfolioHealthChip(health)}
            <span class="goal-status ${escapeHtml(goal.status)}">${escapeHtml(goalStatusLabels[goal.status] || goal.status)}</span>
          </div>
        </div>
        ${goal.description ? `<p>${escapeHtml(goal.description)}</p>` : ""}
        ${goal.success_metric ? `<div class="goal-metric">성공 기준 · ${escapeHtml(goal.success_metric)}</div>` : ""}
        <div class="project-stats">
          <span class="project-stat">${escapeHtml(goal.owner || "책임자 미정")}</span>
          <span class="project-stat">${escapeHtml(target)}</span>
          <span class="project-stat">프로젝트 ${projects.length}</span>
          <span class="project-stat">완료 업무 ${completed}/${tasks.length}</span>
        </div>
        ${portfolioProgress(health)}
        ${portfolioActions("goal", goal.id, goal.status)}
      </article>`;
  }).join("");
}

function renderAgents() {
  if (!state.agents.length) {
    $("#agent-list").innerHTML = '<p class="empty">등록된 AI 직원이 없습니다.</p>';
    return;
  }
  $("#agent-list").innerHTML = state.agents.map((agent) => `
    <article class="agent-card">
      <div class="agent-heading">
        <div><span class="agent-role">${escapeHtml(agent.role)}</span><strong>${escapeHtml(agent.key)}</strong></div>
        <span class="agent-chip ${escapeHtml(agent.evaluation_status)}">${escapeHtml(evaluationStatusLabels[agent.evaluation_status] || agent.evaluation_status)}</span>
      </div>
      <p>${escapeHtml(agent.purpose)}</p>
      <div class="agent-boundaries">
        <span class="agent-chip">${escapeHtml(agent.provider)} · ${escapeHtml(agent.model)}</span>
        ${(agent.allowed_tools || []).map((tool) => `<span class="agent-chip">도구 ${escapeHtml(tool)}</span>`).join("")}
        <span class="agent-chip approval">${escapeHtml(agent.approval_policy)}</span>
      </div>
    </article>
  `).join("");
}

function renderAttention() {
  const items = state.attention.items || [];
  if (!items.length) {
    $("#attention-list").innerHTML = '<p class="empty">현재 대표가 확인할 주의 항목이 없습니다.</p>';
    return;
  }
  $("#attention-list").innerHTML = items.slice(0, 8).map((item) => `
    <article class="attention-item level-${escapeHtml(item.level)}">
      <div class="attention-heading">
        <span class="attention-level">${escapeHtml(attentionLevelLabels[item.level] || item.level)}</span>
        <span class="attention-kind">${escapeHtml(attentionKindLabels[item.kind] || item.kind)}</span>
      </div>
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.summary)}</p>
      <small>${escapeHtml(item.recommendation)}</small>
    </article>
  `).join("");
}

function renderBriefingSchedule() {
  const schedule = state.briefingSchedule;
  const badge = $("#briefing-schedule-badge");
  badge.classList.remove("is-off", "is-failed");
  if (!schedule.enabled) {
    badge.textContent = "자동 브리핑 꺼짐";
    badge.classList.add("is-off");
    return;
  }
  const last = schedule.last_delivery;
  if (["failed", "uncertain"].includes(last?.status)) {
    badge.textContent = `자동 브리핑 재시도 대기 · ${schedule.daily_time}`;
    badge.classList.add("is-failed");
    return;
  }
  badge.textContent = `자동 브리핑 매일 ${schedule.daily_time} KST`;
  badge.title = `조용한 시간 ${schedule.quiet_hours} · 최대 ${schedule.max_attempts}회 시도`;
}

function renderCommitments() {
  const items = state.commitments.filter((item) => !["completed", "cancelled"].includes(item.status));
  if (!items.length) {
    $("#commitment-list").innerHTML = '<p class="empty">진행 중인 약속이 없습니다.</p>';
    return;
  }
  $("#commitment-list").innerHTML = items.slice(0, 8).map((item) => `
    <article class="commitment-item ${item.is_overdue ? "overdue" : ""}">
      <div>
        <div class="task-meta">
          <span class="status-pill ${escapeHtml(item.status)}">${escapeHtml(commitmentStatusLabels[item.status] || item.status)}</span>
          ${item.is_overdue ? '<span class="overdue-label">기한 초과</span>' : ""}
          <span>${new Date(item.due_at).toLocaleString("ko-KR")}까지</span>
        </div>
        <strong>${escapeHtml(item.statement)}</strong>
        <p>${escapeHtml(item.owner_id)} · ${escapeHtml(item.owner_type)}</p>
      </div>
      <div class="commitment-actions">
        ${item.status === "open" ? `<button data-commitment-id="${item.id}" data-commitment-status="in_progress">시작</button>` : ""}
        <button class="approve" data-commitment-id="${item.id}" data-commitment-status="completed">완료</button>
        <button class="danger" data-commitment-id="${item.id}" data-commitment-status="cancelled">취소</button>
      </div>
    </article>
  `).join("");
}

function renderCompanyContext() {
  $("#memory-count").textContent = state.memories.length;
  $("#decision-count").textContent = state.decisions.length;
  $("#knowledge-count").textContent = state.knowledge.length;

  $("#memory-list").innerHTML = state.memories.length ? state.memories.slice(0, 3).map((item) => `
    <div class="context-item"><strong>${escapeHtml(item.category)}</strong><p>${escapeHtml(item.content)}</p></div>
  `).join("") : '<p class="empty">저장된 기억이 없습니다.</p>';
  $("#decision-list").innerHTML = state.decisions.length ? state.decisions.slice(0, 3).map((item) => `
    <div class="context-item">
      <strong>${escapeHtml(item.subject)} <span class="decision-state ${escapeHtml(item.status)}">${escapeHtml(decisionStatusLabels[item.status] || item.status)}</span></strong>
      <p>${escapeHtml(item.choice)}</p>
      ${item.status === "proposed" ? `<button class="context-action" data-decision-id="${item.id}" data-decision-status="active">확정</button>` : ""}
      ${item.status === "active" ? `<button class="context-action danger" data-decision-id="${item.id}" data-decision-status="revoked">철회</button>` : ""}
    </div>
  `).join("") : '<p class="empty">기록된 결정이 없습니다.</p>';
  $("#knowledge-list").innerHTML = state.knowledge.length ? state.knowledge.slice(0, 3).map((item) => `
    <div class="context-item"><strong>${escapeHtml(item.title)}</strong><p>${escapeHtml(item.content)}</p></div>
  `).join("") : '<p class="empty">아직 축적된 지식이 없습니다.</p>';
}

function renderProvenance() {
  $("#provenance-count").textContent = state.provenance.length;
  if (!state.provenance.length) {
    $("#provenance-list").innerHTML = '<p class="empty">기록된 근거가 없습니다.</p>';
    return;
  }
  $("#provenance-list").innerHTML = state.provenance.slice(0, 8).map((item) => {
    const source = item.source_uri
      ? `<a href="${escapeHtml(item.source_uri)}" target="_blank" rel="noopener noreferrer">원문 열기</a>`
      : '<span class="provenance-no-link">외부 URL 없음</span>';
    return `
      <article class="provenance-item">
        <div class="provenance-meta">
          <span>${escapeHtml(provenanceSubjectLabels[item.subject_type] || item.subject_type)}</span>
          <span class="provenance-status ${escapeHtml(item.verification_status)}">${escapeHtml(provenanceStatusLabels[item.verification_status] || item.verification_status)}</span>
        </div>
        <strong>${escapeHtml(item.source_label)}</strong>
        <div class="provenance-detail">
          ${source}
          <code title="SHA-256 ${escapeHtml(item.content_hash)}">SHA-256 ${escapeHtml(item.content_hash.slice(0, 12))}…</code>
          ${item.produced_by_agent ? `<span>${escapeHtml(item.produced_by_agent)}</span>` : ""}
        </div>
      </article>`;
  }).join("");
}

function renderContextSearch() {
  const results = $("#context-search-results");
  if (!state.contextSearch.query) {
    results.innerHTML = "";
    return;
  }
  if (!state.contextSearch.items.length) {
    results.innerHTML = '<p class="empty">일치하는 회사 맥락이 없습니다.</p>';
    return;
  }
  results.innerHTML = state.contextSearch.items.map((item) => `
    <article class="search-result">
      <div class="search-result-heading">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="search-result-type">${escapeHtml(contextResourceLabels[item.resource_type] || item.resource_type)}</span>
      </div>
      <p>${escapeHtml(item.excerpt)}</p>
    </article>
  `).join("");
}

async function loadDashboard() {
  try {
    const [tasks, approvals, events, memories, decisions, commitments, attention, briefingSchedule, knowledge, provenance, goals, projects, portfolioHealth, agents] = await Promise.all([
      api("/api/v1/tasks"), api("/api/v1/approvals"), api("/api/v1/audit-events?limit=9"),
      api("/api/v1/memories"), api("/api/v1/decisions"), api("/api/v1/commitments"),
      api("/api/v1/attention?limit=8"),
      api("/api/v1/briefing-schedule"),
      api("/api/v1/knowledge"),
      api("/api/v1/provenance?limit=20"),
      api("/api/v1/goals"),
      api("/api/v1/projects"),
      api("/api/v1/portfolio/health"),
      api("/api/v1/agents"),
    ]);
    state.tasks = await Promise.all(tasks.map((task) => api(`/api/v1/tasks/${task.id}`)));
    state.approvals = approvals;
    state.memories = memories;
    state.decisions = decisions;
    state.commitments = commitments;
    state.attention = attention;
    state.briefingSchedule = briefingSchedule;
    state.knowledge = knowledge;
    state.provenance = provenance;
    state.goals = goals;
    state.projects = projects;
    state.portfolioHealth = portfolioHealth;
    state.agents = agents;
    renderPortfolioHealth(); renderGoals(); renderProjects(); renderTasks(); renderApprovals(); renderMetrics(); renderAttention(); renderBriefingSchedule(); renderCommitments(); renderCompanyContext(); renderProvenance(); renderAgents();
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
      project_id: $("#task-project").value || null,
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
$("#add-goal-button").addEventListener("click", () => $("#goal-dialog").showModal());
$("#add-project-button").addEventListener("click", () => $("#project-dialog").showModal());
async function handlePortfolioTransition(button, kind) {
  const id = button.dataset[`${kind}Id`];
  const target = button.dataset.status;
  const terminal = ["achieved", "cancelled", "completed", "archived"].includes(target);
  if (terminal && !window.confirm(`상태를 '${kind === "goal" ? goalStatusLabels[target] : projectStatusLabels[target]}'(으)로 변경할까요?`)) return;
  button.disabled = true;
  try {
    await api(`/api/v1/${kind}s/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ status: target, note: "CEO Desk 상태 변경" }),
    });
    await loadDashboard();
  } catch (error) {
    window.alert(error.message);
  } finally {
    button.disabled = false;
  }
}
$("#goal-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-goal-id]");
  if (button) await handlePortfolioTransition(button, "goal");
});
$("#project-list").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-project-id]");
  if (button) await handlePortfolioTransition(button, "project");
});
$("#add-commitment-button").addEventListener("click", () => {
  const availableDecisions = state.decisions.filter((item) => ["proposed", "active"].includes(item.status));
  $("#commitment-decision-id").innerHTML = '<option value="">연결하지 않음</option>'
    + availableDecisions.map((item) => `<option value="${item.id}">${escapeHtml(item.subject)}</option>`).join("");
  const due = new Date(Date.now() + 24 * 60 * 60 * 1000);
  due.setMinutes(due.getMinutes() - due.getTimezoneOffset());
  $("#commitment-due-at").value = due.toISOString().slice(0, 16);
  $("#commitment-dialog").showModal();
});
$("#add-memory-button").addEventListener("click", () => $("#memory-dialog").showModal());
$("#add-decision-button").addEventListener("click", () => {
  const activeCompanyDecisions = state.decisions.filter(
    (item) => item.status === "active" && item.scope === "company",
  );
  $("#decision-supersedes").innerHTML = '<option value="">대체하지 않음</option>'
    + activeCompanyDecisions.map((item) => (
      `<option value="${item.id}">${escapeHtml(item.subject)}</option>`
    )).join("");
  $("#decision-dialog").showModal();
});
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => $(`#${button.dataset.closeDialog}`).close());
});

$("#context-search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = $("#context-search-query").value.trim();
  if (query.length < 2) return;
  $("#context-search-status").textContent = "회사 맥락을 찾는 중입니다…";
  try {
    state.contextSearch = await api(
      `/api/v1/context/search?q=${encodeURIComponent(query)}&limit=12`,
    );
    renderContextSearch();
    $("#context-search-status").textContent =
      `전체 ${state.contextSearch.total}건 중 ${state.contextSearch.items.length}건 표시`;
  } catch (error) {
    $("#context-search-status").textContent = error.message;
  }
});

$("#goal-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#goal-form-status").textContent = "저장 중입니다…";
  try {
    await api("/api/v1/goals", { method: "POST", body: JSON.stringify({
      title: $("#goal-title").value.trim(),
      description: $("#goal-description").value.trim() || null,
      success_metric: $("#goal-success-metric").value.trim() || null,
      owner: $("#goal-owner").value.trim() || null,
      target_date: $("#goal-target-date").value || null,
      status: $("#goal-status").value,
    }) });
    $("#goal-form").reset();
    $("#goal-form-status").textContent = "";
    $("#goal-dialog").close();
    await loadDashboard();
  } catch (error) { $("#goal-form-status").textContent = error.message; }
});

$("#project-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#project-form-status").textContent = "저장 중입니다…";
  try {
    await api("/api/v1/projects", { method: "POST", body: JSON.stringify({
      title: $("#project-title").value.trim(),
      description: $("#project-description").value.trim() || null,
      status: $("#project-status").value,
      goal_id: $("#project-goal-id").value || null,
    }) });
    $("#project-form").reset();
    $("#project-form-status").textContent = "";
    $("#project-dialog").close();
    await loadDashboard();
  } catch (error) { $("#project-form-status").textContent = error.message; }
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
    const supersedesDecisionId = $("#decision-supersedes").value;
    if (supersedesDecisionId && $("#decision-lifecycle-status").value !== "active") {
      throw new Error("기존 결정을 대체하는 새 결정은 '확정 결정'으로 저장해 주세요.");
    }
    await api("/api/v1/decisions", { method: "POST", body: JSON.stringify({
      subject: $("#decision-subject").value.trim(),
      choice: $("#decision-choice").value.trim(),
      rationale: $("#decision-rationale").value.trim(),
      decided_by: "CEO",
      status: $("#decision-lifecycle-status").value,
      supersedes_decision_id: supersedesDecisionId || null,
    }) });
    $("#decision-form").reset();
    $("#decision-status").textContent = "";
    $("#decision-dialog").close();
    await loadDashboard();
  } catch (error) { $("#decision-status").textContent = error.message; }
});

$("#decision-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-decision-status]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/v1/decisions/${button.dataset.decisionId}/transition`, {
      method: "POST",
      body: JSON.stringify({
        status: button.dataset.decisionStatus,
        note: "CEO Desk에서 변경",
      }),
    });
    await loadDashboard();
  } catch (error) {
    alert(error.message);
    button.disabled = false;
  }
});

$("#commitment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#commitment-status").textContent = "저장 중입니다…";
  try {
    const decisionId = $("#commitment-decision-id").value;
    await api("/api/v1/commitments", { method: "POST", body: JSON.stringify({
      statement: $("#commitment-statement").value.trim(),
      owner_type: $("#commitment-owner-type").value,
      owner_id: $("#commitment-owner-id").value.trim(),
      due_at: new Date($("#commitment-due-at").value).toISOString(),
      decision_id: decisionId || null,
      source_type: decisionId ? "decision" : "manual",
      provenance: { channel: "ceo_desk" },
    }) });
    $("#commitment-form").reset();
    $("#commitment-owner-id").value = "CEO";
    $("#commitment-status").textContent = "";
    $("#commitment-dialog").close();
    await loadDashboard();
  } catch (error) { $("#commitment-status").textContent = error.message; }
});

$("#commitment-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-commitment-status]");
  if (!button) return;
  button.disabled = true;
  try {
    await api(`/api/v1/commitments/${button.dataset.commitmentId}/transition`, {
      method: "POST",
      body: JSON.stringify({
        status: button.dataset.commitmentStatus,
        note: "CEO Desk에서 변경",
      }),
    });
    await loadDashboard();
  } catch (error) {
    alert(error.message);
    button.disabled = false;
  }
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
