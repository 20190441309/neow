/**
 * Neow Web Studio — Frontend Controller (ES6+)
 */

const state = {
  busy: false,
  activeModel: null,
  models: [],
  presets: [],
  files: [],
  filesQuery: "",
  fileDirectories: new Map(),
  expandedDirectories: new Set(),
  fileTreeVersion: 0,
  skills: [],
  todos: [],
  editingModelName: "",
  previewFilePath: "",
  streamingAssistantEl: null,
  streamingAssistantText: "",
  streamingReasoningEl: null,
  streamingReasoningText: "",
  toolCardsById: new Map(),
  welcomeHero: null,
  followTimeline: true,
  submitting: false,
  eventSource: null,
  reconnectTimer: null,
  modalReturnFocus: null,
  needsSnapshot: false,
  recovering: false,
  recoveryEvents: [],
  recoveryGeneration: 0,
  recoveryController: null,
  timelineRecords: [],
  lastPlanText: "",
  planPending: false,
  planCollapsed: false,
  completedAssistantPrefix: "",
  workspacePath: "",
  workspaceGeneration: null,
  workspaceEpoch: 0,
  workspaceBrowsePath: "",
  workspaceBrowseParent: null,
  workspaceBrowseRequest: 0,
  workspaceSwitching: false,
  filesTruncated: false,
  fileSearchTimer: null,
  fileRequest: 0,
  fileController: null,
  previewRequest: 0,
  lastClearState: null,
  modelEditorGeneration: 0,
  modelFetchRequest: 0,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

function icon(name) {
  const paths = {
    folder:
      '<path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
    tool: '<path d="m14.7 6.3 3 3a6 6 0 0 1-7.4 7.4l-4.6 4.6a2.1 2.1 0 0 1-3-3l4.6-4.6a6 6 0 0 1 7.4-7.4Z"/><path d="m14.7 6.3 4-4 3 3-4 4"/>',
    thinking: '<path d="M9 18h6M10 21h4M9 15a6 6 0 1 1 6 0v3H9z"/>',
    shield:
      '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z"/><path d="m9 12 2 2 4-4"/>',
    message:
      '<path d="M21 11a8 8 0 0 1-8 8H8l-5 3V9a7 7 0 0 1 7-7h3a8 8 0 0 1 8 9Z"/><path d="M7 8h10M7 12h7"/>',
    skill: '<path d="m12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5"/>',
  };
  return `<svg class="icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.file}</svg>`;
}

function setOptionalText(selector, text) {
  const el = $(selector);
  if (el) el.textContent = text;
  return el;
}

function resizePromptInput() {
  const input = $("#prompt-input");
  const computedCap = parseFloat(getComputedStyle(input).maxHeight);
  const cap = Number.isFinite(computedCap) ? computedCap : 180;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, cap)}px`;
  input.style.overflowY = input.scrollHeight > cap ? "auto" : "hidden";
}

function focusPrompt() {
  closePopovers();
  closeDrawers(false);
  $("#prompt-input").focus();
  resizePromptInput();
}

function showError(err) {
  const message =
    err instanceof Error ? err.message : String(err || "操作失败，请重试");
  const modal = $(".modal-backdrop:not(.hidden)");
  if (modal) {
    let errorEl = modal.querySelector(".modal-error");
    if (!errorEl) {
      errorEl = document.createElement("p");
      errorEl.className = "modal-error editor-status error";
      errorEl.setAttribute("role", "alert");
      (modal.querySelector(".modal-body") || modal).prepend(errorEl);
    }
    errorEl.textContent = message;
    return;
  }
  appendNoticeCard(message, "error");
}

async function runAction(action, button = null, onError = showError) {
  if (button && button.disabled) return;
  if (button) button.disabled = true;
  try {
    return await action();
  } catch (err) {
    onError(err);
  } finally {
    if (button) button.disabled = false;
    syncBusyControls();
  }
}

function modalFocusables(modal) {
  return Array.from(
    modal.querySelectorAll(
      'button, a[href], summary, input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter(
    (el) =>
      !el.disabled &&
      el.getAttribute?.("tabindex") !== "-1" &&
      !el.closest(".hidden, [inert]") &&
      el.getClientRects().length > 0,
  );
}

function openModal(id, focusSelector = "") {
  const modal = document.getElementById(id);
  if (!modal) return;
  closePopovers(true);
  if (!$(".modal-backdrop:not(.hidden)"))
    state.modalReturnFocus = document.activeElement;
  $$(".modal-backdrop:not(.hidden)").forEach((other) => {
    if (other !== modal) closeModal(other.id, false);
  });
  modal.querySelector(".modal-error")?.remove();
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  const shell = $(".app-shell");
  if (shell) shell.inert = true;
  const dialog = modal.querySelector(".modal-dialog") || modal;
  dialog.setAttribute("tabindex", "-1");
  const target =
    (focusSelector && modal.querySelector(focusSelector)) ||
    modalFocusables(modal)[0] ||
    dialog;
  target.focus();
}

function closeModal(id, restoreFocus = true) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  const shell = $(".app-shell");
  if (shell) shell.inert = Boolean($(".modal-backdrop:not(.hidden)"));
  if (restoreFocus && !$(".modal-backdrop:not(.hidden)")) {
    const target = state.modalReturnFocus;
    state.modalReturnFocus = null;
    if (target?.isConnected && !target.closest("[inert]")) target.focus();
    else $("#prompt-input").focus();
  }
}

function activeDrawer() {
  const shell = $(".app-shell");
  if (!shell) return null;
  for (const [name, query] of [
    ["sidebar", "(max-width: 760px)"],
    ["inspector", null],
  ]) {
    if (
      (!query || window.matchMedia(query).matches) &&
      shell.classList.contains(`${name}-open`)
    ) {
      return {
        name,
        panel: $(`#workspace-${name}`),
        toggle: $(`#btn-toggle-${name}`),
      };
    }
  }
  return null;
}

function syncDrawerAccessibility() {
  const shell = $(".app-shell");
  if (!shell) return;
  const active = activeDrawer();
  [
    [
      "sidebar",
      "#workspace-sidebar",
      "#btn-toggle-sidebar",
      "(max-width: 760px)",
    ],
    ["inspector", "#workspace-inspector", "#btn-toggle-inspector", null],
  ].forEach(([name, panelSelector, toggleSelector, query]) => {
    const compact = !query || window.matchMedia(query).matches;
    const open = !compact || shell.classList.contains(`${name}-open`);
    const panel = $(panelSelector);
    const toggle = $(toggleSelector);
    if (panel) {
      panel.inert = !open || Boolean(active && active.name !== name);
      panel.setAttribute("aria-hidden", String(!open));
    }
    if (toggle) {
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute(
        "aria-label",
        `${open ? "关闭" : "打开"}${name === "sidebar" ? "工作区侧栏" : "任务面板"}`,
      );
    }
  });
  const center = $(".center-stage");
  if (center) center.inert = Boolean(active);
  // The header stays operable, including the toggle that closes the drawer.
  const backdrop = $("#panel-backdrop");
  if (backdrop) backdrop.setAttribute("tabindex", "-1");
}

function setDrawer(name, open) {
  const shell = $(".app-shell");
  if (!shell) return;
  const compact =
    name !== "sidebar" || window.matchMedia("(max-width: 760px)").matches;
  if (open) closePopovers(true);
  if (open)
    shell.classList.remove(
      name === "sidebar" ? "inspector-open" : "sidebar-open",
    );
  shell.classList.toggle(`${name}-open`, Boolean(open && compact));
  syncDrawerAccessibility();
  const drawer = activeDrawer();
  if (open && drawer?.panel) {
    drawer.panel.setAttribute("tabindex", "-1");
    const focusDrawer = () => {
      if (activeDrawer()?.name !== name || $(".modal-backdrop:not(.hidden)"))
        return;
      if (!drawer.panel.contains(document.activeElement))
        (modalFocusables(drawer.panel)[0] || drawer.panel).focus();
    };
    (modalFocusables(drawer.panel)[0] || drawer.panel).focus();
    if (typeof requestAnimationFrame === "function")
      requestAnimationFrame(focusDrawer);
  } else if (!open && compact) {
    $(`#btn-toggle-${name}`)?.focus();
  }
}

function closeDrawers(restoreFocus = true) {
  const shell = $(".app-shell");
  if (!shell) return;
  const drawer = activeDrawer();
  shell.classList.remove("sidebar-open", "inspector-open");
  syncDrawerAccessibility();
  if (restoreFocus && drawer) drawer.toggle?.focus();
}

function selectSidebarTab(tab) {
  $$(".tab-btn").forEach((button) => {
    const active = button.getAttribute("data-tab") === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.setAttribute("tabindex", active ? "0" : "-1");
  });
  $$(".sidebar-pane").forEach((pane) =>
    pane.classList.toggle("active", pane.id === `tab-${tab}`),
  );
}

function setLibraryOpen(open) {
  const panel = $("#workspace-library");
  const toggle = $("#btn-toggle-library");
  if (!panel || !toggle) return;
  if (!open && panel.contains(document.activeElement)) toggle.focus();
  panel.classList.toggle("hidden", !open);
  toggle.setAttribute("aria-expanded", String(Boolean(open)));
  toggle.classList.toggle("active", Boolean(open));
  $("#btn-show-conversation")?.classList.toggle("active", !open);
}

function openFileLibrary() {
  setLibraryOpen(true);
  selectSidebarTab("files");
  setDrawer("sidebar", true);
  $("#file-search-input").focus();
}

function closePopovers(restoreFocus = false, except = null) {
  let closed = false;
  $$("[data-popover][open]").forEach((popover) => {
    if (popover === except) return;
    if (restoreFocus && popover.contains(document.activeElement))
      popover.querySelector("summary")?.focus();
    popover.open = false;
    closed = true;
  });
  return closed;
}

function syncComposerOptions() {
  const mode = $("#select-approval-mode")?.value;
  const modeLabel =
    {
      "always-ask": "所有操作询问",
      write: "写入前询问",
      yolo: "全自动执行",
    }[mode] || "执行权限";
  const effort = $("#select-effort")?.value;
  const effortLabel =
    { off: "关闭", low: "轻量", medium: "均衡", high: "深入" }[effort] ||
    "默认";
  setOptionalText("#approval-mode-label", modeLabel);
  const trigger = $("#composer-options-trigger");
  if (trigger) {
    trigger.classList.toggle("unrestricted", mode === "yolo");
    trigger.title = `执行权限：${modeLabel} · 思考：${effortLabel}`;
    trigger.setAttribute(
      "aria-label",
      `执行权限：${modeLabel}；思考深度：${effortLabel}；打开设置`,
    );
  }
}

