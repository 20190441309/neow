/**
 * Neow Web Studio — Frontend Controller (ES6+)
 */

const state = {
  busy: false,
  activeModel: null,
  models: [],
  presets: [],
  files: [],
  skills: [],
  todos: [],
  editingModelName: "",
  previewFilePath: "",
  streamingAssistantEl: null,
  streamingAssistantText: "",
  streamingReasoningEl: null,
  streamingReasoningText: "",
  toolCardsById: new Map(),
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdownLite(text) {
  if (!text) return "";
  const parts = String(text).split(/(```[\s\S]*?```)/g);
  return parts
    .map((part) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        const lines = part.slice(3, -3).split("\n");
        const firstLine = (lines[0] || "").trim();
        const code = lines.slice(firstLine && !firstLine.includes(" ") ? 1 : 0).join("\n");
        return `<pre><code>${escapeHtml(code)}</code></pre>`;
      }
      return escapeHtml(part)
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    })
    .join("");
}

function renderDiffHtml(diffText) {
  if (!diffText) return "";
  const lines = String(diffText).split("\n");
  const htmlLines = lines.map((line) => {
    let cls = "diff-line";
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
      cls += " diff-hdr";
    } else if (line.startsWith("+")) {
      cls += " diff-add";
    } else if (line.startsWith("-")) {
      cls += " diff-del";
    }
    return `<div class="${cls}">${escapeHtml(line)}</div>`;
  });
  return `<div class="diff-block">${htmlLines.join("")}</div>`;
}

