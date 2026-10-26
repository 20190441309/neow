/* Run directly with node --test tests/web_frontend.test.cjs. No DOM package needed. */
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(
  path.join(__dirname, "../neow/web/static/app.js"),
  "utf8",
);

function controller(overrides = {}) {
  const context = vm.createContext({
    console,
    clearTimeout,
    AbortController,
    document: {
      addEventListener() {},
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    ...overrides,
  });
  vm.runInContext(source, context, { filename: "app.js" });
  vm.runInContext("state.workspaceGeneration = 0", context);
  return context;
}

function element() {
  const classes = new Set();
  return {
    children: [],
    classList: {
      add(...names) {
        names.forEach((name) => classes.add(name));
      },
      remove(...names) {
        names.forEach((name) => classes.delete(name));
      },
      contains(name) {
        return classes.has(name);
      },
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : force;
        if (enabled) classes.add(name);
        else classes.delete(name);
        return enabled;
      },
    },
    replaceChildren(...children) {
      this.children = children;
    },
    appendChild(child) {
      this.children.push(child);
    },
  };
}

test("HTML escaping protects text and double-quoted attributes", () => {
  const app = controller();
  assert.equal(
    app.escapeHtml('<img src="x" onerror="alert(1)">&'),
    "&lt;img src=&quot;x&quot; onerror=&quot;alert(1)&quot;&gt;&amp;",
  );
});

test("markdown keeps model-supplied HTML inert in prose and code", () => {
  const app = controller();
  const html = app.renderMarkdownLite(
    '**Review** <script>alert(1)</script> `a < b`\n```html\n<img onerror="alert(1)">\n```',
  );
  assert.match(html, /<strong>Review<\/strong>/);
  assert.match(html, /<code>a &lt; b<\/code>/);
  assert.match(html, /<pre><code>/);
  assert.doesNotMatch(html, /<(script|img)\b/);
});

test("diff rendering distinguishes headers and changes without interpreting HTML", () => {
  const app = controller();
  const html = app.renderDiffHtml(
    '--- a/file.html\n+++ b/file.html\n@@ -1 +1 @@\n-<script>old</script>\n+<img src="x">',
  );
  assert.equal((html.match(/diff-hdr/g) || []).length, 3);
  assert.equal((html.match(/diff-del/g) || []).length, 1);
  assert.equal((html.match(/diff-add/g) || []).length, 1);
  assert.doesNotMatch(html, /<(script|img)\b/);
});

test("POST API uses JSON and preserves the server's useful error message", async () => {
  const calls = [];
  const app = controller({
    fetch: async (...args) => {
      calls.push(args);
      return {
        ok: false,
        status: 409,
        json: async () => ({ error: "Turn is busy" }),
      };
    },
  });
  await assert.rejects(
    app.apiPost("/api/chat", { prompt: "hello" }),
    /Turn is busy/,
  );
  assert.equal(calls[0][0], "/api/chat");
  assert.equal(calls[0][1].method, "POST");
  assert.equal(calls[0][1].headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0][1].body), {
    prompt: "hello",
    workspace_generation: 0,
  });
});

test("POST sends the current workspace generation, never a caller's stale one", async () => {
  const calls = [];
  const app = controller({
    fetch: async (...args) => {
      calls.push(args);
      return { ok: true, json: async () => ({ ok: true }) };
    },
  });
  vm.runInContext("state.workspaceGeneration = 3", app);
  await app.apiPost("/api/clear", { workspace_generation: 1 });
  assert.equal(JSON.parse(calls[0][1].body).workspace_generation, 3);
});

test("POST refuses mutations until a workspace snapshot has loaded", async () => {
  let calls = 0;
  const app = controller({
    fetch: async () => {
      calls += 1;
    },
  });
  vm.runInContext("state.workspaceGeneration = null", app);
  await assert.rejects(app.apiPost("/api/clear"), /工作区状态尚未同步/);
  assert.equal(calls, 0);
});

test("GET API returns decoded response data", async () => {
  const snapshot = { active_model: null, busy: false };
  const app = controller({
    fetch: async () => ({ ok: true, json: async () => snapshot }),
  });
  assert.deepEqual(await app.apiGet("/api/state"), snapshot);
});

test("POST rejects an unsuccessful operation even with an HTTP 200 response", async () => {
  const app = controller({
    fetch: async () => ({
      ok: true,
      json: async () => ({ ok: false, error: "Not ready" }),
    }),
  });
  await assert.rejects(
    app.apiPost("/api/goal", { action: "start" }),
    /Not ready/,
  );
});

test("Enter does not submit an unfinished IME composition or Shift+Enter", () => {
  const app = controller();
  let submissions = 0;
  let prevented = 0;
  app.handleSendPrompt = () => {
    submissions += 1;
  };
  const event = {
    key: "Enter",
    shiftKey: false,
    isComposing: false,
    keyCode: 13,
    preventDefault() {
      prevented += 1;
    },
  };
  app.handlePromptKeydown({ ...event, isComposing: true });
  app.handlePromptKeydown({ ...event, keyCode: 229 });
  app.handlePromptKeydown({ ...event, shiftKey: true });
  app.handlePromptKeydown({ ...event, key: "a" });
  assert.equal(submissions, 0);
  assert.equal(prevented, 0);
  app.handlePromptKeydown(event);
  assert.equal(submissions, 1);
  assert.equal(prevented, 1);
});