function setConnectionState(status) {
  const labels = {
    connecting: "连接中",
    connected: "本地已连接",
    disconnected: "连接断开 · 重试中",
  };
  setOptionalText("#connection-label", labels[status] || labels.connecting);
  const dot = $("#connection-dot");
  if (dot) {
    dot.dataset.status = status;
    dot.classList.toggle("connected", status === "connected");
    dot.classList.toggle("disconnected", status === "disconnected");
    dot.classList.toggle("unconfigured", status !== "connected");
  }
}

function escapeHtml(str) {
  return String(str ?? "")
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
        const code = lines
          .slice(firstLine && !firstLine.includes(" ") ? 1 : 0)
          .join("\n");
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
    if (
      line.startsWith("+++") ||
      line.startsWith("---") ||
      line.startsWith("@@")
    ) {
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

async function apiGet(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

async function apiPost(path, body = {}) {
  const generation = state.workspaceGeneration;
  if (!Number.isInteger(generation) || generation < 0)
    throw new Error("工作区状态尚未同步，请等待连接恢复后再试。");
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, workspace_generation: generation }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  if (data.ok === false)
    throw new Error(data.error || "操作未完成，请检查当前状态后重试");
  return data;
}

function scrollTimelineBottom(force = false) {
  const tl = $("#timeline");
  if (tl && (force || state.followTimeline)) tl.scrollTop = tl.scrollHeight;
}

function setBusyState(busy) {
  state.busy = Boolean(busy);
  $("#busy-indicator").classList.toggle("hidden", !state.busy);
  $("#btn-stop").classList.toggle("hidden", !state.busy);
  $("#btn-send").classList.toggle("hidden", state.busy);
  $("#btn-send").disabled = state.busy;
  $("#timeline").setAttribute("aria-busy", String(state.busy));
  setOptionalText("#session-status", state.busy ? "正在执行" : "准备就绪");
  syncBusyControls();
}

function syncBusyControls() {
  const locked = state.busy || state.submitting || state.workspaceSwitching;
  [
    "#btn-send",
    "#act-new-chat",
    "#act-compact",
    "#btn-approve-plan",
    "#btn-submit-plan-task",
    "#btn-start-goal",
    "#btn-save-model",
    "#btn-test-model",
    "#btn-import-gateway",
    "#btn-sync-magpie",
    "#select-approval-mode",
    "#select-effort",
  ].forEach((selector) => {
    const control = $(selector);
    if (control) control.disabled = locked;
  });
  const switchButton = $("#btn-switch-workspace");
  if (switchButton)
    switchButton.disabled =
      locked ||
      !state.workspaceBrowsePath ||
      state.workspaceBrowsePath === state.workspacePath;
  $$(".switch-model-btn, .del-model-btn, .toggle-skill-btn").forEach(
    (button) => {
      button.disabled = locked;
    },
  );
}

function requireIdle() {
  if (!state.busy && !state.submitting && !state.workspaceSwitching)
    return true;
  showError(new Error("当前任务正在执行，请先停止或等待完成。"));
  return false;
}

function setWorkspaceStatus(message, isError = false) {
  const status = $("#workspace-status");
  status.textContent = message || "";
  status.classList.toggle("error", isError);
}

function invalidateWorkspaceSelection() {
  state.workspaceBrowseRequest += 1;
  state.workspaceBrowsePath = "";
  syncBusyControls();
  setWorkspaceStatus("输入路径后点击浏览，确认目标文件夹再切换。");
}

function renderWorkspaceLocations(selector, locations) {
  const container = $(selector);
  container.innerHTML = locations.length
    ? locations
        .map(
          (item) =>
            `<button type="button" class="workspace-location-btn" data-path="${escapeHtml(item.path)}" title="${escapeHtml(item.path)}">${icon("folder")}<span>${escapeHtml(item.name || item.path)}</span></button>`,
        )
        .join("")
    : '<div class="empty-hint">暂无记录</div>';
  container.querySelectorAll("button[data-path]").forEach((button) => {
    button.addEventListener("click", () =>
      browseWorkspace(button.getAttribute("data-path")),
    );
  });
}

async function browseWorkspace(path) {
  const request = ++state.workspaceBrowseRequest;
  const epoch = state.workspaceEpoch;
  state.workspaceBrowsePath = "";
  $("#workspace-path-input").value = path || "";
  $("#workspace-directory-list").innerHTML =
    '<div class="empty-hint">正在读取文件夹...</div>';
  $("#btn-workspace-parent").disabled = true;
  syncBusyControls();
  setWorkspaceStatus("");
  try {
    const data = await apiGet(
      `/api/workspaces/browse?path=${encodeURIComponent(path || "")}`,
    );
    if (
      request !== state.workspaceBrowseRequest ||
      epoch !== state.workspaceEpoch
    )
      return;
    state.workspaceBrowsePath = data.path;
    state.workspaceBrowseParent = data.parent || null;
    $("#workspace-path-input").value = data.path;
    $("#workspace-browse-path").textContent = data.path;
    $("#workspace-browse-path").title = data.path;
    $("#btn-workspace-parent").disabled = !data.parent;
    const container = $("#workspace-directory-list");
    container.innerHTML = data.directories.length
      ? data.directories
          .map(
            (item) =>
              `<button type="button" class="workspace-directory-btn" data-path="${escapeHtml(item.path)}">${icon("folder")}<span>${escapeHtml(item.name)}</span></button>`,
          )
          .join("")
      : '<div class="empty-hint">没有子文件夹。可以选择当前文件夹作为项目。</div>';
    container
      .querySelectorAll("button[data-path]")
      .forEach((button) =>
        button.addEventListener("click", () =>
          browseWorkspace(button.getAttribute("data-path")),
        ),
      );
    if (data.truncated)
      setWorkspaceStatus(
        "文件夹较多，仅显示部分结果；可直接输入目标的完整路径。",
      );
    else if (data.path === state.workspacePath)
      setWorkspaceStatus("这是当前工作区。选择其他项目文件夹后即可切换。");
    else if (state.busy)
      setWorkspaceStatus(
        "当前任务仍在执行，可以浏览文件夹，完成或停止任务后再切换。",
      );
  } catch (err) {
    if (
      request !== state.workspaceBrowseRequest ||
      epoch !== state.workspaceEpoch
    )
      return;
    $("#workspace-directory-list").innerHTML =
      '<div class="empty-hint">无法打开此文件夹，请检查路径和访问权限。</div>';
    setWorkspaceStatus(err.message, true);
  } finally {
    if (request === state.workspaceBrowseRequest) syncBusyControls();
  }
}

async function openWorkspaceModal() {
  openModal("modal-workspace", "#workspace-path-input");
  $("#workspace-current-path").textContent =
    state.workspacePath || "正在读取...";
  setWorkspaceStatus("");
  const epoch = state.workspaceEpoch;
  try {
    const catalog = await apiGet("/api/workspaces");
    if (epoch !== state.workspaceEpoch) return;
    state.workspacePath = catalog.current;
    $("#workspace-current-path").textContent = catalog.current;
    renderWorkspaceLocations("#workspace-recent-list", catalog.recent || []);
    renderWorkspaceLocations("#workspace-roots-list", catalog.roots || []);
    await browseWorkspace(catalog.current);
  } catch (err) {
    if (epoch === state.workspaceEpoch) setWorkspaceStatus(err.message, true);
  }
}

function applyWorkspaceState(snap) {
  if (!snap) return;
  if (
    snap.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    snap.workspace_generation < state.workspaceGeneration
  )
    return;
  const changed =
    snap.cwd !== state.workspacePath ||
    (snap.workspace_generation !== undefined &&
      snap.workspace_generation !== state.workspaceGeneration);
  if (!changed) return;
  state.workspaceEpoch += 1;
  state.workspaceBrowseRequest += 1;
  state.fileRequest += 1;
  state.previewRequest += 1;
  state.fileController?.abort();
  clearTimeout(state.fileSearchTimer);
  state.recoveryGeneration += 1;
  state.recoveryController?.abort();
  state.recoveryController = null;
  state.recovering = false;
  state.recoveryEvents = [];
  state.files = [];
  state.filesQuery = "";
  state.filesTruncated = false;
  invalidateFileTree();
  state.expandedDirectories.clear();
  state.skills = [];
  state.previewFilePath = "";
  state.completedAssistantPrefix = "";
  state.planPending = false;
  state.planCollapsed = false;
  state.lastPlanText = "";
  state.lastClearState = null;
  state.submitting = false;
  state.modelEditorGeneration += 1;
  state.modelFetchRequest += 1;
  [
    "#prompt-input",
    "#file-search-input",
    "#goal-quick-input",
    "#plan-task-input",
    "#plan-editor-textarea",
  ].forEach((selector) => {
    $(selector).value = "";
  });
  $$(".modal-backdrop:not(.hidden)").forEach((modal) =>
    closeModal(modal.id, false),
  );
  closeDrawers(false);
  hydrateSnapshot(snap);
  loadWorkspaceFiles();
  loadSkills();
  refreshTasks();
  resizePromptInput();
  focusPrompt();
}

async function switchWorkspace() {
  if (!requireIdle()) return;
  const typedPath = $("#workspace-path-input").value.trim();
  if (typedPath !== state.workspaceBrowsePath) {
    await browseWorkspace(typedPath);
    if (!state.workspaceBrowsePath) return;
  }
  if (state.workspaceBrowsePath === state.workspacePath) return;
  state.workspaceSwitching = true;
  syncBusyControls();
  setWorkspaceStatus("正在归档对话并切换工作区...");
  try {
    const result = await apiPost("/api/workspaces/switch", {
      path: state.workspaceBrowsePath,
    });
    applyWorkspaceState(result.state);
    closeModal("modal-workspace", false);
    focusPrompt();
  } catch (err) {
    setWorkspaceStatus(err.message, true);
  } finally {
    state.workspaceSwitching = false;
    syncBusyControls();
  }
}

function updateTopbar(snap) {
  if (
    snap.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    snap.workspace_generation < state.workspaceGeneration
  )
    return;
  if (
    state.workspacePath &&
    snap.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    snap.workspace_generation !== state.workspaceGeneration
  ) {
    applyWorkspaceState(snap);
    return;
  }
  if (snap.cwd) {
    state.workspacePath = snap.cwd;
    const workspace =
      snap.cwd
        .replace(/[\\/]+$/, "")
        .split(/[\\/]/)
        .pop() || snap.cwd;
    $("#meta-cwd").textContent = snap.cwd;
    $("#meta-cwd").title = snap.cwd;
    setOptionalText("#workspace-name", workspace);
    const pathLabel = setOptionalText("#workspace-path", snap.cwd);
    if (pathLabel) pathLabel.title = snap.cwd;
  }
  if (snap.workspace_generation !== undefined)
    state.workspaceGeneration = snap.workspace_generation;
  if (snap.git_branch !== undefined) {
    $("#meta-branch").textContent = snap.git_branch || "no-git";
  }
  state.activeModel = snap.active_model || null;
  const dot = $("#model-status-dot");
  const label = $("#active-model-label");
  if (state.activeModel) {
    dot.classList.remove("unconfigured");
    label.textContent = snap.model_id || state.activeModel;
    $("#btn-open-models").title =
      `${state.activeModel}${snap.model_id ? ` / ${snap.model_id}` : ""} · 切换模型`;
  } else {
    dot.classList.add("unconfigured");
    label.textContent = "连接你的模型";
    $("#btn-open-models").title = "尚未配置模型，点击添加模型或同步本地网关";
  }

  if (snap.approval_mode) {
    $("#select-approval-mode").value = snap.approval_mode;
  }
  if (snap.effort) {
    $("#select-effort").value = snap.effort;
  }
  syncComposerOptions();
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
  $("#stat-tokens").textContent =
    `↑ ${inTok.toLocaleString()} · ↓ ${outTok.toLocaleString()}`;
  $("#stat-cost").textContent = `$${cost}`;
}

/* Timeline Rendering */

function hideWelcomeIfNeeded() {
  const hero = $("#welcome-hero");
  if (hero) hero.classList.add("hidden");
}

function resetTimeline(showWelcome = true) {
  const timeline = $("#timeline");
  if (!state.welcomeHero) state.welcomeHero = $("#welcome-hero");
  timeline.replaceChildren();
  if (state.welcomeHero) {
    state.welcomeHero.classList.toggle("hidden", !showWelcome);
    timeline.appendChild(state.welcomeHero);
  }
  state.streamingAssistantEl = null;
  state.streamingAssistantText = "";
  state.streamingReasoningEl = null;
  state.streamingReasoningText = "";
  state.toolCardsById.clear();
  state.timelineRecords = [];
  state.completedAssistantPrefix = "";
  state.followTimeline = true;
}

function bindCardDisclosure(card) {
  const summary = card.querySelector(".card-summary");
  const details = card.querySelector(".card-details");
  summary.setAttribute("role", "button");
  summary.setAttribute("tabindex", "0");
  summary.setAttribute(
    "aria-expanded",
    String(!details.classList.contains("hidden")),
  );
  const toggle = () => {
    details.classList.toggle("hidden");
    summary.setAttribute(
      "aria-expanded",
      String(!details.classList.contains("hidden")),
    );
  };
  summary.addEventListener("click", toggle);
  summary.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      toggle();
    }
  });
}