async function apiGet(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(path, body = {}) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function scrollTimelineBottom() {
  const tl = $("#timeline");
  if (tl) tl.scrollTop = tl.scrollHeight;
}

function setBusyState(busy) {
  state.busy = Boolean(busy);
  $("#busy-indicator").classList.toggle("hidden", !state.busy);
  $("#btn-stop").classList.toggle("hidden", !state.busy);
  $("#btn-send").disabled = state.busy;
}

function updateTopbar(snap) {
  if (snap.cwd) {
    $("#meta-cwd").textContent = snap.cwd;
    $("#meta-cwd").title = snap.cwd;
  }
  if (snap.git_branch !== undefined) {
    $("#meta-branch").textContent = snap.git_branch ? `git:${snap.git_branch}` : "no-git";
  }
  state.activeModel = snap.active_model || null;
  const dot = $("#model-status-dot");
  const label = $("#active-model-label");
  if (state.activeModel) {
    dot.classList.remove("unconfigured");
    label.textContent = snap.model_id && snap.model_id !== state.activeModel
      ? `${state.activeModel} (${snap.model_id})`
      : state.activeModel;
  } else {
    dot.classList.add("unconfigured");
    label.textContent = "未配置模型 (点击配置)";
  }

  if (snap.approval_mode) {
    $("#select-approval-mode").value = snap.approval_mode;
  }
  if (snap.effort) {
    $("#select-effort").value = snap.effort;
  }
  if (snap.usage) {
    updateUsageStats(snap.usage);
  }
  if (snap.todos) {
    renderTodos(snap.todos);
  }
  if (snap.goal) {
    renderGoalState(snap.goal);
  }
  if (snap.plan) {
    renderPlanBanner(snap.plan);
  }
  setBusyState(snap.busy);
}

function updateUsageStats(usage) {
  const inTok = usage.input_tokens || 0;
  const outTok = usage.output_tokens || 0;
  const cost = Number(usage.cost || 0).toFixed(4);
  $("#stat-tokens").textContent = `↑ ${inTok.toLocaleString()} · ↓ ${outTok.toLocaleString()}`;
  $("#stat-cost").textContent = `$${cost}`;
}

/* Timeline Rendering */

function hideWelcomeIfNeeded() {
  const hero = $("#welcome-hero");
  if (hero) hero.classList.add("hidden");
}

function appendUserCard(text) {
  hideWelcomeIfNeeded();
  const card = document.createElement("div");
  card.className = "msg-card msg-user";
  card.innerHTML = `
    <div class="msg-header"><span>YOU</span><span>刚刚</span></div>
    <div class="msg-body">${escapeHtml(text)}</div>
  `;
  $("#timeline").appendChild(card);
  scrollTimelineBottom();
}

function ensureStreamingReasoningCard() {
  hideWelcomeIfNeeded();
  if (state.streamingReasoningEl) return state.streamingReasoningEl;
  const card = document.createElement("div");
  card.className = "thinking-card";
  card.innerHTML = `
    <div class="card-summary">
      <span>💭 深度思考中...</span>
      <span class="think-toggle-hint">点击折叠/展开</span>
    </div>
    <div class="card-details"></div>
  `;
  card.querySelector(".card-summary").addEventListener("click", () => {
    card.querySelector(".card-details").classList.toggle("hidden");
  });
  $("#timeline").appendChild(card);
  state.streamingReasoningEl = card;
  state.streamingReasoningText = "";
  scrollTimelineBottom();
  return card;
}

function ensureStreamingAssistantCard() {
  hideWelcomeIfNeeded();
  if (state.streamingAssistantEl) return state.streamingAssistantEl;
  const card = document.createElement("div");
  card.className = "msg-card msg-assistant";
  card.innerHTML = `
    <div class="msg-header"><span>◆ NEOW AGENT</span><span>生成中...</span></div>
    <div class="msg-body"></div>
  `;
  $("#timeline").appendChild(card);
  state.streamingAssistantEl = card;
  state.streamingAssistantText = "";
  scrollTimelineBottom();
  return card;
}

function finalizeStreamingAssistantCard(fullContent) {
  if (fullContent && !state.streamingAssistantEl) {
    ensureStreamingAssistantCard();
  }
  if (state.streamingAssistantEl) {
    const body = state.streamingAssistantEl.querySelector(".msg-body");
    const text = fullContent || state.streamingAssistantText;
    body.innerHTML = renderMarkdownLite(text);
    const hdr = state.streamingAssistantEl.querySelector(".msg-header span:last-child");
    if (hdr) hdr.textContent = "完成";
  }
  state.streamingAssistantEl = null;
  state.streamingAssistantText = "";
  state.streamingReasoningEl = null;
  state.streamingReasoningText = "";
  scrollTimelineBottom();
}

function appendToolStartedCard(ev) {
  hideWelcomeIfNeeded();
  // Flush current assistant card before tool card so chronological order stays exact
  if (state.streamingAssistantEl) {
    finalizeStreamingAssistantCard(state.streamingAssistantText);
  }
  const card = document.createElement("div");
  card.className = "tool-card";
  const argPreview = JSON.stringify(ev.args || {});
  card.innerHTML = `
    <div class="card-summary">
      <span>🔧 <strong>${escapeHtml(ev.name)}</strong> <code style="color:var(--text-dim)">${escapeHtml(argPreview.slice(0, 80))}</code></span>
      <span class="tool-status-badge">执行中...</span>
    </div>
    <div class="card-details hidden">参数:\n${escapeHtml(JSON.stringify(ev.args || {}, null, 2))}</div>
    <div class="tool-diff-slot"></div>
  `;
  card.querySelector(".card-summary").addEventListener("click", () => {
    card.querySelector(".card-details").classList.toggle("hidden");
  });
  $("#timeline").appendChild(card);
  if (ev.call_id) state.toolCardsById.set(ev.call_id, card);
  scrollTimelineBottom();
  return card;
}

function updateToolFinishedCard(ev) {
  let card = ev.call_id ? state.toolCardsById.get(ev.call_id) : null;
  if (!card) {
    card = appendToolStartedCard({ call_id: ev.call_id, name: ev.name, args: {} });
  }
  if (ev.is_error || ev.denied) card.classList.add("error");
  const statusEl = card.querySelector(".tool-status-badge");
  if (statusEl) {
    statusEl.textContent = ev.denied ? "已拒绝" : ev.is_error ? "失败" : "✓ 完成";
    statusEl.style.color = ev.is_error || ev.denied ? "var(--danger)" : "var(--success)";
  }
  const detailsEl = card.querySelector(".card-details");
  if (detailsEl) {
    detailsEl.textContent = String(ev.result || "(无输出)");
  }
  if (ev.diff) {
    const diffSlot = card.querySelector(".tool-diff-slot");
    if (diffSlot) diffSlot.innerHTML = renderDiffHtml(ev.diff);
  }
  scrollTimelineBottom();
}

function appendNoticeCard(message, level = "info") {
  hideWelcomeIfNeeded();
  const card = document.createElement("div");
  card.className = "msg-card";
  const borderColor = level === "error" ? "var(--danger)" : level === "warn" ? "var(--warn)" : "var(--accent)";
  card.style.borderLeft = `3px solid ${borderColor}`;
  card.innerHTML = `<div class="msg-body">${escapeHtml(message)}</div>`;
  $("#timeline").appendChild(card);
  scrollTimelineBottom();
}

/* Interactive Approval & ask_user Cards */

function renderApprovalRequest(req) {
  const q = $("#interactive-queue");
  const existing = document.getElementById(`approval-${req.id}`);
  if (existing) return;

  const box = document.createElement("div");
  box.className = "approval-card";
  box.id = `approval-${req.id}`;
  box.innerHTML = `
    <div class="interactive-title">⚠️ 工具权限审批请求: ${escapeHtml(req.tool)}</div>
    <div style="font-size:12.5px;color:var(--text-dim)">${escapeHtml(req.reason || "需要确认是否执行该操作")}</div>
    <div class="interactive-params">${escapeHtml(JSON.stringify(req.params || {}, null, 2))}</div>
    <div class="interactive-actions">
      <button class="btn-primary btn-sm" data-decision="allow_once">允许一次 (Allow Once)</button>
      <button class="btn-secondary btn-sm" data-decision="allow_always">本会话始终允许 (${escapeHtml(req.tool)})</button>
      <button class="btn-danger btn-sm" data-decision="deny">拒绝 (Deny)</button>
    </div>
  `;
  box.querySelectorAll("button[data-decision]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const decision = btn.getAttribute("data-decision");
      await apiPost("/api/approval", { id: req.id, decision });
      box.remove();
    });
  });
  q.appendChild(box);
}