test("composer autosizing respects the smaller mobile CSS height cap", () => {
  const input = { style: {}, scrollHeight: 160 };
  const getComputedStyle = () => ({ maxHeight: "140px" });
  const app = controller({
    document: { addEventListener() {}, querySelector: () => input },
    getComputedStyle,
    window: { getComputedStyle },
  });
  app.resizePromptInput();
  assert.equal(input.style.height, "140px");
  assert.equal(input.style.overflowY, "auto");
});

test("clearing the timeline restores the same welcome node and forgets stale streams", () => {
  const timeline = element();
  const hero = element();
  hero.classList.add("hidden");
  timeline.children = [hero, element()];
  const app = controller({
    document: {
      addEventListener() {},
      querySelector(selector) {
        if (selector === "#timeline") return timeline;
        if (selector === "#welcome-hero") return hero;
        return null;
      },
    },
  });
  const state = vm.runInContext("state", app);
  state.streamingAssistantEl = element();
  state.streamingAssistantText = "old response";
  state.streamingReasoningEl = element();
  state.streamingReasoningText = "old reasoning";
  state.toolCardsById.set("old-tool", element());
  state.followTimeline = false;
  app.resetTimeline();

  assert.deepEqual(timeline.children, [hero]);
  assert.equal(hero.classList.contains("hidden"), false);
  assert.equal(state.streamingAssistantEl, null);
  assert.equal(state.streamingAssistantText, "");
  assert.equal(state.streamingReasoningEl, null);
  assert.equal(state.streamingReasoningText, "");
  assert.equal(state.toolCardsById.size, 0);
  assert.equal(state.followTimeline, true);

  app.resetTimeline(false);
  assert.equal(hero.classList.contains("hidden"), true);
  app.resetTimeline();
  assert.deepEqual(timeline.children, [hero]);
  assert.equal(hero.classList.contains("hidden"), false);
});

test("streaming does not drag the timeline away from earlier messages", () => {
  const timeline = { scrollTop: 24, scrollHeight: 600 };
  const app = controller({
    document: { addEventListener() {}, querySelector: () => timeline },
  });
  const state = vm.runInContext("state", app);
  state.followTimeline = false;
  app.scrollTimelineBottom();
  assert.equal(timeline.scrollTop, 24);
  state.followTimeline = true;
  app.scrollTimelineBottom();
  assert.equal(timeline.scrollTop, 600);
});

test("async actions report failures and restore disabled buttons", async () => {
  const app = controller();
  app.syncBusyControls = () => {};
  const button = { disabled: false };
  const failure = new Error("Unavailable");
  const errors = [];
  await app.runAction(
    async () => {
      assert.equal(button.disabled, true);
      throw failure;
    },
    button,
    (error) => errors.push(error),
  );
  assert.equal(button.disabled, false);
  assert.deepEqual(errors, [failure]);
});

test("a disabled action cannot be submitted twice", async () => {
  const app = controller();
  let attempts = 0;
  await app.runAction(
    () => {
      attempts += 1;
    },
    { disabled: true },
  );
  assert.equal(attempts, 0);
});

function promptController(fetch) {
  const input = { value: "  Review this function  " };
  const errors = [];
  const app = controller({
    fetch,
    document: { addEventListener() {}, querySelector: () => input },
  });
  const state = vm.runInContext("state", app);
  state.activeModel = "configured-model";
  app.resizePromptInput = () => {};
  app.syncBusyControls = () => {};
  app.setBusyState = (busy) => {
    state.busy = busy;
  };
  app.showError = (error) => errors.push(error);
  return { app, input, state, errors };
}

test("failed chat requests keep the complete draft and release submission state", async () => {
  const { app, input, state, errors } = promptController(async () => {
    throw new Error("Connection interrupted");
  });
  const draft = input.value;
  await app.handleSendPrompt();
  assert.equal(input.value, draft);
  assert.equal(state.submitting, false);
  assert.equal(state.busy, false);
  assert.equal(errors.length, 1);
  assert.match(errors[0].message, /Connection interrupted/);
});

test("a successful request cannot erase a newer draft typed while waiting", async () => {
  let resolveResponse;
  const { app, input, state } = promptController(
    () =>
      new Promise((resolve) => {
        resolveResponse = resolve;
      }),
  );
  const request = app.handleSendPrompt();
  assert.equal(state.submitting, true);
  input.value = "Next task";
  resolveResponse({ ok: true, json: async () => ({ ok: true }) });
  await request;
  assert.equal(input.value, "Next task");
  assert.equal(state.submitting, false);
});

test("unconfigured models open setup without sending or discarding the draft", async () => {
  let requests = 0;
  let modalOpened = 0;
  const { app, input, state } = promptController(async () => {
    requests += 1;
  });
  state.activeModel = null;
  app.openModelsModal = () => {
    modalOpened += 1;
  };
  app.setEditorStatus = () => {};
  const draft = input.value;
  await app.handleSendPrompt();
  assert.equal(requests, 0);
  assert.equal(modalOpened, 1);
  assert.equal(input.value, draft);
});

test("resolved server requests remove approvals and questions in other tabs", () => {
  const removed = [];
  const app = controller({
    document: {
      addEventListener() {},
      getElementById(id) {
        return {
          remove() {
            removed.push(id);
          },
        };
      },
    },
  });
  app.handleServerEvent({ type: "approval_resolved", id: "permit-1" });
  app.handleServerEvent({ type: "ask_user_resolved", id: "question-1" });
  assert.deepEqual(removed, ["approval-permit-1", "ask-question-1"]);
});