function appendUserCard(text) {
  hideWelcomeIfNeeded();
  const card = document.createElement("div");
  card.className = "msg-card msg-user";
  card.innerHTML = `
    <div class="msg-header"><span>你</span><span>刚刚</span></div>
    <div class="msg-body">${escapeHtml(text)}</div>
  `;
  $("#timeline").appendChild(card);
  state.followTimeline = true;
  scrollTimelineBottom(true);
}

function ensureStreamingReasoningCard() {
  hideWelcomeIfNeeded();
  if (state.streamingReasoningEl) return state.streamingReasoningEl;
  const card = document.createElement("div");
  card.className = "thinking-card";
  card.innerHTML = `
    <div class="card-summary">
      <span>${icon("thinking")} 正在思考</span>
      <span class="think-toggle-hint">点击折叠/展开</span>
    </div>
    <div class="card-details"></div>
  `;
  bindCardDisclosure(card);
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
    <div class="msg-header"><span>Neow</span><span>生成中</span></div>
    <div class="msg-body"></div>
  `;
  $("#timeline").appendChild(card);
  state.streamingAssistantEl = card;
  state.streamingAssistantText = "";
  scrollTimelineBottom();
  return card;
}

function finalizeStreamingAssistantCard(fullContent, segmentOnly = false) {
  if (
    !segmentOnly &&
    fullContent &&
    state.completedAssistantPrefix &&
    fullContent.startsWith(state.completedAssistantPrefix)
  )
    fullContent = fullContent.slice(state.completedAssistantPrefix.length);
  if (fullContent && !state.streamingAssistantEl) {
    ensureStreamingAssistantCard();
  }
  if (state.streamingAssistantEl) {
    const body = state.streamingAssistantEl.querySelector(".msg-body");
    const text = fullContent || state.streamingAssistantText;
    body.innerHTML = renderMarkdownLite(text);
    const hdr = state.streamingAssistantEl.querySelector(
      ".msg-header span:last-child",
    );
    if (hdr) hdr.textContent = "完成";
  }
  state.streamingAssistantEl = null;
  state.streamingAssistantText = "";
  state.streamingReasoningEl = null;
  state.streamingReasoningText = "";
  if (!segmentOnly) state.completedAssistantPrefix = "";
  scrollTimelineBottom();
}

function appendToolStartedCard(ev) {
  hideWelcomeIfNeeded();
  // Flush current assistant card before tool card so chronological order stays exact
  if (state.streamingAssistantEl) {
    state.completedAssistantPrefix += state.streamingAssistantText;
    finalizeStreamingAssistantCard(state.streamingAssistantText, true);
  }
  const card = document.createElement("div");
  card.className = "tool-card";
  const argPreview = JSON.stringify(ev.args || {});
  card.innerHTML = `
    <div class="card-summary">
      <span>${icon("tool")} <strong>${escapeHtml(ev.name)}</strong> <code style="color:var(--text-dim)">${escapeHtml(argPreview.slice(0, 80))}</code></span>
      <span class="tool-status-badge">执行中...</span>
    </div>
    <div class="card-details hidden">参数:\n${escapeHtml(JSON.stringify(ev.args || {}, null, 2))}</div>
    <div class="tool-diff-slot"></div>
  `;
  bindCardDisclosure(card);
  $("#timeline").appendChild(card);
  if (ev.call_id) state.toolCardsById.set(ev.call_id, card);
  scrollTimelineBottom();
  return card;
}

function updateToolFinishedCard(ev) {
  let card = ev.call_id ? state.toolCardsById.get(ev.call_id) : null;
  if (!card) {
    card = appendToolStartedCard({
      call_id: ev.call_id,
      name: ev.name,
      args: {},
    });
  }
  if (ev.is_error || ev.denied) card.classList.add("error");
  const statusEl = card.querySelector(".tool-status-badge");
  if (statusEl) {
    statusEl.textContent = ev.denied
      ? "已拒绝"
      : ev.is_error
        ? "失败"
        : "✓ 完成";
    statusEl.style.color =
      ev.is_error || ev.denied ? "var(--danger)" : "var(--success)";
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
  if (level === "error") card.setAttribute("role", "alert");
  const borderColor =
    level === "error"
      ? "var(--danger)"
      : level === "warn"
        ? "var(--warn)"
        : "var(--accent)";
  card.style.borderLeft = `3px solid ${borderColor}`;
  card.innerHTML = `<div class="msg-body">${escapeHtml(message)}</div>`;
  $("#timeline").appendChild(card);
  scrollTimelineBottom();
}

/* Interactive Approval & ask_user Cards */

async function submitInteractive(box, path, payload) {
  if (box.dataset.submitting === "true") return;
  box.dataset.submitting = "true";
  box.querySelectorAll("button, input").forEach((el) => {
    el.disabled = true;
  });
  try {
    await apiPost(path, payload);
    box.remove();
  } catch (err) {
    let errorEl = box.querySelector(".interactive-error");
    if (!errorEl) {
      errorEl = document.createElement("p");
      errorEl.className = "interactive-error editor-status error";
      errorEl.setAttribute("role", "alert");
      box.appendChild(errorEl);
    }
    errorEl.textContent = err.message;
  } finally {
    box.dataset.submitting = "false";
    box.querySelectorAll("button, input").forEach((el) => {
      el.disabled = false;
    });
  }
}

function renderApprovalRequest(req) {
  const q = $("#interactive-queue");
  const existing = document.getElementById(`approval-${req.id}`);
  if (existing) return;

  const box = document.createElement("div");
  box.className = "approval-card";
  box.id = `approval-${req.id}`;
  box.innerHTML = `
    <div class="interactive-title">${icon("shield")} 执行前请确认 · ${escapeHtml(req.tool)}</div>
    <div style="font-size:12.5px;color:var(--text-dim)">${escapeHtml(req.reason || "需要确认是否执行该操作")}</div>
    <div class="interactive-params">${escapeHtml(JSON.stringify(req.params || {}, null, 2))}</div>
    <div class="interactive-actions">
      <button class="btn-primary btn-sm" data-decision="allow_once">允许一次 (Allow Once)</button>
      <button class="btn-secondary btn-sm" data-decision="allow_always">本会话始终允许 (${escapeHtml(req.tool)})</button>
      <button class="btn-danger btn-sm" data-decision="deny">拒绝 (Deny)</button>
    </div>
  `;
  box.querySelectorAll("button[data-decision]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const decision = btn.getAttribute("data-decision");
      submitInteractive(box, "/api/approval", { id: req.id, decision });
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
        `<button class="btn-secondary btn-sm ask-opt-btn" data-opt="${escapeHtml(opt)}">${escapeHtml(opt)}</button>`,
    )
    .join("");

  box.innerHTML = `
    <div class="interactive-title">${icon("message")} 需要你的想法</div>
    <div style="font-size:13.5px;margin-bottom:8px;">${escapeHtml(req.question)}</div>
    ${optsHtml ? `<div class="interactive-actions" style="margin-bottom:8px;">${optsHtml}</div>` : ""}
    <div style="display:flex;gap:8px;">
      <input type="text" class="ask-custom-input" aria-label="输入你的回答" placeholder="输入你的回答..." style="flex:1;min-width:0;padding:6px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--bg);color:var(--text);" />
      <button class="btn-primary btn-sm ask-submit-btn">提交回答</button>
    </div>
  `;

  const submitAnswer = (ans) =>
    submitInteractive(box, "/api/ask_user", { id: req.id, answer: ans });

  box.querySelectorAll(".ask-opt-btn").forEach((btn) => {
    btn.addEventListener("click", () =>
      submitAnswer(btn.getAttribute("data-opt")),
    );
  });
  box.querySelector(".ask-submit-btn").addEventListener("click", () => {
    const val = box.querySelector(".ask-custom-input").value.trim();
    if (val) submitAnswer(val);
  });
  box.querySelector(".ask-custom-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.isComposing && ev.keyCode !== 229) {
      ev.preventDefault();
      const answer = ev.target.value.trim();
      if (answer) submitAnswer(answer);
    }
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
  const progress = $("#todo-progress-bar").parentElement;
  if (progress) {
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-label", "任务完成进度");
    progress.setAttribute("aria-valuemin", "0");
    progress.setAttribute("aria-valuemax", "100");
    progress.setAttribute("aria-valuenow", String(pct));
  }
  setOptionalText("#todo-percent", `${pct}%`);

  if (!total) {
    listEl.innerHTML = `<div class="empty-hint">多步骤任务时 Agent 会自动拆解并更新进度</div>`;
    return;
  }
  listEl.innerHTML = state.todos
    .map((t) => {
      const symbol =
        t.status === "completed" ? "✓" : t.status === "in_progress" ? "◌" : "○";
      return `<div class="todo-item ${escapeHtml(t.status || "pending")}">
        <span aria-hidden="true">${symbol}</span>
        <span>${escapeHtml(t.content || "")}</span>
      </div>`;
    })
    .join("");
}

function renderGoalState(goal) {
  const active = Boolean(goal && goal.active);
  $("#goal-status-badge").textContent = active
    ? `运行中 R${goal.current_round}`
    : "待机";
  $("#goal-inactive-view").classList.toggle("hidden", active);
  $("#goal-active-view").classList.toggle("hidden", !active);
  if (active) {
    $("#goal-active-text").textContent = goal.goal || "";
    $("#goal-round-info").textContent =
      `自主巡航轮次: Round ${goal.current_round} / ${goal.max_rounds}`;
  }
}

function renderPlanBanner(plan) {
  const banner = $("#plan-banner");
  state.planPending = Boolean(plan && plan.pending && plan.text);
  if (plan && plan.pending && plan.text) {
    if (state.lastPlanText !== plan.text) {
      $("#plan-editor-textarea").value = plan.text;
      state.planCollapsed = false;
    }
    banner.classList.toggle("hidden", state.planCollapsed);
    state.lastPlanText = plan.text;
  } else {
    banner.classList.add("hidden");
    state.lastPlanText = "";
    state.planCollapsed = false;
  }
}

function closePlanEditor() {
  state.planCollapsed = true;
  $("#plan-banner").classList.add("hidden");
}

function openPlanEditor() {
  if (state.planPending) {
    state.planCollapsed = false;
    $("#plan-banner").classList.remove("hidden");
    closeDrawers(false);
    $("#plan-editor-textarea").focus();
    return;
  }
  openModal("modal-plan-prompt", "#plan-task-input");
}

async function refreshTasks() {
  const epoch = state.workspaceEpoch;
  try {
    const data = await apiGet("/api/tasks");
    if (epoch !== state.workspaceEpoch) return;
    const listEl = $("#tasks-list");
    const tasks = data.tasks || [];
    setOptionalText(
      "#task-count",
      String(tasks.filter((task) => task.status === "running").length),
    );
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
              : `<span style="font-size:11px;color:var(--text-muted)">exit=${escapeHtml(t.exit_code ?? "-")}</span>`
          }
        </div>
        <code style="font-size:11px;color:var(--text-dim)">${escapeHtml(t.command)}</code>
      </div>
    `,
      )
      .join("");
    listEl.querySelectorAll(".kill-task-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        runAction(async () => {
          await apiPost("/api/tasks/kill", {
            task_id: btn.getAttribute("data-id"),
          });
          await refreshTasks();
        }, btn),
      );
    });
  } catch (e) {
    if (epoch !== state.workspaceEpoch) return;
    $("#tasks-list").innerHTML =
      `<div class="empty-hint">暂时无法加载后台进程，请点击刷新重试。</div>`;
  }
}