function renderAskUserRequest(req) {
  const q = $("#interactive-queue");
  if (document.getElementById(`ask-${req.id}`)) return;

  const box = document.createElement("div");
  box.className = "ask-card";
  box.id = `ask-${req.id}`;
  const optsHtml = (req.options || [])
    .map(
      (opt) =>
        `<button class="btn-secondary btn-sm ask-opt-btn" data-opt="${escapeHtml(opt)}">${escapeHtml(opt)}</button>`
    )
    .join("");

  box.innerHTML = `
    <div class="interactive-title">💬 Agent 向你提问</div>
    <div style="font-size:13.5px;margin-bottom:8px;">${escapeHtml(req.question)}</div>
    ${optsHtml ? `<div class="interactive-actions" style="margin-bottom:8px;">${optsHtml}</div>` : ""}
    <div style="display:flex;gap:8px;">
      <input type="text" class="ask-custom-input" placeholder="输入你的回答..." style="flex:1;padding:6px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg);color:var(--text);" />
      <button class="btn-primary btn-sm ask-submit-btn">提交回答</button>
    </div>
  `;

  const submitAnswer = async (ans) => {
    await apiPost("/api/ask_user", { id: req.id, answer: ans });
    box.remove();
  };

  box.querySelectorAll(".ask-opt-btn").forEach((btn) => {
    btn.addEventListener("click", () => submitAnswer(btn.getAttribute("data-opt")));
  });
  box.querySelector(".ask-submit-btn").addEventListener("click", () => {
    const val = box.querySelector(".ask-custom-input").value.trim();
    if (val) submitAnswer(val);
  });
  q.appendChild(box);
}

/* Right Inspector: Todos, Goal, Tasks */

function renderTodos(todos) {
  state.todos = todos || [];
  const listEl = $("#todo-list");
  const total = state.todos.length;
  const done = state.todos.filter((t) => t.status === "completed").length;
  $("#todo-count-badge").textContent = `${done}/${total}`;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  $("#todo-progress-bar").style.width = `${pct}%`;

  if (!total) {
    listEl.innerHTML = `<div class="empty-hint">多步骤任务时 Agent 会自动拆解并更新进度</div>`;
    return;
  }
  listEl.innerHTML = state.todos
    .map((t) => {
      const icon = t.status === "completed" ? "✓" : t.status === "in_progress" ? "▶" : "○";
      return `<div class="todo-item ${escapeHtml(t.status || "pending")}">
        <span>${icon}</span>
        <span>${escapeHtml(t.content || "")}</span>
      </div>`;
    })
    .join("");
}

function renderGoalState(goal) {
  const active = Boolean(goal && goal.active);
  $("#goal-status-badge").textContent = active ? `运行中 R${goal.current_round}` : "待机";
  $("#goal-inactive-view").classList.toggle("hidden", active);
  $("#goal-active-view").classList.toggle("hidden", !active);
  if (active) {
    $("#goal-active-text").textContent = goal.goal || "";
    $("#goal-round-info").textContent = `自主巡航轮次: Round ${goal.current_round} / ${goal.max_rounds}`;
  }
}

function renderPlanBanner(plan) {
  const banner = $("#plan-banner");
  if (plan && plan.pending && plan.text) {
    banner.classList.remove("hidden");
    $("#plan-editor-textarea").value = plan.text;
  } else {
    banner.classList.add("hidden");
  }
}