test("reconnecting preserves pending answer drafts and removes only resolved requests", () => {
  const nodes = new Map();
  const queue = {
    children: [],
    querySelectorAll() {
      return this.children;
    },
  };
  function request(id, draft = "") {
    const node = {
      id,
      draft,
      remove() {
        queue.children = queue.children.filter((child) => child !== this);
        nodes.delete(id);
      },
    };
    queue.children.push(node);
    nodes.set(id, node);
    return node;
  }
  const retained = request("ask-still-pending", "My answer in progress");
  request("approval-already-resolved");
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: () => queue,
      getElementById: (id) => nodes.get(id) || null,
    },
  });
  app.renderApprovalRequest = (item) => {
    if (!nodes.has(`approval-${item.id}`)) request(`approval-${item.id}`);
  };
  app.renderAskUserRequest = (item) => {
    if (!nodes.has(`ask-${item.id}`)) request(`ask-${item.id}`);
  };
  app.reconcilePendingRequests({
    pending_approvals: [{ id: "new-permit" }],
    pending_questions: [{ id: "still-pending" }],
  });
  assert.equal(nodes.get("ask-still-pending"), retained);
  assert.equal(retained.draft, "My answer in progress");
  assert.equal(nodes.has("approval-already-resolved"), false);
  assert.equal(nodes.has("approval-new-permit"), true);
});

test("opening a compact drawer focuses it and makes the obscured workspace inert", () => {
  const nodes = new Map();
  let focused;
  const selectors = [
    ".app-shell",
    ".center-stage",
    "#workspace-sidebar",
    "#workspace-inspector",
    "#btn-toggle-sidebar",
    "#btn-toggle-inspector",
    "#panel-backdrop",
  ];
  for (const selector of selectors) {
    const node = element();
    node.attributes = {};
    node.setAttribute = (key, value) => {
      node.attributes[key] = value;
    };
    node.focus = () => {
      focused = node;
    };
    nodes.set(selector, node);
  }
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
      querySelectorAll: () => [],
    },
    window: { matchMedia: () => ({ matches: true }) },
  });
  app.modalFocusables = () => [];
  app.setDrawer("inspector", true);
  assert.equal(focused, nodes.get("#workspace-inspector"));
  assert.equal(nodes.get(".center-stage").inert, true);
  assert.equal(nodes.get("#workspace-sidebar").inert, true);
  assert.equal(nodes.get("#workspace-inspector").inert, false);
  assert.equal(
    nodes.get("#btn-toggle-inspector").attributes["aria-expanded"],
    "true",
  );

  app.closeDrawers();
  assert.equal(focused, nodes.get("#btn-toggle-inspector"));
  assert.equal(nodes.get(".center-stage").inert, false);
  assert.equal(nodes.get("#workspace-inspector").inert, true);
});

test("the inspector is an opt-in drawer even on a wide desktop", () => {
  const nodes = new Map();
  for (const selector of [
    ".app-shell",
    ".center-stage",
    "#workspace-sidebar",
    "#workspace-inspector",
    "#btn-toggle-sidebar",
    "#btn-toggle-inspector",
    "#panel-backdrop",
  ]) {
    const node = element();
    node.attributes = {};
    node.setAttribute = (key, value) => {
      node.attributes[key] = value;
    };
    node.focus = () => {};
    nodes.set(selector, node);
  }
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
      querySelectorAll: () => [],
    },
    window: { matchMedia: () => ({ matches: false }) },
  });
  app.modalFocusables = () => [];
  app.syncDrawerAccessibility();
  assert.equal(nodes.get("#workspace-inspector").inert, true);
  assert.equal(
    nodes.get("#workspace-inspector").attributes["aria-hidden"],
    "true",
  );
  assert.equal(nodes.get("#workspace-sidebar").inert, false);
  assert.equal(app.activeDrawer(), null);

  app.setDrawer("inspector", true);
  assert.equal(app.activeDrawer().name, "inspector");
  assert.equal(nodes.get("#workspace-inspector").inert, false);
  assert.equal(nodes.get("#workspace-sidebar").inert, true);
  assert.equal(nodes.get(".center-stage").inert, true);
  assert.equal(
    nodes.get("#btn-toggle-inspector").attributes["aria-label"],
    "关闭任务面板",
  );

  app.closeDrawers();
  assert.equal(nodes.get("#workspace-inspector").inert, true);
  assert.equal(nodes.get("#workspace-sidebar").inert, false);
  assert.equal(nodes.get(".center-stage").inert, false);

  app.setDrawer("sidebar", true);
  assert.equal(
    nodes.get(".app-shell").classList.contains("sidebar-open"),
    false,
  );
  assert.equal(app.activeDrawer(), null);
  assert.equal(nodes.get(".center-stage").inert, false);
});

test("resource navigation reveals files and restores focus before hiding them", () => {
  const panel = element();
  panel.classList.add("hidden");
  let focused;
  const search = {
    focus: () => {
      focused = search;
    },
  };
  const toggle = element();
  toggle.attributes = {};
  toggle.setAttribute = (key, value) => {
    toggle.attributes[key] = value;
  };
  toggle.focus = () => {
    focused = toggle;
  };
  const conversation = element();
  panel.contains = (node) => node === search;
  const nodes = new Map([
    ["#workspace-library", panel],
    ["#btn-toggle-library", toggle],
    ["#btn-show-conversation", conversation],
    ["#file-search-input", search],
  ]);
  const document = {
    addEventListener() {},
    activeElement: search,
    querySelector: (selector) => nodes.get(selector),
  };
  const app = controller({ document });
  const calls = [];
  app.selectSidebarTab = (tab) => calls.push(tab);
  app.setDrawer = (name, open) => calls.push([name, open]);
  app.openFileLibrary();
  assert.equal(panel.classList.contains("hidden"), false);
  assert.equal(toggle.attributes["aria-expanded"], "true");
  assert.equal(conversation.classList.contains("active"), false);
  assert.equal(focused, search);
  assert.deepEqual(calls, ["files", ["sidebar", true]]);

  app.setLibraryOpen(false);
  assert.equal(panel.classList.contains("hidden"), true);
  assert.equal(toggle.attributes["aria-expanded"], "false");
  assert.equal(conversation.classList.contains("active"), true);
  assert.equal(focused, toggle);
});