/* Workspace Files & Skills */

function invalidateFileTree() {
  state.fileTreeVersion += 1;
  state.fileDirectories.clear();
}

async function loadFileDirectory(path = "", append = false) {
  const previous = state.fileDirectories.get(path);
  if (previous?.loading || (append && previous?.nextOffset == null)) return;
  const directory = {
    entries: append ? previous.entries : [],
    nextOffset: append ? previous.nextOffset : null,
    loading: true,
    error: false,
  };
  const epoch = state.workspaceEpoch;
  const version = state.fileTreeVersion;
  const offset = append ? directory.nextOffset : 0;
  state.fileDirectories.set(path, directory);
  renderFilesList();
  try {
    const data = await apiGet(
      `/api/files/tree?path=${encodeURIComponent(path)}&offset=${offset}`,
    );
    if (
      epoch !== state.workspaceEpoch ||
      version !== state.fileTreeVersion ||
      state.fileDirectories.get(path) !== directory
    )
      return;
    if (data.workspace_generation !== state.workspaceGeneration)
      throw new Error("工作区已切换，请稍后重试");
    directory.entries.push(...(data.entries || []));
    directory.nextOffset = data.next_offset ?? null;
  } catch (error) {
    if (epoch !== state.workspaceEpoch || version !== state.fileTreeVersion)
      return;
    directory.error = true;
  } finally {
    if (
      epoch === state.workspaceEpoch &&
      version === state.fileTreeVersion &&
      state.fileDirectories.get(path) === directory
    ) {
      directory.loading = false;
      renderFilesList();
    }
  }
}

async function loadWorkspaceFiles() {
  const request = ++state.fileRequest;
  const epoch = state.workspaceEpoch;
  const query = $("#file-search-input").value.trim();
  state.fileController?.abort();
  if (!query) {
    state.filesQuery = "";
    const expanded = [...state.expandedDirectories];
    invalidateFileTree();
    await loadFileDirectory();
    if (request !== state.fileRequest || epoch !== state.workspaceEpoch) return;
    await Promise.all(expanded.map((path) => loadFileDirectory(path)));
    return;
  }
  const controller = new AbortController();
  state.fileController = controller;
  try {
    const data = await apiGet(`/api/files?q=${encodeURIComponent(query)}`, {
      signal: controller.signal,
    });
    if (request !== state.fileRequest || epoch !== state.workspaceEpoch) return;
    state.files = data.files || [];
    state.filesQuery = query;
    state.filesTruncated = Boolean(data.truncated);
    setOptionalText(
      "#file-count",
      `${state.files.length}${data.truncated ? "+" : ""}`,
    );
    $("#file-count").title = query ? "匹配当前搜索的文件数" : "已载入文件数";
    renderFilesList();
  } catch (e) {
    if (
      e.name === "AbortError" ||
      request !== state.fileRequest ||
      epoch !== state.workspaceEpoch
    )
      return;
    $("#file-tree-list").innerHTML =
      `<div class="empty-hint">工作区暂时无法连接，稍后重试。</div>`;
  }
}

function renderFileRow(file) {
  const name = file.name || file.path.split("/").pop();
  return `<div class="file-item" data-path="${escapeHtml(file.path)}">
    <button type="button" class="file-open" title="预览 ${escapeHtml(file.path)}" aria-label="预览 ${escapeHtml(file.path)}">
      ${icon("file")}<span class="file-path">${escapeHtml(name)}</span>
    </button>
    <button type="button" class="file-ref-btn" data-ref="${escapeHtml(file.path)}" title="引用 ${escapeHtml(file.path)}" aria-label="引用 ${escapeHtml(file.path)}">@</button>
  </div>`;
}

function renderFileFolder(entry, children, open) {
  return `<details class="file-folder" data-directory="${escapeHtml(entry.path)}"${open ? " open" : ""}>
    <summary class="folder-row" title="${escapeHtml(entry.path)}" aria-label="文件夹 ${escapeHtml(entry.path)}">
      <svg class="icon folder-chevron" aria-hidden="true"><use href="#i-chevron" /></svg>
      ${icon("folder")}<span class="folder-name">${escapeHtml(entry.name)}</span>
    </summary>
    <div class="folder-children">${children}</div>
  </details>`;
}

function renderFileDirectory(path = "") {
  const directory = state.fileDirectories.get(path);
  if (!directory) return '<div class="file-tree-status">展开后加载</div>';
  const rows = directory.entries
    .map((entry) =>
      entry.kind === "directory"
        ? renderFileFolder(
            entry,
            state.expandedDirectories.has(entry.path)
              ? renderFileDirectory(entry.path)
              : "",
            state.expandedDirectories.has(entry.path),
          )
        : renderFileRow(entry),
    )
    .join("");
  let status = "";
  if (directory.loading)
    status = '<div class="file-tree-status" role="status">正在读取...</div>';
  else if (directory.error)
    status = `<button type="button" class="file-tree-more" data-load-directory="${escapeHtml(path)}" data-append="${directory.entries.length > 0}">加载失败，点击重试</button>`;
  else if (directory.nextOffset != null)
    status = `<button type="button" class="file-tree-more" data-load-directory="${escapeHtml(path)}" data-append="true">加载更多</button>`;
  else if (!directory.entries.length)
    status = '<div class="file-tree-status">文件夹为空</div>';
  return rows + status;
}