async function refreshTasks() {
  try {
    const data = await apiGet("/api/tasks");
    const listEl = $("#tasks-list");
    const tasks = data.tasks || [];
    if (!tasks.length) {
      listEl.innerHTML = `<div class="empty-hint">暂无后台长进程</div>`;
      return;
    }
    listEl.innerHTML = tasks
      .map(
        (t) => `
      <div class="todo-item" style="flex-direction:column;gap:4px;">
        <div style="display:flex;justify-content:space-between;width:100%;align-items:center;">
          <strong>#${escapeHtml(t.task_id)} (${escapeHtml(t.status)})</strong>
          ${
            t.status === "running"
              ? `<button class="btn-danger btn-xs kill-task-btn" data-id="${escapeHtml(t.task_id)}">终止</button>`
              : `<span style="font-size:11px;color:var(--text-muted)">exit=${t.exit_code}</span>`
          }
        </div>
        <code style="font-size:11px;color:var(--text-dim)">${escapeHtml(t.command)}</code>
      </div>
    `
      )
      .join("");
    listEl.querySelectorAll(".kill-task-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiPost("/api/tasks/kill", { task_id: btn.getAttribute("data-id") });
        refreshTasks();
      });
    });
  } catch (e) {
    // ignore
  }
}

/* Workspace Files & Skills */

async function loadWorkspaceFiles() {
  try {
    const data = await apiGet("/api/files");
    state.files = data.files || [];
    renderFilesList();
  } catch (e) {
    // ignore
  }
}

function renderFilesList() {
  const q = ($("#file-search-input").value || "").trim().toLowerCase();
  const filtered = state.files.filter((f) => !q || f.path.toLowerCase().includes(q));
  const container = $("#file-tree-list");
  if (!filtered.length) {
    container.innerHTML = `<div class="empty-hint" style="padding:8px;">无匹配文件</div>`;
    return;
  }
  container.innerHTML = filtered
    .slice(0, 120)
    .map(
      (f) => `
    <div class="file-item" data-path="${escapeHtml(f.path)}">
      <span class="file-path" title="${escapeHtml(f.path)}">📄 ${escapeHtml(f.path)}</span>
      <button class="file-ref-btn" data-ref="${escapeHtml(f.path)}" title="插入 @引用">@引用</button>
    </div>
  `
    )
    .join("");

  container.querySelectorAll(".file-item").forEach((row) => {
    row.addEventListener("click", async (ev) => {
      if (ev.target.classList.contains("file-ref-btn")) return;
      const p = row.getAttribute("data-path");
      openFilePreview(p);
    });
  });

  container.querySelectorAll(".file-ref-btn").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      insertAtReference(btn.getAttribute("data-ref"));
    });
  });
}

function insertAtReference(relPath) {
  const input = $("#prompt-input");
  const prefix = input.value && !input.value.endsWith(" ") ? " " : "";
  input.value = `${input.value}${prefix}@${relPath} `;
  input.focus();
}

async function openFilePreview(relPath) {
  try {
    const data = await apiGet(`/api/file?path=${encodeURIComponent(relPath)}`);
    state.previewFilePath = data.path;
    $("#preview-modal-title").textContent = `📄 ${data.path}`;
    $("#preview-modal-content").textContent = data.content || "";
    $("#btn-insert-file-ref").classList.remove("hidden");
    $("#modal-preview").classList.remove("hidden");
  } catch (err) {
    alert(err.message);
  }
}

async function loadSkills() {
  try {
    const data = await apiGet("/api/skills");
    state.skills = data.skills || [];
    const el = $("#skills-list");
    if (!state.skills.length) {
      el.innerHTML = `<div class="empty-hint" style="padding:8px;">当前项目未发现 SKILL.md 技能包</div>`;
      return;
    }
    el.innerHTML = state.skills
      .map(
        (s) => `
      <div class="skill-item" data-name="${escapeHtml(s.name)}">
        <div style="flex:1;min-width:0;">
          <div style="font-weight:600;color:var(--text)">🧩 ${escapeHtml(s.name)}</div>
          <div style="font-size:11px;color:var(--text-muted)">${escapeHtml(s.description || "")}</div>
        </div>
        <button class="btn-xs ${s.active ? "btn-primary" : "btn-secondary"} toggle-skill-btn" data-name="${escapeHtml(s.name)}">
          ${s.active ? "已启用" : "启用"}
        </button>
      </div>
    `
      )
      .join("");
    el.querySelectorAll(".toggle-skill-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await apiPost("/api/skills/toggle", { name: btn.getAttribute("data-name") });
        loadSkills();
      });
    });
  } catch (e) {
    // ignore
  }
}

/* Model & Gateway Studio Modal */

async function openModelsModal() {
  $("#modal-models").classList.remove("hidden");
  await refreshModelsCatalog();
}