test("resource tabs expose only the selected tab in the keyboard order", () => {
  function tab(name) {
    const node = element();
    node.attributes = { "data-tab": name };
    node.setAttribute = (key, value) => {
      node.attributes[key] = value;
    };
    node.getAttribute = (key) => node.attributes[key];
    return node;
  }
  const files = tab("files");
  const skills = tab("skills");
  const filesPane = Object.assign(element(), { id: "tab-files" });
  const skillsPane = Object.assign(element(), { id: "tab-skills" });
  const app = controller({
    document: {
      addEventListener() {},
      querySelectorAll: (selector) =>
        selector === ".tab-btn" ? [files, skills] : [filesPane, skillsPane],
    },
  });
  app.selectSidebarTab("skills");
  assert.equal(files.attributes["aria-selected"], "false");
  assert.equal(files.attributes.tabindex, "-1");
  assert.equal(skills.attributes["aria-selected"], "true");
  assert.equal(skills.attributes.tabindex, "0");
  assert.equal(skillsPane.classList.contains("active"), true);
  assert.equal(filesPane.classList.contains("active"), false);
});

test("closing a menu restores its summary, but outside clicks keep their focus", () => {
  const focused = {};
  let restored = 0;
  const summary = {
    focus: () => {
      restored += 1;
    },
  };
  const menu = {
    open: true,
    contains: (node) => node === focused,
    querySelector: () => summary,
  };
  const other = { ...menu, contains: () => false };
  const app = controller({
    document: {
      addEventListener() {},
      activeElement: focused,
      querySelectorAll: () => [menu, other].filter((item) => item.open),
    },
  });
  assert.equal(app.closePopovers(true, other), true);
  assert.equal(menu.open, false);
  assert.equal(other.open, true);
  assert.equal(restored, 1);
  menu.open = true;
  assert.equal(app.closePopovers(false), true);
  assert.equal(restored, 1);
  assert.equal(app.closePopovers(true), false);
});

test("compact composer settings still disclose unrestricted execution", () => {
  const label = {};
  const trigger = element();
  trigger.attributes = {};
  trigger.setAttribute = (key, value) => {
    trigger.attributes[key] = value;
  };
  const mode = { value: "yolo" };
  const nodes = new Map([
    ["#select-approval-mode", mode],
    ["#select-effort", { value: "high" }],
    ["#approval-mode-label", label],
    ["#composer-options-trigger", trigger],
  ]);
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
    },
  });
  app.syncComposerOptions();
  assert.equal(label.textContent, "全自动执行");
  assert.equal(trigger.classList.contains("unrestricted"), true);
  assert.match(trigger.attributes["aria-label"], /全自动执行.*深入/);
  mode.value = "write";
  app.syncComposerOptions();
  assert.equal(label.textContent, "写入前询问");
  assert.equal(trigger.classList.contains("unrestricted"), false);
});

test("focus discovery does not include SVG use references as links", () => {
  const button = {
    disabled: false,
    closest: () => null,
    getClientRects: () => [{}],
  };
  const svgUse = {
    disabled: false,
    closest: () => null,
    getClientRects: () => [{}],
  };
  const modal = {
    querySelectorAll(selector) {
      return selector.includes("a[href]") ? [button] : [svgUse, button];
    },
  };
  const app = controller();
  const focusables = app.modalFocusables(modal);
  assert.equal(focusables.length, 1);
  assert.equal(focusables[0], button);
});

test("drawer focus discovery includes menu summaries but skips inactive tabs", () => {
  const make = (tabindex) => ({
    disabled: false,
    getAttribute: () => tabindex,
    closest: () => null,
    getClientRects: () => [{}],
  });
  const summary = make(null);
  const inactiveTab = make("-1");
  const activeTab = make("0");
  const panel = {
    querySelectorAll(selector) {
      assert.match(selector, /summary/);
      return [summary, inactiveTab, activeTab];
    },
  };
  const app = controller();
  const focusables = app.modalFocusables(panel);
  assert.equal(focusables.length, 2);
  assert.equal(focusables[0], summary);
  assert.equal(focusables[1], activeTab);
});

test("busy composer swaps send for stop and restores send when idle", () => {
  const nodes = new Map();
  const app = controller({
    document: {
      addEventListener() {},
      querySelector(selector) {
        if (!nodes.has(selector)) {
          const node = element();
          node.setAttribute = () => {};
          nodes.set(selector, node);
        }
        return nodes.get(selector);
      },
    },
  });
  app.syncBusyControls = () => {};
  app.setBusyState(true);
  assert.equal(nodes.get("#btn-send").classList.contains("hidden"), true);
  assert.equal(nodes.get("#btn-stop").classList.contains("hidden"), false);
  assert.equal(nodes.get("#btn-send").disabled, true);
  app.setBusyState(false);
  assert.equal(nodes.get("#btn-send").classList.contains("hidden"), false);
  assert.equal(nodes.get("#btn-stop").classList.contains("hidden"), true);
  assert.equal(nodes.get("#btn-send").disabled, false);
});