function renderFileSearch(files) {
  const root = { entries: new Map() };
  for (const file of files) {
    const parts = file.path.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i += 1) {
      const path = parts.slice(0, i + 1).join("/");
      if (!current.entries.has(parts[i]))
        current.entries.set(parts[i], {
          ...file,
          path,
          name: parts[i],
          kind: i === parts.length - 1 ? "file" : "directory",
          entries: new Map(),
        });
      current = current.entries.get(parts[i]);
    }
  }
  const render = (node) =>
    [...node.entries.values()]
      .sort(
        (a, b) =>
          (a.kind !== "directory") - (b.kind !== "directory") ||
          a.name.localeCompare(b.name, "zh-CN", { numeric: true }),
      )
      .map((entry) =>
        entry.kind === "directory"
          ? renderFileFolder(entry, render(entry), true)
          : renderFileRow(entry),
      )
      .join("");
  return render(root);
}

function renderFilesList() {
  const query = $("#file-search-input").value.trim();
  const container = $("#file-tree-list");
  const focus = container.contains(document.activeElement)
    ? document.activeElement
    : null;
  const focusKey = focus?.classList.contains("file-ref-btn")
    ? ["data-ref", focus.getAttribute("data-ref")]
    : focus?.classList.contains("file-open")
      ? ["data-file", focus.closest(".file-item").getAttribute("data-path")]
      : focus?.hasAttribute("data-load-directory")
        ? ["data-load-directory", focus.getAttribute("data-load-directory")]
        : focus?.closest(".file-folder")
          ? [
              "data-directory",
              focus.closest(".file-folder").getAttribute("data-directory"),
            ]
          : null;
  const scrollTop = container.scrollTop;
  if (query) {
    const current = state.filesQuery === query;
    container.innerHTML = current
      ? state.files.length
        ? renderFileSearch(state.files)
        : '<div class="file-tree-status">无匹配文件</div>'
      : '<div class="file-tree-status" role="status">正在搜索...</div>';
    if (current && state.filesTruncated)
      container.insertAdjacentHTML(
        "beforeend",
        `<div class="empty-hint file-list-more">显示前 ${state.files.length} 个匹配文件，请缩小搜索范围</div>`,
      );
    setOptionalText(
      "#file-count",
      current ? `${state.files.length}${state.filesTruncated ? "+" : ""}` : "…",
    );
    $("#file-count").title = "匹配当前搜索的文件数";
  } else {
    container.innerHTML = renderFileDirectory();
    const root = state.fileDirectories.get("");
    setOptionalText(
      "#file-count",
      root && !root.loading
        ? `${root.entries.length}${root.nextOffset != null ? "+" : ""}`
        : "…",
    );
    $("#file-count").title = "根目录中的文件与文件夹数量";
  }
  container.querySelectorAll(".file-folder").forEach((folder) => {
    folder.addEventListener("toggle", () => {
      if (!folder.isConnected || $("#file-search-input").value.trim()) return;
      const path = folder.getAttribute("data-directory");
      if (folder.open) {
        state.expandedDirectories.add(path);
        if (!state.fileDirectories.has(path)) loadFileDirectory(path);
        else if (!folder.querySelector(".folder-children").innerHTML)
          renderFilesList();
      } else state.expandedDirectories.delete(path);
    });
  });
  container.querySelectorAll("[data-load-directory]").forEach((button) => {
    button.addEventListener("click", () =>
      loadFileDirectory(
        button.getAttribute("data-load-directory"),
        button.getAttribute("data-append") === "true",
      ),
    );
  });
  container.querySelectorAll(".file-open").forEach((button) => {
    button.addEventListener("click", () =>
      openFilePreview(button.closest(".file-item").getAttribute("data-path")),
    );
  });

  container.querySelectorAll(".file-ref-btn").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      insertAtReference(btn.getAttribute("data-ref"));
    });
  });
  container.scrollTop = scrollTop;
  if (focusKey) {
    const [kind, path] = focusKey;
    const candidates =
      kind === "data-file"
        ? container.querySelectorAll(".file-open")
        : kind === "data-directory"
          ? container.querySelectorAll(".file-folder > summary")
          : container.querySelectorAll(`[${kind}]`);
    const target = [...candidates].find((node) =>
      kind === "data-file"
        ? node.closest(".file-item").getAttribute("data-path") === path
        : kind === "data-directory"
          ? node.closest(".file-folder").getAttribute(kind) === path
          : node.getAttribute(kind) === path,
    );
    target?.focus({ preventScroll: true });
  }
}

function insertAtReference(relPath) {
  const input = $("#prompt-input");
  const prefix = input.value && !input.value.endsWith(" ") ? " " : "";
  const reference = /\s/.test(relPath) ? `@"${relPath}"` : `@${relPath}`;
  input.value = `${input.value}${prefix}${reference} `;
  focusPrompt();
}

async function openFilePreview(relPath) {
  const request = ++state.previewRequest;
  const epoch = state.workspaceEpoch;
  try {
    const data = await apiGet(`/api/file?path=${encodeURIComponent(relPath)}`);
    if (request !== state.previewRequest || epoch !== state.workspaceEpoch)
      return;
    state.previewFilePath = data.path;
    $("#preview-modal-title").textContent = data.path;
    $("#preview-modal-content").textContent = data.content || "";
    $("#preview-truncation-notice").classList.toggle("hidden", !data.truncated);
    $("#btn-insert-file-ref").classList.remove("hidden");
    openModal("modal-preview");
  } catch (err) {
    if (request !== state.previewRequest || epoch !== state.workspaceEpoch)
      return;
    showError(err);
  }
}