async function refreshModelsCatalog() {
  try {
    const data = await apiGet("/api/models");
    state.models = data.models || [];
    state.presets = data.presets || [];
    state.activeModel = data.current || null;

    // Populate preset select
    const presetSel = $("#editor-preset-select");
    presetSel.innerHTML = state.presets
      .map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`)
      .join("");

    renderConfiguredModelsList();
  } catch (err) {
    setEditorStatus(err.message, true);
  }
}

function renderConfiguredModelsList() {
  const q = ($("#model-filter-input").value || "").trim().toLowerCase();
  const listEl = $("#configured-models-list");
  const filtered = state.models.filter(
    (m) =>
      !q ||
      m.name.toLowerCase().includes(q) ||
      (m.display_name || "").toLowerCase().includes(q) ||
      (m.provider || "").toLowerCase().includes(q)
  );

  if (!filtered.length) {
    listEl.innerHTML = `<div class="empty-hint">无匹配模型，可在右侧选择预设添加或点击上方「网关/Magpie 同步」</div>`;
    return;
  }

  listEl.innerHTML = filtered
    .map(
      (m) => `
    <div class="model-row-item ${m.active ? "active" : ""}">
      <div class="model-row-info" data-select="${escapeHtml(m.name)}">
        <div class="model-row-title">
          ${m.active ? "● " : ""}${escapeHtml(m.name)}
          ${m.source === "magpie" ? `<span class="badge">Magpie</span>` : ""}
        </div>
        <div class="model-row-sub">${escapeHtml(m.display_name)} · ${escapeHtml(m.provider)}</div>
      </div>
      <div class="model-row-btns">
        ${
          m.active
            ? `<span class="badge" style="background:var(--success-soft);color:var(--success)">当前使用</span>`
            : `<button class="btn-primary btn-xs switch-model-btn" data-name="${escapeHtml(m.name)}">切换</button>`
        }
        <button class="btn-secondary btn-xs edit-model-btn" data-name="${escapeHtml(m.name)}">编辑</button>
        ${
          !m.active
            ? `<button class="btn-ghost btn-xs del-model-btn" data-name="${escapeHtml(m.name)}">删除</button>`
            : ""
        }
      </div>
    </div>
  `
    )
    .join("");

  listEl.querySelectorAll(".switch-model-btn, .model-row-info").forEach((el) => {
    el.addEventListener("click", async () => {
      const name = el.getAttribute("data-name") || el.getAttribute("data-select");
      if (!name) return;
      setEditorStatus(`正在连接并切换至 ${name} ...`, false);
      try {
        const res = await apiPost("/api/models/select", { name });
        setEditorStatus(`✓ 已切换至 ${res.active_model}`, false);
        await refreshModelsCatalog();
        const snap = await apiGet("/api/state");
        updateTopbar(snap);
      } catch (err) {
        setEditorStatus(err.message, true);
      }
    });
  });

  listEl.querySelectorAll(".edit-model-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.getAttribute("data-name");
      const m = state.models.find((item) => item.name === name);
      if (m) populateEditorForEdit(m);
    });
  });

  listEl.querySelectorAll(".del-model-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const name = btn.getAttribute("data-name");
      try {
        await apiPost("/api/models/delete", { name });
        setEditorStatus(`已删除模型: ${name}`, false);
        await refreshModelsCatalog();
      } catch (err) {
        setEditorStatus(err.message, true);
      }
    });
  });
}

function populateEditorForEdit(m) {
  state.editingModelName = m.name;
  $("#editor-form-title").textContent = `✎ 编辑模型: ${m.name}`;
  $("#editor-name").value = m.name;
  $("#editor-name").disabled = true;
  $("#editor-provider").value = m.provider || "openai-compatible";
  $("#editor-url").value = m.base_url || "";
  $("#editor-model-id").value = m.model || "";
  $("#editor-api-key").value = "";
  $("#editor-api-key").placeholder = m.has_key ? "保持已保存的 Key (留空不修改)" : "粘贴 API Key";
  $("#editor-key-env").value = m.api_key_env || "";
  setEditorStatus(`正在编辑「${m.name}」`, false);
}

function resetModelEditor() {
  state.editingModelName = "";
  $("#editor-form-title").textContent = "+ 添加 / 自定义模型";
  $("#editor-preset-select").value = "custom";
  $("#editor-name").value = "";
  $("#editor-name").disabled = false;
  $("#editor-provider").value = "openai-compatible";
  $("#editor-url").value = "";
  $("#editor-model-id").value = "";
  $("#editor-api-key").value = "";
  $("#editor-api-key").placeholder = "粘贴 API Key (本地 Ollama/Magpie 可留空)";
  $("#editor-key-env").value = "";
  $("#editor-fetched-models").classList.add("hidden");
  setEditorStatus("", false);
}

function setEditorStatus(msg, isError = false) {
  const el = $("#editor-status-msg");
  el.textContent = msg || "";
  el.classList.toggle("error", Boolean(isError));
}

/* Prompt Submission & Slash Commands */

async function handleSendPrompt() {
  const input = $("#prompt-input");
  const raw = (input.value || "").trim();
  if (!raw || state.busy) return;

  // Handle quick client-side slash commands
  if (raw === "/model" || raw === "/models" || raw === "/model add") {
    input.value = "";
    openModelsModal();
    return;
  }
  if (raw === "/clear") {
    input.value = "";
    await apiPost("/api/clear");
    return;
  }
  if (raw === "/compact") {
    input.value = "";
    await apiPost("/api/compact");
    return;
  }
  if (raw.startsWith("/goal ")) {
    const goalText = raw.slice(6).trim();
    input.value = "";
    if (goalText) await apiPost("/api/goal", { action: "start", goal: goalText });
    return;
  }
  if (raw.startsWith("/plan ")) {
    const planTask = raw.slice(6).trim();
    input.value = "";
    if (planTask) {
      appendNoticeCard(`📋 正在为「${planTask}」生成架构实施计划...`, "info");
      try {
        await apiPost("/api/plan", { action: "generate", task: planTask });
      } catch (err) {
        appendNoticeCard(err.message, "error");
      }
    }
    return;
  }

  input.value = "";
  try {
    setBusyState(true);
    await apiPost("/api/chat", { prompt: raw });
  } catch (err) {
    setBusyState(false);
    appendNoticeCard(err.message, "error");
    if (err.message.includes("model") || err.message.includes("API key") || err.message.includes("配置")) {
      openModelsModal();
    }
  }
}

/* SSE Event Stream */

function connectSSE() {
  const es = new EventSource("/api/events");

  es.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      handleServerEvent(ev);
    } catch (err) {
      // ignore malformed event
    }
  };

  es.onerror = () => {
    es.close();
    setTimeout(connectSSE, 2000);
  };
}

function handleServerEvent(ev) {
  switch (ev.type) {
    case "user_message":
      appendUserCard(ev.text);
      setBusyState(true);
      break;
    case "reasoning_started":
      ensureStreamingReasoningCard();
      break;
    case "reasoning_delta": {
      const card = ensureStreamingReasoningCard();
      state.streamingReasoningText += ev.text || "";
      card.querySelector(".card-details").textContent = state.streamingReasoningText;
      scrollTimelineBottom();
      break;
    }
    case "reasoning_end": {
      if (state.streamingReasoningEl) {
        const hdr = state.streamingReasoningEl.querySelector(".card-summary span:first-child");
        if (hdr) hdr.textContent = `💭 思考完成 (${ev.duration || 0}s)`;
        state.streamingReasoningEl.querySelector(".card-details").classList.add("hidden");
      }
      state.streamingReasoningEl = null;
      break;
    }
    case "content_delta": {
      const card = ensureStreamingAssistantCard();
      state.streamingAssistantText += ev.text || "";
      card.querySelector(".msg-body").innerHTML = renderMarkdownLite(state.streamingAssistantText);
      scrollTimelineBottom();
      break;
    }
    case "tool_started":
      appendToolStartedCard(ev);
      break;
    case "tool_progress": {
      const card = ev.call_id ? state.toolCardsById.get(ev.call_id) : null;
      if (card) {
        const badge = card.querySelector(".tool-status-badge");
        if (badge) badge.textContent = ev.message || "执行中...";
      }
      break;
    }
    case "tool_finished":
      updateToolFinishedCard(ev);
      loadWorkspaceFiles();
      refreshTasks();
      break;
    case "todos_updated":
      renderTodos(ev.todos || []);
      break;
    case "goal_updated":
      renderGoalState(ev);
      break;
    case "plan_updated":
      renderPlanBanner(ev);
      break;
    case "approval_request":
      renderApprovalRequest(ev);
      break;
    case "ask_user_request":
      renderAskUserRequest(ev);
      break;
    case "notice":
      appendNoticeCard(ev.message, ev.level);
      break;
    case "turn_completed":
      finalizeStreamingAssistantCard(ev.content);
      if (ev.usage) updateUsageStats(ev.usage);
      setBusyState(false);
      break;
    case "turn_failed":
      finalizeStreamingAssistantCard("");
      appendNoticeCard(ev.message || "对话回合失败", "error");
      setBusyState(false);
      break;
    case "model_switched":
      apiGet("/api/state").then(updateTopbar).catch(() => {});
      break;
    case "cleared":
      $("#timeline").innerHTML = "";
      $("#interactive-queue").innerHTML = "";
      setBusyState(false);
      break;
  }
}

/* Hydrate Initial State & Bind UI Events */

async function initApp() {
  // Theme toggle
  $("#btn-theme-toggle").addEventListener("click", () => {
    const html = document.documentElement;
    const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
  });

  // Sidebar tabs
  $$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".tab-btn").forEach((b) => b.classList.remove("active"));
      $$(".sidebar-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`#tab-${btn.getAttribute("data-tab")}`).classList.add("active");
    });
  });

  // Starter chips
  $$(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      $("#prompt-input").value = chip.getAttribute("data-prompt") || "";
      handleSendPrompt();
    });
  });

  // Prompt send / stop
  $("#btn-send").addEventListener("click", handleSendPrompt);
  $("#prompt-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey) {
      ev.preventDefault();
      handleSendPrompt();
    }
  });
  $("#btn-stop").addEventListener("click", () => apiPost("/api/cancel"));

  // Topbar controls
  $("#btn-open-models").addEventListener("click", openModelsModal);
  $("#btn-open-models-bottom").addEventListener("click", openModelsModal);
  $("#btn-insert-at").addEventListener("click", () => {
    $("#file-search-input").focus();
  });

  $("#select-approval-mode").addEventListener("change", (ev) => {
    apiPost("/api/mode", { approval_mode: ev.target.value });
  });
  $("#select-effort").addEventListener("change", (ev) => {
    apiPost("/api/mode", { effort: ev.target.value });
  });

  // Left quick actions
  $("#act-new-chat").addEventListener("click", () => apiPost("/api/clear"));
  $("#act-compact").addEventListener("click", () => apiPost("/api/compact"));
  $("#act-open-plan").addEventListener("click", () => {
    $("#modal-plan-prompt").classList.remove("hidden");
    $("#plan-task-input").focus();
  });
  $("#act-open-goal").addEventListener("click", () => {
    $("#goal-quick-input").focus();
  });
  $("#act-git-diff").addEventListener("click", async () => {
    const data = await apiGet("/api/git");
    $("#preview-modal-title").textContent = `🔀 Git 变更 (${data.branch || "workspace"})`;
    $("#preview-modal-content").textContent = `${data.status}\n\n${data.diff || "(无未提交代码 Diff)"}`;
    $("#btn-insert-file-ref").classList.add("hidden");
    $("#modal-preview").classList.remove("hidden");
  });

  // Plan modal & banner
  $("#btn-submit-plan-task").addEventListener("click", async () => {
    const task = ($("#plan-task-input").value || "").trim();
    if (!task) return;
    $("#modal-plan-prompt").classList.add("hidden");
    appendNoticeCard(`📋 正在生成架构实施计划: ${task} ...`, "info");
    try {
      await apiPost("/api/plan", { action: "generate", task });
    } catch (err) {
      appendNoticeCard(err.message, "error");
    }
  });
  $("#btn-approve-plan").addEventListener("click", async () => {
    const plan = $("#plan-editor-textarea").value;
    await apiPost("/api/plan", { action: "approve", plan });
  });
  $("#btn-close-plan").addEventListener("click", () => {
    $("#plan-banner").classList.add("hidden");
  });

  // Goal panel
  $("#btn-start-goal").addEventListener("click", async () => {
    const goal = ($("#goal-quick-input").value || "").trim();
    if (!goal) return;
    $("#goal-quick-input").value = "";
    await apiPost("/api/goal", { action: "start", goal });
  });
  $("#btn-stop-goal").addEventListener("click", () => apiPost("/api/goal", { action: "stop" }));
  $("#btn-refresh-tasks").addEventListener("click", refreshTasks);

  // File filter & preview insert
  $("#file-search-input").addEventListener("input", renderFilesList);
  $("#btn-insert-file-ref").addEventListener("click", () => {
    if (state.previewFilePath) insertAtReference(state.previewFilePath);
    $("#modal-preview").classList.add("hidden");
  });

  // Modal close buttons
  $$(".modal-close").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-close");
      if (target) $(`#${target}`).classList.add("hidden");
    });
  });

  // Model Studio Modal events
  $("#model-filter-input").addEventListener("input", renderConfiguredModelsList);
  $("#btn-reset-editor").addEventListener("click", resetModelEditor);

  $("#editor-preset-select").addEventListener("change", (ev) => {
    const pid = ev.target.value;
    const preset = state.presets.find((p) => p.id === pid);
    if (!preset || pid === "custom") return;
    if (!state.editingModelName) {
      $("#editor-name").value = preset.default_name || pid;
    }
    $("#editor-provider").value = preset.provider || "openai-compatible";
    $("#editor-url").value = preset.base_url || "";
    $("#editor-model-id").value = preset.default_model || "";
    $("#editor-key-env").value = preset.api_key_env || "";
    if (preset.default_key) {
      $("#editor-api-key").value = preset.default_key;
    }
    setEditorStatus(`已套用「${preset.label}」预设，请填写 API Key 后保存或点击拉取模型`, false);
  });

  $("#btn-fetch-remote-models").addEventListener("click", async () => {
    const base_url = $("#editor-url").value.trim();
    const api_key = $("#editor-api-key").value.trim();
    const api_key_env = $("#editor-key-env").value.trim();
    setEditorStatus("正在请求 /models 拉取可用模型列表...", false);
    try {
      const res = await apiPost("/api/models/fetch", { base_url, api_key, api_key_env });
      const models = res.models || [];
      const sel = $("#editor-fetched-models");
      sel.innerHTML = models
        .map((mid) => `<option value="${escapeHtml(mid)}">选用远端模型: ${escapeHtml(mid)}</option>`)
        .join("");
      sel.classList.remove("hidden");
      if (models.length) {
        $("#editor-model-id").value = models[0];
      }
      setEditorStatus(`✓ 成功拉取 ${models.length} 个模型，可在下拉框中切换`, false);
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  $("#editor-fetched-models").addEventListener("change", (ev) => {
    if (ev.target.value) {
      $("#editor-model-id").value = ev.target.value;
    }
  });

  $("#btn-save-model").addEventListener("click", async () => {
    setEditorStatus("正在保存并验证模型配置...", false);
    try {
      const payload = {
        name: $("#editor-name").value.trim(),
        is_edit: Boolean(state.editingModelName),
        provider: $("#editor-provider").value,
        base_url: $("#editor-url").value.trim(),
        model: $("#editor-model-id").value.trim(),
        api_key: $("#editor-api-key").value.trim(),
        api_key_env: $("#editor-key-env").value.trim(),
        activate: true,
      };
      await apiPost("/api/models/save", payload);
      setEditorStatus(`✓ 模型 ${payload.name} 已保存并启用`, false);
      await refreshModelsCatalog();
      const snap = await apiGet("/api/state");
      updateTopbar(snap);
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  $("#btn-test-model").addEventListener("click", async () => {
    setEditorStatus("正在测试连接...", false);
    try {
      const res = await apiPost("/api/models/test", {
        name: $("#editor-name").value.trim() || "test",
        provider: $("#editor-provider").value,
        base_url: $("#editor-url").value.trim(),
        model: $("#editor-model-id").value.trim(),
        api_key: $("#editor-api-key").value.trim(),
        api_key_env: $("#editor-key-env").value.trim(),
      });
      setEditorStatus(res.ok ? "✓ 连接测试成功！" : "连接失败，请检查地址和 Key", !res.ok);
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  $("#btn-import-gateway").addEventListener("click", async () => {
    const base_url = $("#editor-url").value.trim();
    const api_key = $("#editor-api-key").value.trim();
    const api_key_env = $("#editor-key-env").value.trim();
    const prefix = $("#editor-name").value.trim() || "gw";
    setEditorStatus("正在从该网关批量导入全部模型...", false);
    try {
      const res = await apiPost("/api/models/sync", { base_url, api_key, api_key_env, prefix });
      setEditorStatus(`✓ 已成功导入 ${res.count} 个模型 (前缀: ${prefix}/)`, false);
      await refreshModelsCatalog();
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  $("#btn-sync-magpie").addEventListener("click", async () => {
    setEditorStatus("正在同步本地 Magpie / 默认网关模型...", false);
    try {
      const res = await apiPost("/api/models/sync", {});
      const extra = res.preferred ? ` (推荐: ${res.preferred})` : "";
      setEditorStatus(`✓ 已同步 ${res.count} 个模型${extra}`, false);
      await refreshModelsCatalog();
      const snap = await apiGet("/api/state");
      updateTopbar(snap);
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  // Load initial snapshot
  try {
    const snap = await apiGet("/api/state");
    updateTopbar(snap);
    (snap.timeline || []).forEach((item) => {
      if (item.kind === "user") appendUserCard(item.text);
      else if (item.kind === "assistant") finalizeStreamingAssistantCard(item.text);
      else if (item.kind === "tool") updateToolFinishedCard(item);
      else if (item.kind === "notice" || item.kind === "error") {
        appendNoticeCard(item.message, item.kind === "error" ? "error" : item.level);
      }
    });
    (snap.pending_approvals || []).forEach(renderApprovalRequest);
    (snap.pending_questions || []).forEach(renderAskUserRequest);
    if (!snap.active_model) {
      openModelsModal();
    }
  } catch (e) {
    // ignore
  }

  loadWorkspaceFiles();
  loadSkills();
  refreshTasks();
  connectSSE();
}

document.addEventListener("DOMContentLoaded", initApp);