test("snapshot refresh preserves edits to an unchanged pending plan", () => {
  const banner = element();
  const editor = { value: "" };
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) =>
        selector === "#plan-banner" ? banner : editor,
    },
  });
  app.renderPlanBanner({ pending: true, text: "Original plan" });
  editor.value = "My revised plan";
  app.renderPlanBanner({ pending: true, text: "Original plan" });
  assert.equal(editor.value, "My revised plan");
  app.renderPlanBanner({ pending: true, text: "A newly generated plan" });
  assert.equal(editor.value, "A newly generated plan");
});

test("recovery rehydrates responses completed while the connection was down", () => {
  const timeline = { scrollTop: 42 };
  const rendered = [];
  const app = controller({
    document: { addEventListener() {}, querySelector: () => timeline },
  });
  const state = vm.runInContext("state", app);
  state.followTimeline = false;
  app.resetTimeline = () => {
    rendered.length = 0;
  };
  app.appendUserCard = (text) => rendered.push(["user", text]);
  app.finalizeStreamingAssistantCard = (text) =>
    rendered.push(["assistant", text]);
  app.updateTopbar = (snap) => {
    state.busy = snap.busy;
  };
  app.reconcilePendingRequests = () => {};
  const snapshot = {
    busy: false,
    timeline: [
      { kind: "user", text: "Explain the code" },
      {
        kind: "assistant",
        text: "Complete response recovered from the server",
      },
    ],
  };
  app.hydrateSnapshot(snapshot);
  assert.deepEqual(rendered, [
    ["user", "Explain the code"],
    ["assistant", "Complete response recovered from the server"],
  ]);
  assert.equal(state.busy, false);
  assert.equal(state.followTimeline, false);
  assert.equal(timeline.scrollTop, 42);
});

test("buffered completion already in the snapshot is not rendered twice", () => {
  const app = controller();
  const baseline = [{ kind: "user", text: "Question" }];
  const snapshot = {
    timeline: [...baseline, { kind: "assistant", text: "Answer" }],
  };
  const events = app.eventsAfterSnapshot(
    snapshot,
    [
      { type: "content_delta", text: "Answer" },
      { type: "turn_completed", content: "Answer" },
      { type: "approval_request", id: "new-approval" },
    ],
    baseline,
  );
  assert.equal(
    events.filter((event) => event.type === "content_delta").length,
    0,
  );
  assert.equal(events[0].snapshotApplied, true);
  assert.equal(events[1].id, "new-approval");
});

test("historical equal text cannot consume a genuinely new buffered response", () => {
  const app = controller();
  const baseline = [{ kind: "assistant", text: "Same answer" }];
  const buffered = [{ type: "turn_completed", content: "Same answer" }];
  const events = app.eventsAfterSnapshot(
    { timeline: baseline },
    buffered,
    baseline,
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].snapshotApplied, undefined);
  assert.equal(events[0].content, "Same answer");
});

test("switching workspaces invalidates old drafts and fetches, once per generation", () => {
  const nodes = new Map();
  const selectors = [
    "#prompt-input",
    "#file-search-input",
    "#goal-quick-input",
    "#plan-task-input",
    "#plan-editor-textarea",
  ];
  selectors.forEach((selector) =>
    nodes.set(selector, { value: "old project draft" }),
  );
  let aborted = 0;
  let hydrations = 0;
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
      querySelectorAll: () => [],
    },
  });
  const state = vm.runInContext("state", app);
  state.workspacePath = "/project-a";
  state.workspaceGeneration = 1;
  state.files = [{ path: "old.py" }];
  state.expandedDirectories.add("old-src");
  state.fileDirectories.set("old-src", { entries: [] });
  state.previewFilePath = "old.py";
  state.fileController = {
    abort() {
      aborted += 1;
    },
  };
  state.recoveryController = {
    abort() {
      aborted += 1;
    },
  };
  app.closeDrawers = () => {};
  app.hydrateSnapshot = (snap) => {
    hydrations += 1;
    state.workspacePath = snap.cwd;
    state.workspaceGeneration = snap.workspace_generation;
  };
  app.loadWorkspaceFiles = () => {};
  app.loadSkills = () => {};
  app.refreshTasks = () => {};
  app.resizePromptInput = () => {};
  app.focusPrompt = () => {};
  const snapshot = { cwd: "/project-b", workspace_generation: 2 };
  app.applyWorkspaceState(snapshot);
  assert.equal(aborted, 2);
  assert.equal(state.files.length, 0);
  assert.equal(state.expandedDirectories.size, 0);
  assert.equal(state.fileDirectories.size, 0);
  assert.equal(state.previewFilePath, "");
  assert.equal(state.workspaceEpoch, 1);
  selectors.forEach((selector) => assert.equal(nodes.get(selector).value, ""));
  nodes.get("#prompt-input").value = "new project draft";
  app.applyWorkspaceState(snapshot);
  assert.equal(hydrations, 1);
  assert.equal(nodes.get("#prompt-input").value, "new project draft");
});