async function loadSkills() {
  const epoch = state.workspaceEpoch;
  try {
    const data = await apiGet("/api/skills");
    if (epoch !== state.workspaceEpoch) return;
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
          <div style="font-weight:600;color:var(--text)">${icon("skill")} ${escapeHtml(s.name)}</div>
          <div style="font-size:11px;color:var(--text-muted)">${escapeHtml(s.description || "")}</div>
        </div>
        <button class="btn-xs ${s.active ? "btn-primary" : "btn-secondary"} toggle-skill-btn" data-name="${escapeHtml(s.name)}">
          ${s.active ? "已启用" : "启用"}
        </button>
      </div>
    `,
      )
      .join("");
    el.querySelectorAll(".toggle-skill-btn").forEach((btn) => {
      btn.addEventListener("click", () =>
        runAction(async () => {
          await apiPost("/api/skills/toggle", {
            name: btn.getAttribute("data-name"),
          });
          await loadSkills();
        }, btn),
      );
    });
    syncBusyControls();
  } catch (e) {
    if (epoch !== state.workspaceEpoch) return;
    $("#skills-list").innerHTML =
      `<div class="empty-hint">暂时无法加载技能，稍后重试。</div>`;
  }
}

/* Model & Gateway Studio Modal */

async function openModelsModal() {
  openModal("modal-models", "#model-filter-input");
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
    const previousPreset = presetSel.value;
    presetSel.innerHTML = state.presets
      .map(
        (p) =>
          `<option value="${escapeHtml(p.id)}">${escapeHtml(p.label)}</option>`,
      )
      .join("");
    if (state.presets.some((preset) => preset.id === previousPreset))
      presetSel.value = previousPreset;

    renderConfiguredModelsList();
    syncBusyControls();
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
      (m.provider || "").toLowerCase().includes(q),
  );

  if (!filtered.length) {
    listEl.innerHTML = `<div class="empty-hint">无匹配模型，可在右侧选择预设添加或点击上方「网关/Magpie 同步」</div>`;
    return;
  }

  listEl.innerHTML = filtered
    .map(
      (m) => `
    <div class="model-row-item ${m.active ? "active" : ""}">
      <div class="model-row-info" data-select="${escapeHtml(m.name)}" role="button" tabindex="0" aria-label="切换到 ${escapeHtml(m.name)}">
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
  `,
    )
    .join("");

  listEl
    .querySelectorAll(".switch-model-btn, .model-row-info")
    .forEach((el) => {
      const select = async () => {
        if (!requireIdle()) return;
        const name =
          el.getAttribute("data-name") || el.getAttribute("data-select");
        if (!name || el.dataset.submitting === "true") return;
        el.dataset.submitting = "true";
        if (el.tagName === "BUTTON") el.disabled = true;
        setEditorStatus(`正在连接并切换至 ${name} ...`, false);
        try {
          const res = await apiPost("/api/models/select", { name });
          setEditorStatus(`✓ 已切换至 ${res.active_model}`, false);
          await refreshModelsCatalog();
          const snap = await apiGet("/api/state");
          updateTopbar(snap);
        } catch (err) {
          setEditorStatus(err.message, true);
        } finally {
          el.dataset.submitting = "false";
          if (el.tagName === "BUTTON") el.disabled = false;
          syncBusyControls();
        }
      };
      el.addEventListener("click", select);
      el.addEventListener("keydown", (ev) => {
        if (el.tagName !== "BUTTON" && (ev.key === "Enter" || ev.key === " ")) {
          ev.preventDefault();
          select();
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
    btn.addEventListener("click", () =>
      runAction(
        async () => {
          if (!requireIdle()) return;
          const name = btn.getAttribute("data-name");
          try {
            await apiPost("/api/models/delete", { name });
            setEditorStatus(`已删除模型: ${name}`, false);
            await refreshModelsCatalog();
          } catch (err) {
            setEditorStatus(err.message, true);
          }
        },
        btn,
        (err) => setEditorStatus(err.message, true),
      ),
    );
  });
  syncBusyControls();
}

function invalidateModelEditor() {
  state.modelEditorGeneration += 1;
  $("#editor-fetched-models").classList.add("hidden");
  $("#editor-fetched-models").innerHTML = "";
}

function populateEditorForEdit(m) {
  invalidateModelEditor();
  state.editingModelName = m.name;
  $("#editor-form-title").textContent = `编辑模型 · ${m.name}`;
  $("#editor-name").value = m.name;
  $("#editor-name").disabled = true;
  $("#editor-provider").value = m.provider || "openai-compatible";
  $("#editor-url").value = m.base_url || "";
  $("#editor-model-id").value = m.model || "";
  $("#editor-api-key").value = "";
  $("#editor-api-key").placeholder = m.has_key
    ? "保持已保存的 Key (留空不修改)"
    : "粘贴 API Key";
  $("#editor-key-env").value = m.api_key_env || "";
  $("#editor-preset-select").value = "custom";
  $("#editor-fetched-models").classList.add("hidden");
  $("#editor-fetched-models").innerHTML = "";
  setEditorStatus(`正在编辑「${m.name}」`, false);
}

function resetModelEditor() {
  invalidateModelEditor();
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

function bindEditorAction(selector, action) {
  $(selector).addEventListener("click", (ev) =>
    runAction(action, ev.currentTarget, (err) => {
      setEditorStatus(err.message, true);
    }),
  );
}

function modelEditorFingerprint() {
  return JSON.stringify([
    state.editingModelName,
    ...[
      "#editor-name",
      "#editor-provider",
      "#editor-url",
      "#editor-model-id",
      "#editor-api-key",
      "#editor-key-env",
    ].map((selector) => $(selector)?.value || ""),
  ]);
}

async function fetchRemoteModels() {
  const request = ++state.modelFetchRequest;
  const generation = state.modelEditorGeneration;
  const fingerprint = modelEditorFingerprint();
  const payload = {
    name: state.editingModelName,
    is_edit: Boolean(state.editingModelName),
    base_url: $("#editor-url").value.trim(),
    api_key: $("#editor-api-key").value.trim(),
    api_key_env: $("#editor-key-env").value.trim(),
  };
  setEditorStatus("正在请求 /models 拉取可用模型列表...", false);
  try {
    const res = await apiPost("/api/models/fetch", payload);
    if (
      generation !== state.modelEditorGeneration ||
      request !== state.modelFetchRequest ||
      fingerprint !== modelEditorFingerprint()
    )
      return;
    const models = res.models || [];
    const sel = $("#editor-fetched-models");
    sel.innerHTML = models
      .map(
        (mid) =>
          `<option value="${escapeHtml(mid)}">选用远端模型: ${escapeHtml(mid)}</option>`,
      )
      .join("");
    sel.classList.remove("hidden");
    if (models.length) $("#editor-model-id").value = models[0];
    setEditorStatus(
      `✓ 成功拉取 ${models.length} 个模型，可在下拉框中切换`,
      false,
    );
  } catch (err) {
    if (
      generation !== state.modelEditorGeneration ||
      request !== state.modelFetchRequest ||
      fingerprint !== modelEditorFingerprint()
    )
      return;
    setEditorStatus(err.message, true);
  }
}

/* Prompt Submission & Slash Commands */

function requireModel() {
  if (state.activeModel) return true;
  openModelsModal();
  setEditorStatus(
    "先连接一个模型，再开始你的开发任务。输入的内容会为你保留。",
    false,
  );
  return false;
}

function handlePromptKeydown(ev) {
  if (
    ev.key === "Enter" &&
    !ev.shiftKey &&
    !ev.isComposing &&
    ev.keyCode !== 229
  ) {
    ev.preventDefault();
    handleSendPrompt();
  }
}

async function handleSendPrompt() {
  const input = $("#prompt-input");
  const draft = input.value || "";
  const raw = draft.trim();
  if (!raw || state.busy || state.submitting) return;

  if (raw === "/model" || raw === "/models" || raw === "/model add") {
    input.value = "";
    resizePromptInput();
    openModelsModal();
    return;
  }
  if (raw === "/plan") {
    openPlanEditor();
    return;
  }
  if (raw === "/goal") {
    setDrawer("inspector", true);
    $("#goal-quick-input").focus();
    return;
  }
  const localCommand = raw === "/clear" || raw === "/compact";
  if (!localCommand && !requireModel()) return;
  const isPlan = raw.startsWith("/plan ");
  const isGoal = raw.startsWith("/goal ");
  const isChat = !localCommand && !isPlan && !isGoal;
  state.submitting = true;
  syncBusyControls();
  try {
    if (isChat) {
      setBusyState(true);
      await apiPost("/api/chat", { prompt: raw });
    } else if (isGoal) {
      await apiPost("/api/goal", {
        action: "start",
        goal: raw.slice(6).trim(),
      });
    } else if (isPlan) {
      appendNoticeCard(`正在生成实施计划 · ${raw.slice(6).trim()}`, "info");
      await apiPost("/api/plan", {
        action: "generate",
        task: raw.slice(6).trim(),
      });
    } else {
      const result = await apiPost(
        raw === "/clear" ? "/api/clear" : "/api/compact",
      );
      if (raw === "/clear" && result.state) applyClearedState(result.state);
    }
    // A slow request must not erase the next draft typed while it was pending.
    if (input.value === draft) input.value = "";
    resizePromptInput();
  } catch (err) {
    if (isChat) setBusyState(false);
    showError(err);
    if (/model|api key|配置/i.test(err.message)) {
      openModelsModal();
    }
  } finally {
    state.submitting = false;
    syncBusyControls();
  }
}

function applyClearedState(snap) {
  if (
    snap &&
    snap.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    snap.workspace_generation < state.workspaceGeneration
  )
    return;
  if (snap && state.lastClearState === JSON.stringify(snap)) return;
  if (snap) state.lastClearState = JSON.stringify(snap);
  state.lastPlanText = "";
  state.planPending = false;
  state.submitting = false;
  state.previewFilePath = "";
  if (snap) hydrateSnapshot(snap);
  else {
    resetTimeline();
    $("#interactive-queue").innerHTML = "";
    renderTodos([]);
    renderPlanBanner(null);
    renderGoalState(null);
    setBusyState(false);
  }
  loadSkills();
}

/* SSE Event Stream */

function timelineRecordForEvent(ev) {
  switch (ev.type) {
    case "user_message":
      return { kind: "user", text: ev.text || "" };
    case "reasoning_end":
      return {
        kind: "reasoning",
        text: ev.text || "",
        duration: ev.duration || 0,
      };
    case "tool_finished":
      return { kind: "tool", ...ev };
    case "notice":
      return {
        kind: "notice",
        message: ev.message || "",
        level: ev.level || "info",
      };
    case "turn_completed":
      return ev.content ? { kind: "assistant", text: ev.content } : null;
    case "turn_failed":
      return { kind: "error", message: ev.message || "" };
    default:
      return null;
  }
}

function timelineRecordKey(record) {
  if (record.kind === "tool")
    return JSON.stringify([
      record.kind,
      record.call_id || "",
      record.name,
      record.result,
    ]);
  if (record.kind === "notice")
    return JSON.stringify([
      record.kind,
      record.message,
      record.level || "info",
    ]);
  if (record.kind === "error")
    return JSON.stringify([record.kind, record.message]);
  return JSON.stringify([record.kind, record.text || ""]);
}

function eventsAfterSnapshot(snap, events, baseline = []) {
  const generation = snap.workspace_generation;
  let workspaceBoundary = -1;
  events.forEach((event, index) => {
    if (
      event.type === "workspace_changed" &&
      event.state &&
      generation !== undefined &&
      event.state.workspace_generation <= generation
    )
      workspaceBoundary = index;
  });
  if (workspaceBoundary >= 0) {
    events = events.slice(workspaceBoundary + 1);
    baseline = [];
  }
  if (generation !== undefined)
    events = events.filter(
      (event) =>
        event.workspace_generation === undefined ||
        event.workspace_generation >= generation,
    );
  const records = snap.timeline || [];
  let shared = 0;
  while (
    shared < records.length &&
    shared < baseline.length &&
    timelineRecordKey(records[shared]) === timelineRecordKey(baseline[shared])
  )
    shared += 1;
  const fresh = records.slice(shared);
  const persisted = events
    .map((event, index) => ({
      event,
      index,
      record: timelineRecordForEvent(event),
    }))
    .filter((item) => item.record);
  let overlap = Math.min(fresh.length, persisted.length);
  // The server has no sequence cursor; match the ordered persisted suffix, never arbitrary equal text.
  while (overlap > 0) {
    if (
      fresh
        .slice(-overlap)
        .every(
          (record, index) =>
            timelineRecordKey(record) ===
            timelineRecordKey(persisted[index].record),
        )
    )
      break;
    overlap -= 1;
  }
  if (!overlap) return events;
  const cutoff = persisted[overlap - 1].index;
  const prefix = events
    .slice(0, cutoff + 1)
    .filter((event) =>
      [
        "approval_request",
        "approval_resolved",
        "ask_user_request",
        "ask_user_resolved",
        "turn_completed",
        "turn_failed",
      ].includes(event.type),
    );
  return [
    ...prefix.map((event) =>
      event.type.startsWith("turn_")
        ? { ...event, snapshotApplied: true, busy: Boolean(snap.busy) }
        : event,
    ),
    ...events.slice(cutoff + 1),
  ];
}

function reconcilePendingRequests(snap) {
  const approvals = snap.pending_approvals || [];
  const questions = snap.pending_questions || [];
  const ids = new Set([
    ...approvals.map((req) => `approval-${req.id}`),
    ...questions.map((req) => `ask-${req.id}`),
  ]);
  Array.from($("#interactive-queue").children).forEach((node) => {
    if (!ids.has(node.id)) node.remove();
  });
  approvals.forEach(renderApprovalRequest);
  questions.forEach(renderAskUserRequest);
}

function hydrateSnapshot(snap) {
  if (
    snap.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    snap.workspace_generation < state.workspaceGeneration
  )
    return;
  if (
    state.workspacePath &&
    ((snap.cwd && snap.cwd !== state.workspacePath) ||
      (snap.workspace_generation !== undefined &&
        state.workspaceGeneration !== null &&
        snap.workspace_generation !== state.workspaceGeneration))
  ) {
    state.workspacePath = snap.cwd || state.workspacePath;
    state.workspaceGeneration =
      snap.workspace_generation ?? state.workspaceGeneration;
  }
  const timeline = $("#timeline");
  const previousScroll = timeline.scrollTop;
  const follow = state.followTimeline;
  resetTimeline();
  (snap.timeline || []).forEach((item) => {
    if (item.kind === "user") appendUserCard(item.text);
    else if (item.kind === "assistant")
      finalizeStreamingAssistantCard(item.text);
    else if (item.kind === "tool") updateToolFinishedCard(item);
    else if (item.kind === "reasoning") {
      const card = ensureStreamingReasoningCard();
      card.querySelector(".card-details").textContent = item.text || "";
      card.querySelector(".card-details").classList.add("hidden");
      card
        .querySelector(".card-summary")
        .setAttribute("aria-expanded", "false");
      card.querySelector(".card-summary span:first-child").textContent =
        `思考完成 · ${item.duration || 0}s`;
      state.streamingReasoningEl = null;
    } else if (item.kind === "notice" || item.kind === "error") {
      appendNoticeCard(
        item.message,
        item.kind === "error" ? "error" : item.level,
      );
    }
  });
  state.timelineRecords = (snap.timeline || []).slice();
  updateTopbar(snap);
  reconcilePendingRequests(snap);
  state.followTimeline = follow;
  if (follow) scrollTimelineBottom(true);
  else timeline.scrollTop = previousScroll;
}

async function recoverSession(es) {
  const generation = ++state.recoveryGeneration;
  const controller = new AbortController();
  state.recoveryController?.abort();
  state.recoveryController = controller;
  state.recovering = true;
  state.recoveryEvents = [];
  const baseline = state.timelineRecords.slice();
  setConnectionState("connecting");
  setOptionalText("#connection-label", "正在恢复工作区");
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const snap = await apiGet("/api/state", { signal: controller.signal });
    if (generation !== state.recoveryGeneration || state.eventSource !== es)
      return;
    const switched =
      snap.cwd !== state.workspacePath ||
      (snap.workspace_generation !== undefined &&
        snap.workspace_generation !== state.workspaceGeneration);
    const events = eventsAfterSnapshot(
      snap,
      state.recoveryEvents,
      switched ? [] : baseline,
    );
    if (switched) applyWorkspaceState(snap);
    else hydrateSnapshot(snap);
    state.recoveryEvents = [];
    state.recovering = false;
    state.needsSnapshot = false;
    events.forEach(handleServerEvent);
    setConnectionState("connected");
  } catch (err) {
    if (generation !== state.recoveryGeneration || state.eventSource !== es)
      return;
    const events = state.recoveryEvents;
    state.recoveryEvents = [];
    state.recovering = false;
    events.forEach(handleServerEvent);
    state.needsSnapshot = true;
    setBusyState(false);
    setOptionalText("#session-status", "等待状态同步");
    setConnectionState("disconnected");
    state.reconnectTimer = setTimeout(() => recoverSession(es), 2000);
  } finally {
    clearTimeout(timeout);
    if (generation === state.recoveryGeneration)
      state.recoveryController = null;
  }
}

function connectSSE() {
  if (state.eventSource) state.eventSource.close();
  state.recoveryGeneration += 1;
  state.recoveryController?.abort();
  state.recovering = false;
  state.recoveryEvents = [];
  clearTimeout(state.reconnectTimer);
  setConnectionState("connecting");
  const es = new EventSource("/api/events");
  state.eventSource = es;
  es.onopen = () => {
    if (state.needsSnapshot) recoverSession(es);
    else setConnectionState("connected");
  };

  es.onmessage = (e) => {
    try {
      const ev = JSON.parse(e.data);
      if (state.recovering) {
        state.recoveryEvents.push(ev);
        if (state.recoveryEvents.length >= 512)
          state.recoveryController?.abort();
      } else handleServerEvent(ev);
    } catch (err) {
      console.warn("Neow could not process an event:", err);
    }
  };

  es.onerror = () => {
    es.close();
    state.recoveryGeneration += 1;
    state.recoveryController?.abort();
    state.recovering = false;
    state.recoveryEvents = [];
    state.needsSnapshot = true;
    setConnectionState("disconnected");
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = setTimeout(connectSSE, 2000);
  };
}

function handleServerEvent(ev) {
  if (
    ev.workspace_generation !== undefined &&
    state.workspaceGeneration !== null &&
    ev.workspace_generation < state.workspaceGeneration
  )
    return;
  if (ev.type === "workspace_changed") {
    applyWorkspaceState(ev.state);
    return;
  }
  if (ev.snapshotApplied) {
    if (ev.usage) updateUsageStats(ev.usage);
    setBusyState(Boolean(ev.busy));
    return;
  }
  const record = timelineRecordForEvent(ev);
  if (record) state.timelineRecords.push(record);
  switch (ev.type) {
    case "connected":
      setConnectionState("connected");
      break;
    case "user_message":
      state.lastClearState = null;
      state.completedAssistantPrefix = "";
      appendUserCard(ev.text);
      setBusyState(true);
      break;
    case "reasoning_started":
      ensureStreamingReasoningCard();
      break;
    case "reasoning_delta": {
      const card = ensureStreamingReasoningCard();
      state.streamingReasoningText += ev.text || "";
      card.querySelector(".card-details").textContent =
        state.streamingReasoningText;
      scrollTimelineBottom();
      break;
    }
    case "reasoning_end": {
      if (state.streamingReasoningEl) {
        const hdr = state.streamingReasoningEl.querySelector(
          ".card-summary span:first-child",
        );
        if (hdr) hdr.textContent = `思考完成 · ${ev.duration || 0}s`;
        state.streamingReasoningEl
          .querySelector(".card-details")
          .classList.add("hidden");
        state.streamingReasoningEl
          .querySelector(".card-summary")
          .setAttribute("aria-expanded", "false");
      }
      state.streamingReasoningEl = null;
      break;
    }
    case "content_delta": {
      const card = ensureStreamingAssistantCard();
      state.streamingAssistantText += ev.text || "";
      card.querySelector(".msg-body").innerHTML = renderMarkdownLite(
        state.streamingAssistantText,
      );
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
    case "approval_resolved":
      document.getElementById(`approval-${ev.id}`)?.remove();
      break;
    case "ask_user_resolved":
      document.getElementById(`ask-${ev.id}`)?.remove();
      break;
    case "notice":
      appendNoticeCard(ev.message, ev.level);
      break;
    case "turn_completed":
      finalizeStreamingAssistantCard(ev.content);
      if (ev.usage) updateUsageStats(ev.usage);
      setBusyState(Boolean(ev.busy));
      break;
    case "turn_failed":
      finalizeStreamingAssistantCard("");
      appendNoticeCard(ev.message || "对话回合失败", "error");
      setBusyState(Boolean(ev.busy));
      break;
    case "model_switched":
      apiGet("/api/state").then(updateTopbar).catch(showError);
      break;
    case "state_updated":
      if (ev.state) updateTopbar(ev.state);
      break;
    case "cleared":
      applyClearedState(ev.state);
      break;
  }
}

/* Hydrate Initial State & Bind UI Events */

async function initApp() {
  state.welcomeHero = $("#welcome-hero");
  try {
    const savedTheme = localStorage.getItem("neow-theme");
    document.documentElement.setAttribute(
      "data-theme",
      savedTheme === "dark" ? "dark" : "light",
    );
  } catch (err) {
    // Restricted storage should not prevent the studio from starting.
  }
  $("#btn-theme-toggle").setAttribute(
    "aria-label",
    document.documentElement.getAttribute("data-theme") === "dark"
      ? "切换到浅色主题"
      : "切换到深色主题",
  );
  $("#btn-theme-toggle").addEventListener("click", () => {
    const html = document.documentElement;
    const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", next);
    $("#btn-theme-toggle").setAttribute(
      "aria-label",
      next === "dark" ? "切换到浅色主题" : "切换到深色主题",
    );
    try {
      localStorage.setItem("neow-theme", next);
    } catch (err) {
      /* Storage is optional. */
    }
  });

  ["sidebar", "inspector"].forEach((name) => {
    $(`#btn-toggle-${name}`)?.addEventListener("click", () => {
      setDrawer(name, !$(".app-shell").classList.contains(`${name}-open`));
    });
  });
  $("#panel-backdrop")?.addEventListener("click", () => closeDrawers());
  $("#btn-close-inspector").addEventListener("click", () =>
    setDrawer("inspector", false),
  );
  $("#btn-focus-prompt")?.addEventListener("click", focusPrompt);
  $("#btn-show-conversation").addEventListener("click", () => {
    setLibraryOpen(false);
    focusPrompt();
  });
  $("#btn-toggle-library").addEventListener("click", () => {
    setLibraryOpen($("#workspace-library").classList.contains("hidden"));
  });
  $$("[data-popover]").forEach((popover) => {
    popover.addEventListener("click", (ev) => {
      if (ev.target.closest("summary")) closePopovers(false, popover);
    });
  });
  // Close action menus before a modal captures its return-focus target.
  $("#workflow-menu").addEventListener(
    "click",
    (ev) => {
      if (ev.target.closest("button")) closePopovers(true);
    },
    true,
  );
  document.addEventListener("click", (ev) => {
    closePopovers(false, ev.target.closest("[data-popover]"));
  });
  window.addEventListener("resize", () => {
    syncDrawerAccessibility();
    resizePromptInput();
  });
  syncDrawerAccessibility();

  $$(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () =>
      selectSidebarTab(btn.getAttribute("data-tab")),
    );
    btn.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
        ev.preventDefault();
        const buttons = $$(".tab-btn");
        const next =
          buttons[
            (buttons.indexOf(btn) +
              (ev.key === "ArrowRight" ? 1 : buttons.length - 1)) %
              buttons.length
          ];
        selectSidebarTab(next.getAttribute("data-tab"));
        next.focus();
      }
    });
  });

  $("#timeline").addEventListener("click", (ev) => {
    const chip = ev.target.closest(".chip[data-prompt]");
    if (chip) {
      $("#prompt-input").value = chip.getAttribute("data-prompt") || "";
      focusPrompt();
    }
  });
  $("#timeline").addEventListener("scroll", () => {
    const timeline = $("#timeline");
    state.followTimeline =
      timeline.scrollHeight - timeline.scrollTop - timeline.clientHeight < 80;
  });

  $("#btn-send").addEventListener("click", handleSendPrompt);
  $("#prompt-input").addEventListener("keydown", handlePromptKeydown);
  $("#prompt-input").addEventListener("input", resizePromptInput);
  resizePromptInput();
  $("#btn-stop").addEventListener("click", (ev) =>
    runAction(() => apiPost("/api/cancel"), ev.currentTarget),
  );

  document.addEventListener("keydown", (ev) => {
    if (ev.isComposing) return;
    const modal = $(".modal-backdrop:not(.hidden)");
    if (ev.key === "Escape") {
      if (modal) closeModal(modal.id);
      else if (!closePopovers(true)) closeDrawers();
      ev.preventDefault();
    } else if (modal && ev.key === "Tab") {
      const focusables = modalFocusables(modal);
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!first) {
        ev.preventDefault();
        (modal.querySelector(".modal-dialog") || modal).focus();
      } else if (
        ev.shiftKey &&
        (document.activeElement === first ||
          !focusables.includes(document.activeElement))
      ) {
        ev.preventDefault();
        last.focus();
      } else if (
        !ev.shiftKey &&
        (document.activeElement === last ||
          !focusables.includes(document.activeElement))
      ) {
        ev.preventDefault();
        first.focus();
      }
    } else if (!modal && ev.key === "Tab" && activeDrawer()) {
      const drawer = activeDrawer();
      const focusables = [
        drawer.toggle,
        ...modalFocusables(drawer.panel),
      ].filter(Boolean);
      const current = focusables.indexOf(document.activeElement);
      const next =
        current === -1
          ? ev.shiftKey
            ? focusables.length - 1
            : 0
          : (current + (ev.shiftKey ? focusables.length - 1 : 1)) %
            focusables.length;
      ev.preventDefault();
      focusables[next]?.focus();
    } else if (
      !modal &&
      (ev.ctrlKey || ev.metaKey) &&
      ev.key.toLowerCase() === "k"
    ) {
      ev.preventDefault();
      focusPrompt();
    }
  });

  $("#btn-open-models").addEventListener("click", openModelsModal);
  $("#btn-open-workspace").addEventListener("click", openWorkspaceModal);
  $("#btn-browse-workspace").addEventListener("click", () =>
    browseWorkspace($("#workspace-path-input").value.trim()),
  );
  $("#btn-workspace-parent").addEventListener("click", () => {
    if (state.workspaceBrowseParent)
      browseWorkspace(state.workspaceBrowseParent);
  });
  $("#workspace-path-input").addEventListener(
    "input",
    invalidateWorkspaceSelection,
  );
  $("#workspace-path-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.isComposing && ev.keyCode !== 229) {
      ev.preventDefault();
      browseWorkspace(ev.target.value.trim());
    }
  });
  $("#btn-switch-workspace").addEventListener("click", switchWorkspace);
  $("#btn-insert-at").addEventListener("click", openFileLibrary);

  $("#select-approval-mode").addEventListener("change", (ev) => {
    const control = ev.currentTarget;
    runAction(
      async () => {
        const mode = await apiPost("/api/mode", {
          approval_mode: control.value,
        });
        if (mode.approval_mode) control.value = mode.approval_mode;
        if (mode.effort) $("#select-effort").value = mode.effort;
        syncComposerOptions();
      },
      control,
      (err) => {
        showError(err);
        apiGet("/api/state")
          .then(updateTopbar)
          .catch(() => {});
      },
    );
  });
  $("#select-effort").addEventListener("change", (ev) => {
    const control = ev.currentTarget;
    runAction(
      async () => {
        const mode = await apiPost("/api/mode", { effort: control.value });
        if (mode.effort) control.value = mode.effort;
        if (mode.approval_mode)
          $("#select-approval-mode").value = mode.approval_mode;
        syncComposerOptions();
      },
      control,
      (err) => {
        showError(err);
        apiGet("/api/state")
          .then(updateTopbar)
          .catch(() => {});
      },
    );
  });

  $("#act-new-chat").addEventListener("click", (ev) =>
    runAction(async () => {
      if (!requireIdle()) return;
      const result = await apiPost("/api/clear");
      if (result.state) applyClearedState(result.state);
      focusPrompt();
    }, ev.currentTarget),
  );
  $("#act-compact").addEventListener("click", (ev) =>
    runAction(() => requireIdle() && apiPost("/api/compact"), ev.currentTarget),
  );
  $("#act-open-plan").addEventListener("click", openPlanEditor);
  $("#act-open-goal").addEventListener("click", () => {
    setDrawer("inspector", true);
    $("#goal-quick-input").focus();
  });
  $("#act-git-diff").addEventListener("click", (ev) =>
    runAction(async () => {
      const request = ++state.previewRequest;
      const epoch = state.workspaceEpoch;
      const data = await apiGet("/api/git");
      if (request !== state.previewRequest || epoch !== state.workspaceEpoch)
        return;
      $("#preview-modal-title").textContent =
        `Git 变更 · ${data.branch || "workspace"}`;
      $("#preview-modal-content").textContent =
        `${data.status}\n\n${data.diff || "(无未提交代码 Diff)"}`;
      $("#btn-insert-file-ref").classList.add("hidden");
      $("#preview-truncation-notice").classList.add("hidden");
      openModal("modal-preview");
    }, ev.currentTarget),
  );

  $("#btn-submit-plan-task").addEventListener("click", (ev) =>
    runAction(async () => {
      const task = ($("#plan-task-input").value || "").trim();
      if (!task || !requireIdle() || !requireModel()) return;
      await apiPost("/api/plan", { action: "generate", task });
      closeModal("modal-plan-prompt");
    }, ev.currentTarget),
  );
  $("#btn-approve-plan").addEventListener("click", (ev) =>
    runAction(async () => {
      if (!requireIdle() || !requireModel()) return;
      const plan = $("#plan-editor-textarea").value;
      await apiPost("/api/plan", { action: "approve", plan });
    }, ev.currentTarget),
  );
  $("#btn-close-plan").addEventListener("click", closePlanEditor);

  $("#btn-start-goal").addEventListener("click", (ev) =>
    runAction(async () => {
      const goal = ($("#goal-quick-input").value || "").trim();
      if (!goal || !requireIdle() || !requireModel()) return;
      await apiPost("/api/goal", { action: "start", goal });
      if ($("#goal-quick-input").value.trim() === goal)
        $("#goal-quick-input").value = "";
    }, ev.currentTarget),
  );
  $("#btn-stop-goal").addEventListener("click", (ev) =>
    runAction(() => apiPost("/api/goal", { action: "stop" }), ev.currentTarget),
  );
  $("#btn-refresh-tasks").addEventListener("click", refreshTasks);

  // File filter & preview insert
  $("#file-search-input").addEventListener("input", () => {
    clearTimeout(state.fileSearchTimer);
    state.fileRequest += 1;
    state.fileController?.abort();
    renderFilesList();
    state.fileSearchTimer = setTimeout(loadWorkspaceFiles, 180);
  });
  $("#btn-insert-file-ref").addEventListener("click", () => {
    closeModal("modal-preview", false);
    if (state.previewFilePath) insertAtReference(state.previewFilePath);
  });

  // Modal close buttons
  $$(".modal-close").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-close");
      if (target) closeModal(target);
    });
  });
  $$(".modal-backdrop").forEach((modal) => {
    modal.addEventListener("click", (ev) => {
      if (ev.target === modal) closeModal(modal.id);
    });
  });

  // Model Studio Modal events
  $("#model-filter-input").addEventListener(
    "input",
    renderConfiguredModelsList,
  );
  $("#btn-reset-editor").addEventListener("click", resetModelEditor);
  [
    "#editor-name",
    "#editor-provider",
    "#editor-url",
    "#editor-model-id",
    "#editor-api-key",
    "#editor-key-env",
  ].forEach((selector) => {
    $(selector).addEventListener("input", invalidateModelEditor);
  });

  $("#editor-preset-select").addEventListener("change", (ev) => {
    invalidateModelEditor();
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
    $("#editor-api-key").value = preset.default_key || "";
    $("#editor-fetched-models").classList.add("hidden");
    $("#editor-fetched-models").innerHTML = "";
    setEditorStatus(
      `已套用「${preset.label}」预设，请填写 API Key 后保存或点击拉取模型`,
      false,
    );
  });

  bindEditorAction("#btn-fetch-remote-models", fetchRemoteModels);

  $("#editor-fetched-models").addEventListener("change", (ev) => {
    if (ev.target.value) {
      $("#editor-model-id").value = ev.target.value;
    }
  });

  bindEditorAction("#btn-save-model", async () => {
    if (!requireIdle()) return;
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
      const result = await apiPost("/api/models/save", payload);
      await refreshModelsCatalog();
      const saved = state.models.find((model) => model.name === payload.name);
      if (saved && $("#editor-name").value.trim() === payload.name)
        populateEditorForEdit(saved);
      const snap = await apiGet("/api/state");
      updateTopbar(snap);
      const activated = result.activated ?? snap.active_model === payload.name;
      setEditorStatus(
        activated
          ? `✓ 模型 ${payload.name} 已保存并启用`
          : `配置已保存，但未能启用：${result.activation_error || "请检查连接后点击切换"}`,
        !activated,
      );
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  bindEditorAction("#btn-test-model", async () => {
    if (!requireIdle()) return;
    setEditorStatus("正在测试连接...", false);
    try {
      const res = await apiPost("/api/models/test", {
        name: $("#editor-name").value.trim() || "test",
        is_edit: Boolean(state.editingModelName),
        provider: $("#editor-provider").value,
        base_url: $("#editor-url").value.trim(),
        model: $("#editor-model-id").value.trim(),
        api_key: $("#editor-api-key").value.trim(),
        api_key_env: $("#editor-key-env").value.trim(),
      });
      setEditorStatus(
        res.ok ? "✓ 连接测试成功！" : "连接失败，请检查地址和 Key",
        !res.ok,
      );
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  bindEditorAction("#btn-import-gateway", async () => {
    if (!requireIdle()) return;
    const base_url = $("#editor-url").value.trim();
    const api_key = $("#editor-api-key").value.trim();
    const api_key_env = $("#editor-key-env").value.trim();
    const prefix = $("#editor-name").value.trim() || "gw";
    setEditorStatus("正在从该网关批量导入全部模型...", false);
    try {
      const res = await apiPost("/api/models/sync", {
        base_url,
        api_key,
        api_key_env,
        prefix,
      });
      setEditorStatus(
        `✓ 已成功导入 ${res.count} 个模型 (前缀: ${prefix}/)`,
        false,
      );
      await refreshModelsCatalog();
    } catch (err) {
      setEditorStatus(err.message, true);
    }
  });

  bindEditorAction("#btn-sync-magpie", async () => {
    if (!requireIdle()) return;
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
    hydrateSnapshot(snap);
  } catch (e) {
    state.needsSnapshot = true;
    setConnectionState("disconnected");
    $("#active-model-label").textContent = "连接暂不可用";
    $("#model-status-dot").classList.add("unconfigured");
    $("#btn-open-models").title = `无法加载工作区：${e.message}`;
  }

  loadWorkspaceFiles();
  loadSkills();
  refreshTasks();
  state.needsSnapshot = true;
  connectSSE();
}

document.addEventListener("DOMContentLoaded", initApp);