test("a stale file preview cannot open after the workspace changes", async () => {
  let finish;
  let opened = 0;
  const app = controller({
    fetch: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  app.openModal = () => {
    opened += 1;
  };
  const state = vm.runInContext("state", app);
  const preview = app.openFilePreview("old.py");
  state.workspaceEpoch += 1;
  finish({
    ok: true,
    json: async () => ({ path: "old.py", content: "old secret" }),
  });
  await preview;
  assert.equal(opened, 0);
  assert.equal(state.previewFilePath, "");
});

test("server file search ignores older responses arriving after a newer query", async () => {
  const input = { value: "old" };
  const badge = { textContent: "", title: "" };
  const requests = [];
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) =>
        selector === "#file-search-input" ? input : badge,
    },
    fetch: (url) => new Promise((resolve) => requests.push({ url, resolve })),
  });
  app.renderFilesList = () => {};
  const first = app.loadWorkspaceFiles();
  input.value = "new";
  const second = app.loadWorkspaceFiles();
  requests[1].resolve({
    ok: true,
    json: async () => ({
      files: [{ path: "new.py" }],
      query: "new",
      truncated: false,
    }),
  });
  await second;
  requests[0].resolve({
    ok: true,
    json: async () => ({
      files: [{ path: "old.py" }],
      query: "old",
      truncated: false,
    }),
  });
  await first;
  const state = vm.runInContext("state", app);
  assert.equal(requests[0].url, "/api/files?q=old");
  assert.equal(requests[1].url, "/api/files?q=new");
  assert.equal(state.files[0].path, "new.py");
});

test("directory browsing is lazy, deduplicates in-flight requests, and paginates", async () => {
  const requests = [];
  const app = controller({
    fetch: (url) => new Promise((resolve) => requests.push({ url, resolve })),
  });
  app.renderFilesList = () => {};
  const first = app.loadFileDirectory("src/space name");
  await app.loadFileDirectory("src/space name");
  assert.equal(requests.length, 1);
  assert.equal(
    requests[0].url,
    "/api/files/tree?path=src%2Fspace%20name&offset=0",
  );
  requests[0].resolve({
    ok: true,
    json: async () => ({
      workspace_generation: 0,
      entries: [{ name: "a.py" }],
      next_offset: 200,
    }),
  });
  await first;
  const state = vm.runInContext("state", app);
  assert.equal(state.fileDirectories.size, 1);
  assert.equal(state.fileDirectories.get("src/space name").loading, false);
  const second = app.loadFileDirectory("src/space name", true);
  assert.match(requests[1].url, /offset=200$/);
  requests[1].resolve({
    ok: true,
    json: async () => ({
      workspace_generation: 0,
      entries: [{ name: "b.py" }],
      next_offset: null,
    }),
  });
  await second;
  assert.deepEqual(
    Array.from(
      state.fileDirectories.get("src/space name").entries,
      (entry) => entry.name,
    ),
    ["a.py", "b.py"],
  );
  await app.loadFileDirectory("src/space name", true);
  assert.equal(requests.length, 2);
});

test("old directory responses cannot repopulate a switched or refreshed tree", async () => {
  const requests = [];
  const app = controller({
    fetch: () => new Promise((resolve) => requests.push(resolve)),
  });
  app.renderFilesList = () => {};
  const pending = app.loadFileDirectory("src");
  app.invalidateFileTree();
  const state = vm.runInContext("state", app);
  state.workspaceEpoch += 1;
  requests[0]({
    ok: true,
    json: async () => ({
      workspace_generation: 0,
      entries: [{ name: "old-secret.txt" }],
    }),
  });
  await pending;
  assert.equal(state.fileDirectories.size, 0);

  const mismatched = app.loadFileDirectory("src");
  requests[1]({
    ok: true,
    json: async () => ({
      workspace_generation: 5,
      entries: [{ name: "other-project.txt" }],
    }),
  });
  await mismatched;
  assert.equal(state.fileDirectories.get("src").entries.length, 0);
  assert.equal(state.fileDirectories.get("src").error, true);
});

test("directory load failures can be retried without dropping a loaded page", async () => {
  let calls = 0;
  const app = controller({
    fetch: async () => {
      calls += 1;
      if (calls === 1) throw new Error("offline");
      return {
        ok: true,
        json: async () => ({
          workspace_generation: 0,
          entries: [{ name: "next.py" }],
          next_offset: null,
        }),
      };
    },
  });
  app.renderFilesList = () => {};
  const state = vm.runInContext("state", app);
  state.fileDirectories.set("src", {
    entries: [{ name: "first.py" }],
    nextOffset: 200,
  });
  await app.loadFileDirectory("src", true);
  assert.equal(state.fileDirectories.get("src").error, true);
  await app.loadFileDirectory("src", true);
  assert.equal(state.fileDirectories.get("src").error, false);
  assert.deepEqual(
    Array.from(state.fileDirectories.get("src").entries, (entry) => entry.name),
    ["first.py", "next.py"],
  );
});

test("a root refresh reloads only expanded directories and keeps expansion choices", async () => {
  const app = controller({
    document: { addEventListener() {}, querySelector: () => ({ value: "" }) },
  });
  const calls = [];
  app.loadFileDirectory = async (path = "") => calls.push(path);
  const state = vm.runInContext("state", app);
  state.fileDirectories.set("closed", { entries: [] });
  state.expandedDirectories.add("src");
  state.expandedDirectories.add("src/core");
  await app.loadWorkspaceFiles();
  assert.deepEqual(calls, ["", "src", "src/core"]);
  assert.equal(state.fileDirectories.size, 0);
  assert.equal(state.expandedDirectories.has("src/core"), true);
});

test("search results form automatically opened folders with full-path file actions", () => {
  const app = controller();
  const state = vm.runInContext("state", app);
  state.expandedDirectories.add("other");
  const html = app.renderFileSearch([
    { path: "src/core/run.py" },
    { path: "src/core/test.py" },
    { path: "README.md" },
  ]);
  assert.equal((html.match(/data-directory="src"/g) || []).length, 1);
  assert.match(html, /data-directory="src" open/);
  assert.match(html, /data-directory="src\/core" open/);
  assert.match(html, /aria-label="预览 src\/core\/run.py"/);
  assert.match(html, /data-ref="src\/core\/run.py"/);
  assert.match(html, /class="file-path">run.py</);
  assert.equal(state.expandedDirectories.size, 1);
  assert.equal(state.expandedDirectories.has("other"), true);
});

test("folder and file names remain escaped, and a collapsed folder omits its children", () => {
  const app = controller();
  const state = vm.runInContext("state", app);
  state.fileDirectories.set("", {
    entries: [
      { name: '<img onerror="bad">', path: 'odd"dir', kind: "directory" },
    ],
    nextOffset: null,
  });
  state.fileDirectories.set('odd"dir', {
    entries: [{ name: "secret.py", path: 'odd"dir/secret.py', kind: "file" }],
    nextOffset: null,
  });
  const closed = app.renderFileDirectory();
  assert.doesNotMatch(closed, /<img|secret.py/);
  assert.match(closed, /&lt;img onerror=&quot;bad&quot;&gt;/);
  assert.match(closed, /data-directory="odd&quot;dir"/);
  state.expandedDirectories.add('odd"dir');
  const opened = app.renderFileDirectory();
  assert.match(opened, /secret.py/);
  const file = app.renderFileRow({ path: 'src/"quoted".py' });
  assert.match(file, /data-ref="src\/&quot;quoted&quot;.py"/);
});

test("final cumulative assistant content does not duplicate a pre-tool segment", () => {
  const body = { innerHTML: "" };
  const header = { textContent: "" };
  const card = {
    querySelector: (selector) => (selector === ".msg-body" ? body : header),
  };
  const app = controller();
  const state = vm.runInContext("state", app);
  state.completedAssistantPrefix = "I will inspect the file. ";
  state.streamingAssistantEl = card;
  state.streamingAssistantText = "Here is the result.";
  app.scrollTimelineBottom = () => {};
  app.finalizeStreamingAssistantCard(
    "I will inspect the file. Here is the result.",
  );
  assert.equal(body.innerHTML, "Here is the result.");
  assert.equal(state.completedAssistantPrefix, "");
});

test("file references quote paths containing spaces", () => {
  const input = { value: "Review" };
  const app = controller({
    document: { addEventListener() {}, querySelector: () => input },
  });
  app.focusPrompt = () => {};
  app.insertAtReference("src/my module.py");
  assert.equal(input.value, 'Review @"src/my module.py" ');
});

test("workspace browsing keeps the newest selected folder on out-of-order responses", async () => {
  const nodes = new Map();
  [
    "#workspace-path-input",
    "#workspace-directory-list",
    "#btn-workspace-parent",
    "#workspace-browse-path",
  ].forEach((selector) => {
    nodes.set(selector, {
      value: "",
      textContent: "",
      innerHTML: "",
      querySelectorAll: () => [],
    });
  });
  const requests = [];
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
    },
    fetch: (url) => new Promise((resolve) => requests.push({ url, resolve })),
  });
  app.syncBusyControls = () => {};
  app.setWorkspaceStatus = () => {};
  const first = app.browseWorkspace("/project-a");
  const second = app.browseWorkspace("/project-b");
  requests[1].resolve({
    ok: true,
    json: async () => ({ path: "/project-b", parent: "/", directories: [] }),
  });
  await second;
  requests[0].resolve({
    ok: true,
    json: async () => ({ path: "/project-a", parent: "/", directories: [] }),
  });
  await first;
  const state = vm.runInContext("state", app);
  assert.equal(state.workspaceBrowsePath, "/project-b");
  assert.equal(nodes.get("#workspace-path-input").value, "/project-b");
});

test("busy controls prevent destructive changes and unvalidated workspace switching", () => {
  const nodes = new Map();
  const app = controller({
    document: {
      addEventListener() {},
      querySelector(selector) {
        if (!nodes.has(selector)) nodes.set(selector, { disabled: false });
        return nodes.get(selector);
      },
      querySelectorAll: () => [],
    },
  });
  const state = vm.runInContext("state", app);
  state.workspacePath = "/current";
  state.workspaceBrowsePath = "/next";
  state.busy = true;
  app.syncBusyControls();
  [
    "#btn-send",
    "#act-new-chat",
    "#act-compact",
    "#btn-approve-plan",
    "#btn-switch-workspace",
  ].forEach((selector) => assert.equal(nodes.get(selector).disabled, true));
  state.busy = false;
  state.workspaceBrowsePath = "";
  app.syncBusyControls();
  assert.equal(nodes.get("#act-new-chat").disabled, false);
  assert.equal(nodes.get("#btn-switch-workspace").disabled, true);
  state.workspaceBrowsePath = "/next";
  app.syncBusyControls();
  assert.equal(nodes.get("#btn-switch-workspace").disabled, false);
});

test("typing a workspace path invalidates an outstanding directory browse", async () => {
  const nodes = new Map();
  [
    "#workspace-path-input",
    "#workspace-directory-list",
    "#btn-workspace-parent",
    "#workspace-browse-path",
  ].forEach((selector) => {
    nodes.set(selector, {
      value: "",
      textContent: "",
      innerHTML: "",
      querySelectorAll: () => [],
    });
  });
  let finish;
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
    },
    fetch: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  app.syncBusyControls = () => {};
  app.setWorkspaceStatus = () => {};
  const request = app.browseWorkspace("/old-folder");
  nodes.get("#workspace-path-input").value = "/newly-typed-folder";
  app.invalidateWorkspaceSelection();
  finish({
    ok: true,
    json: async () => ({ path: "/old-folder", parent: "/", directories: [] }),
  });
  await request;
  assert.equal(nodes.get("#workspace-path-input").value, "/newly-typed-folder");
  assert.equal(vm.runInContext("state.workspaceBrowsePath", app), "");
});

test("workspace snapshot boundaries discard buffered events from the previous project", () => {
  const app = controller();
  const snapshot = {
    cwd: "/new-project",
    workspace_generation: 2,
    timeline: [],
  };
  const events = app.eventsAfterSnapshot(snapshot, [
    {
      type: "content_delta",
      text: "old project response",
      workspace_generation: 1,
    },
    { type: "workspace_changed", workspace_generation: 2, state: snapshot },
    { type: "user_message", text: "new project task", workspace_generation: 2 },
  ]);
  assert.equal(
    events.some((event) => event.workspace_generation === 1),
    false,
  );
  assert.equal(
    events.some((event) => event.type === "workspace_changed"),
    false,
  );
  assert.equal(events.length, 1);
  assert.equal(events[0].text, "new project task");
});

test("late events from an older workspace generation cannot mutate the current chat", () => {
  const app = controller();
  const state = vm.runInContext("state", app);
  state.workspaceGeneration = 2;
  let rendered = 0;
  app.appendUserCard = () => {
    rendered += 1;
  };
  app.setBusyState = () => {};
  app.handleServerEvent({
    type: "user_message",
    text: "old",
    workspace_generation: 1,
  });
  assert.equal(rendered, 0);
  assert.equal(state.timelineRecords.length, 0);
});

test("collapsed pending plans stay collapsed across an unchanged snapshot", () => {
  const banner = element();
  const editor = { value: "", focus() {} };
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) =>
        selector === "#plan-banner" ? banner : editor,
    },
  });
  app.closeDrawers = () => {};
  app.renderPlanBanner({ pending: true, text: "Current plan" });
  app.closePlanEditor();
  app.renderPlanBanner({ pending: true, text: "Current plan" });
  assert.equal(banner.classList.contains("hidden"), true);
  app.openPlanEditor();
  assert.equal(banner.classList.contains("hidden"), false);
});

test("a stale remote model catalog cannot overwrite a newly edited model", async () => {
  const nodes = new Map();
  [
    "#editor-name",
    "#editor-provider",
    "#editor-url",
    "#editor-model-id",
    "#editor-api-key",
    "#editor-key-env",
    "#editor-fetched-models",
  ].forEach((selector) => {
    nodes.set(selector, Object.assign(element(), { value: "", innerHTML: "" }));
  });
  nodes.get("#editor-url").value = "https://old.example.invalid/v1";
  let finish;
  const app = controller({
    document: {
      addEventListener() {},
      querySelector: (selector) => nodes.get(selector),
    },
    fetch: () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  });
  app.setEditorStatus = () => {};
  const pending = app.fetchRemoteModels();
  nodes.get("#editor-url").value = "https://new.example.invalid/v1";
  nodes.get("#editor-model-id").value = "new-user-choice";
  app.invalidateModelEditor();
  finish({
    ok: true,
    json: async () => ({ ok: true, models: ["old-server-model"] }),
  });
  await pending;
  assert.equal(nodes.get("#editor-model-id").value, "new-user-choice");
  assert.equal(nodes.get("#editor-fetched-models").innerHTML, "");
  assert.equal(
    nodes.get("#editor-fetched-models").classList.contains("hidden"),
    true,
  );
});

test("a delayed clear response cannot restore an older workspace", () => {
  const app = controller();
  const state = vm.runInContext("state", app);
  state.workspacePath = "/new-project";
  state.workspaceGeneration = 2;
  state.planPending = true;
  state.lastPlanText = "New project plan";
  let hydrated = 0;
  let loaded = 0;
  app.hydrateSnapshot = () => {
    hydrated += 1;
  };
  app.loadSkills = () => {
    loaded += 1;
  };
  app.applyClearedState({
    cwd: "/old-project",
    workspace_generation: 1,
    timeline: [],
  });
  assert.equal(hydrated, 0);
  assert.equal(loaded, 0);
  assert.equal(state.workspacePath, "/new-project");
  assert.equal(state.workspaceGeneration, 2);
  assert.equal(state.planPending, true);
  assert.equal(state.lastPlanText, "New project plan");
});

test("terminal events retain the server reservation until its idle snapshot", () => {
  const app = controller();
  const state = vm.runInContext("state", app);
  app.setBusyState = (busy) => {
    state.busy = busy;
  };
  app.finalizeStreamingAssistantCard = () => {};
  app.appendNoticeCard = () => {};
  app.updateTopbar = (snapshot) => app.setBusyState(snapshot.busy);
  for (const event of [
    { type: "turn_completed", content: "done", busy: true },
    { type: "turn_failed", message: "failed", busy: true },
    { type: "turn_completed", snapshotApplied: true, busy: true },
  ]) {
    app.handleServerEvent(event);
    assert.equal(state.busy, true);
    app.handleServerEvent({ type: "state_updated", state: { busy: false } });
    assert.equal(state.busy, false);
  }
});

test("replayed terminal overlap inherits the newer snapshot reservation", () => {
  const app = controller();
  for (const busy of [true, false]) {
    const replay = app.eventsAfterSnapshot(
      { busy, timeline: [{ kind: "assistant", text: "done" }] },
      [{ type: "turn_completed", content: "done", busy: true }],
    );
    assert.equal(replay.length, 1);
    assert.equal(replay[0].snapshotApplied, true);
    assert.equal(replay[0].busy, busy);
  }
});
