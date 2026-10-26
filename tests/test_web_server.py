"""Tests for Neow Web Studio HTTP + SSE server and WebSessionBridge."""

from __future__ import annotations

import json
from pathlib import Path
import queue
import subprocess
import threading
from types import SimpleNamespace

import pytest
import requests

from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.cancellation import CancelToken
from neow.core.checkpoints import CheckpointStore
from neow.core.config import Config
from neow.core.context import ContextManager
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.goal import GoalState
from neow.core.hooks import HookRunner
from neow.core.mcp_client import ServerConfig, ServerState
from neow.core.token_tracker import TokenTracker
from neow.core.tools_registry import ToolSpec
from neow.models.base import StreamChunk
from neow.tools.command import get_session_cwd, reset_session_cwd, set_session_cwd
from neow.tui.bridge.events import ToolFinished, ToolStarted, TurnCompleted
from neow.web.server import WebServer, WebSessionBridge


class _FakeStreamChunk:
    def __init__(self, content_delta: str = "", progress=None):
        self.content_delta = content_delta
        self.reasoning_delta = ""
        self.progress = progress
        self.usage = {"input_tokens": 10, "output_tokens": 5}
        self.cancelled = False


class _FakeConversation:
    def __init__(self):
        self.model_client = SimpleNamespace(
            config_name="deepseek",
            model="deepseek-chat",
            effort="medium",
            validate_connection=lambda: True,
            chat=lambda msgs: SimpleNamespace(content="## Step 1\nBuild feature"),
        )
        self.tool_executor = SimpleNamespace(
            approval_policy=ApprovalPolicy(mode=ApprovalMode.WRITE),
            approval_callback=None,
        )
        self.ask_user_callback = None
        self.token_tracker = SimpleNamespace(
            total_input_tokens=10,
            total_output_tokens=5,
            total_tokens=15,
            total_cost=0.0012,
            check_max_tokens=lambda: False,
        )
        self.todos = [{"content": "Write web server", "status": "completed"}]
        self.messages = []

    def get_response_stream(self, prompt: str, cancel=None):
        yield _FakeStreamChunk(content_delta=f"Echo: {prompt}")

    def clear_history(self):
        self.messages.clear()

    def compact(self):
        return "Compacted 4 messages."


def test_web_server_endpoints_and_static_assets(tmp_path):
    cfg = Config(tmp_path / "config.json")
    conv = _FakeConversation()
    bridge = WebSessionBridge(conv, config=cfg)
    server = WebServer(bridge, host="127.0.0.1", port=0)
    url = server.start_background()

    try:
        # 1. Static index.html, styles.css, app.js
        r_html = requests.get(f"{url}/", timeout=5)
        assert r_html.status_code == 200
        assert "Neow Web Studio" in r_html.text

        r_css = requests.get(f"{url}/styles.css", timeout=5)
        assert r_css.status_code == 200
        assert "--accent" in r_css.text

        r_js = requests.get(f"{url}/app.js", timeout=5)
        assert r_js.status_code == 200
        assert "connectSSE" in r_js.text

        # 2. State & models catalog
        state = requests.get(f"{url}/api/state", timeout=5).json()
        assert state["active_model"] == "deepseek"
        assert state["approval_mode"] == "write"
        assert len(state["todos"]) == 1

        models = requests.get(f"{url}/api/models", timeout=5).json()
        assert len(models["presets"]) >= 11

        # 3. Mode & effort toggle
        mode_res = requests.post(
            f"{url}/api/mode",
            json={"approval_mode": "yolo", "effort": "high"},
            timeout=5,
        ).json()
        assert mode_res["approval_mode"] == "yolo"
        assert mode_res["effort"] == "high"

        # 4. Save and delete custom model
        save_res = requests.post(
            f"{url}/api/models/save",
            json={
                "name": "local-ollama",
                "provider": "openai-compatible",
                "base_url": "http://127.0.0.1:11434/v1",
                "model": "qwen2.5-coder:7b",
                "activate": False,
            },
            timeout=5,
        ).json()
        assert save_res["ok"] is True
        assert "local-ollama" in cfg.models

        del_res = requests.post(
            f"{url}/api/models/delete",
            json={"name": "local-ollama"},
            timeout=5,
        ).json()
        assert del_res["ok"] is True
        assert "local-ollama" not in cfg.models

        # 5. Chat turn execution
        sub = bridge.broadcaster.subscribe()
        chat_res = requests.post(
            f"{url}/api/chat", json={"prompt": "Hello Web"}, timeout=5
        ).json()
        assert chat_res["ok"] is True

        seen_types = set()
        for _ in range(10):
            ev = sub.get(timeout=5)
            seen_types.add(ev["type"])
            if ev["type"] == "turn_completed":
                assert "Echo: Hello Web" in ev["content"]
                break
        assert "user_message" in seen_types
        assert "turn_completed" in seen_types
        bridge.broadcaster.unsubscribe(sub)

        # 6. Plan generation & approval
        plan_res = requests.post(
            f"{url}/api/plan",
            json={"action": "generate", "task": "Add dark mode"},
            timeout=5,
        ).json()
        assert plan_res["ok"] is True
        assert "Step 1" in plan_res["text"]
    finally:
        server.shutdown()


def test_web_bridge_approval_and_ask_user_and_file_diff(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config(tmp_path / "config.json")
    conv = _FakeConversation()
    bridge = WebSessionBridge(conv, config=cfg)

    # Test approval bridge resolution from worker thread
    sub = bridge.broadcaster.subscribe()
    approval_result = []

    def worker_approve():
        ok = conv.tool_executor.approval_callback(
            "execute_command", {"command": "npm test"}, "Run tests"
        )
        approval_result.append(ok)

    t = threading.Thread(target=worker_approve, daemon=True)
    t.start()

    ev = sub.get(timeout=5)
    assert ev["type"] == "approval_request"
    assert bridge.resolve_approval(ev["id"], "allow_once") is True
    t.join(timeout=5)
    assert approval_result == [True]

    # Drain approval_resolved event
    resolved_ev = sub.get(timeout=5)
    assert resolved_ev["type"] == "approval_resolved"

    # Test ask_user bridge resolution from worker thread
    ask_result = []

    def worker_ask():
        ans = conv.ask_user_callback("Which port?", ["7860", "8080"])
        ask_result.append(ans)

    t2 = threading.Thread(target=worker_ask, daemon=True)
    t2.start()

    q_ev = sub.get(timeout=5)
    assert q_ev["type"] == "ask_user_request"
    assert bridge.resolve_ask_user(q_ev["id"], "7860") is True
    t2.join(timeout=5)
    assert ask_result == ["7860"]

    # Drain ask_user_resolved
    sub.get(timeout=5)

    # Test automatic unified diff generation on write_file / edit_file
    demo_file = tmp_path / "hello.py"
    demo_file.write_text("print('old')\n", encoding="utf-8")

    bridge._on_controller_event(
        ToolStarted(
            name="edit_file",
            args={"path": str(demo_file)},
            call_id="call-1",
        )
    )
    demo_file.write_text("print('new')\n", encoding="utf-8")
    bridge._on_controller_event(
        ToolFinished(
            name="edit_file",
            result="Edited hello.py",
            is_error=False,
            denied=False,
            call_id="call-1",
        )
    )

    # Check tool_finished event includes unified diff
    ev1 = sub.get(timeout=5)
    ev2 = sub.get(timeout=5)
    finished = ev2 if ev2["type"] == "tool_finished" else ev1
    assert finished["type"] == "tool_finished"
    assert "-print('old')" in finished["diff"]
    assert "+print('new')" in finished["diff"]
    bridge.broadcaster.unsubscribe(sub)


@pytest.fixture
def real_web(tmp_path, monkeypatch):
    """Use production conversation contracts without a networked model or user files."""
    root = tmp_path / "project-a"
    root.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        "neow.web.server.get_background_manager",
        lambda: SimpleNamespace(list_tasks=lambda: []),
    )
    cfg = Config(root / "config.json")
    executor = ToolExecutor()
    tracker = TokenTracker(cfg)
    model = SimpleNamespace(
        config_name="test-model",
        model="gpt-4o",
        effort="medium",
        validate_connection=lambda: True,
        chat=lambda messages: SimpleNamespace(content="A safe test plan", usage={}),
    )
    conv = ConversationManager(model, executor, ContextManager(str(root)), tracker)
    checkpoints = CheckpointStore(root=tmp_path / "checkpoints")
    conv.checkpoints = executor.checkpoints = checkpoints
    bridge = WebSessionBridge(
        conv,
        config=cfg,
        token_tracker=tracker,
        approval_policy=ApprovalPolicy(mode=ApprovalMode.WRITE),
    )
    server = WebServer(bridge, host="127.0.0.1", port=0)
    url = server.start_background()
    try:
        yield SimpleNamespace(
            root=root,
            url=url,
            cfg=cfg,
            conv=conv,
            executor=executor,
            tracker=tracker,
            bridge=bridge,
            model=model,
            tmp=tmp_path,
        )
    finally:
        server.shutdown()
        reset_session_cwd()


def _post(web, route, body=None):
    return requests.post(web.url + route, json=body or {}, timeout=5)


def _defer_workers(monkeypatch):
    started = []

    # Windows subprocess pipe readers also use threading.Thread.
    monkeypatch.setattr(WebSessionBridge, "_git_branch", staticmethod(lambda: ""))

    class DeferredThread:
        def __init__(self, target, args=(), kwargs=None, **options):
            self.target = target
            self.args = args
            self.kwargs = kwargs or {}

        def start(self):
            started.append(self)

        def run(self):
            self.target(*self.args, **self.kwargs)

    monkeypatch.setattr("neow.web.server.threading.Thread", DeferredThread)
    return started


def test_real_tool_executor_uses_web_approval_and_question_callbacks(real_web):
    web = real_web
    web.executor.register_tool("test_write", lambda: "written", tier=ApprovalTier.WRITE)
    events = web.bridge.broadcaster.subscribe()
    results = []
    worker = threading.Thread(
        target=lambda: results.append(web.executor.execute("test_write", {})),
        daemon=True,
    )
    worker.start()
    approval = events.get(timeout=3)
    assert approval["type"] == "approval_request"
    assert web.bridge.resolve_approval(approval["id"], "allow_once")
    worker.join(timeout=3)
    assert results == ["written"]
    assert events.get(timeout=3)["type"] == "approval_resolved"

    answers = []
    worker = threading.Thread(
        target=lambda: answers.append(web.conv.ask_user("Which port?", ["7860"])),
        daemon=True,
    )
    worker.start()
    question = events.get(timeout=3)
    assert question["type"] == "ask_user_request"
    assert web.bridge.resolve_ask_user(question["id"], "7860")
    worker.join(timeout=3)
    assert answers == ["User answered: 7860"]
    web.bridge.broadcaster.unsubscribe(events)


def test_web_usage_reads_real_token_tracker_contract(real_web):
    web = real_web
    web.tracker.record({"prompt_tokens": 10000, "completion_tokens": 2000}, "gpt-4o")
    usage = requests.get(web.url + "/api/state", timeout=5).json()["usage"]
    assert usage["input_tokens"] == 10000
    assert usage["output_tokens"] == 2000
    assert usage["total_tokens"] == 12000
    assert usage["cost"] == pytest.approx(0.045)


def test_web_branch_uses_existing_git_command(real_web):
    subprocess.run(
        ["git", "init", "--initial-branch=web-test"],
        cwd=real_web.root,
        capture_output=True,
        check=True,
    )
    assert real_web.bridge.get_state_snapshot()["git_branch"] == "web-test"


def test_workspace_switch_rebuilds_project_state_and_keeps_selected_model(real_web):
    web = real_web
    other = web.tmp / "project-b"
    other.mkdir()
    (other / "NEOW.md").write_text("Project B specific instructions", encoding="utf-8")
    (other / "new.py").write_text("print('new workspace')", encoding="utf-8")
    old_checkpoint = web.conv.checkpoints
    web.conv.messages.append({"role": "user", "content": "old project task"})
    web.conv.context_files[str(web.root / "old.py")] = "old project content"
    web.conv.context_manager.file_cache["old.py"] = "old cache"
    web.conv._structure_injected = True
    web.conv._structure_text = "old project structure"
    web.conv._pending_images.append({"type": "image"})
    web.conv.pending_lint_feedback = "old lint error"
    web.executor._known_files[str(web.root / "old.py")] = "old digest"
    web.bridge.current_plan = "old plan"
    web.bridge.plan_pending_approval = True
    web.bridge.active_skills.add("old-skill")
    set_session_cwd(web.root)
    before = web.bridge.get_state_snapshot().get("workspace_generation", 0)

    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert Path.cwd() == other.resolve()
    assert Path(data["state"]["cwd"]) == other.resolve()
    assert data["state"]["workspace_generation"] > before
    assert web.conv.model_client is web.model
    assert web.conv.context_manager.project_root.resolve() == other.resolve()
    assert web.conv.context_manager.file_cache == {}
    assert web.conv.messages == []
    assert web.conv.context_files == {}
    assert web.conv._pending_images == []
    assert not web.conv.pending_lint_feedback
    assert web.executor._known_files == {}
    assert web.conv.checkpoints is web.executor.checkpoints
    assert web.conv.checkpoints is not old_checkpoint
    assert "Project B specific instructions" in web.conv.memory.text
    assert web.bridge.current_plan == ""
    assert web.bridge.active_skills == set()
    assert get_session_cwd() in (None, other.resolve())


def test_workspace_switch_does_not_rebase_relative_model_config(real_web):
    web = real_web
    config_file = web.root / "relative.json"
    config_file.write_text("{}", encoding="utf-8")
    web.cfg.source_path = Path("relative.json")
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code == 200, response.text
    assert web.cfg.source_path.resolve() == config_file
    assert not (other / "relative.json").exists()


def test_workspace_switch_archives_a_plan_only_session(real_web):
    web = real_web
    web.bridge.current_plan = "Preserve this unexecuted plan"
    web.bridge.plan_pending_approval = True
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code == 200, response.text
    archives = list((web.tmp / "home" / ".neow" / "sessions").glob("web_*.json"))
    assert len(archives) == 1
    archived = json.loads(archives[0].read_text(encoding="utf-8"))
    assert archived["plan"] == "Preserve this unexecuted plan"
    assert Path(archived["cwd"]) == web.root
    assert web.bridge.current_plan == ""


@pytest.mark.parametrize(
    "route,body",
    [
        ("/api/chat", {"prompt": "stale project task"}),
        ("/api/clear", {}),
        ("/api/goal", {"action": "start", "goal": "stale goal"}),
        ("/api/goal", {"action": "stop"}),
        ("/api/cancel", {}),
        ("/api/workspaces/switch", {}),
    ],
)
def test_mutations_from_an_older_workspace_generation_are_rejected(
    real_web, route, body
):
    web = real_web
    old_generation = web.bridge.workspace_generation
    other = web.tmp / "project-b"
    other.mkdir()
    assert _post(web, "/api/workspaces/switch", {"path": str(other)}).status_code == 200
    web.conv.messages.append({"role": "user", "content": "new workspace task"})
    before = web.bridge.get_state_snapshot()
    payload = {**body, "workspace_generation": old_generation}
    if route.endswith("/switch"):
        payload["path"] = str(web.root)
    response = _post(web, route, payload)
    assert response.status_code == 409, response.text
    assert Path.cwd() == other
    assert web.conv.messages == [{"role": "user", "content": "new workspace task"}]
    assert web.bridge.get_state_snapshot() == before


def test_mutation_with_matching_workspace_generation_succeeds(real_web):
    web = real_web
    generation = web.bridge.workspace_generation
    web.conv.messages.append({"role": "user", "content": "clear current workspace"})
    response = _post(web, "/api/clear", {"workspace_generation": generation})
    assert response.status_code == 200, response.text
    assert web.conv.messages == []
    assert response.json()["state"]["workspace_generation"] > generation


def test_invalid_workspace_switch_is_atomic(real_web):
    web = real_web
    context = web.conv.context_manager
    web.conv.messages.append({"role": "user", "content": "keep me"})
    old_history = list(web.conv.messages)
    response = _post(web, "/api/workspaces/switch", {"path": str(web.tmp / "missing")})
    assert response.status_code in (400, 404, 409)
    assert Path.cwd() == web.root
    assert web.conv.context_manager is context
    assert web.conv.messages == old_history


def test_workspace_switch_rejects_busy_and_running_background_tasks(
    real_web, monkeypatch
):
    web = real_web
    other = web.tmp / "project-b"
    other.mkdir()
    web.bridge.controller._busy = True
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code in (400, 409)
    assert Path.cwd() == web.root
    web.bridge.controller._busy = False
    monkeypatch.setattr(
        "neow.web.server.get_background_manager",
        lambda: SimpleNamespace(list_tasks=lambda: [SimpleNamespace(is_running=True)]),
    )
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code in (400, 409)
    assert Path.cwd() == web.root


def test_workspace_switch_rejects_project_owned_config(real_web):
    web = real_web
    project_config = web.root / ".neow.json"
    project_config.write_text("{}", encoding="utf-8")
    web.cfg.source_path = project_config
    web.cfg.user_owned = False
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code in (400, 409), response.text
    assert Path.cwd() == web.root
    assert web.cfg.source_path == project_config


def test_workspace_switch_rejects_configured_shell_hooks(real_web):
    web = real_web
    hooks = HookRunner(
        {"pre_tool_use": [{"command": "./project-only-script"}]},
        cwd=str(web.root),
    )
    web.conv.hooks = hooks
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code in (400, 409), response.text
    assert Path.cwd() == web.root
    assert web.conv.hooks is hooks


def test_workspace_switch_rebinds_event_bus_only_hooks(real_web):
    web = real_web
    hooks = HookRunner(
        {},
        cwd=str(web.root),
        session_id="old-session",
        event_bus=SimpleNamespace(emit=lambda *args, **kwargs: None),
    )
    web.conv.hooks = hooks
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code == 200, response.text
    assert Path(web.conv.hooks.cwd) == other
    assert web.conv.hooks.session_id != "old-session"


@pytest.mark.parametrize(
    "source,transport,status,task_running,allowed",
    [
        ("project", "http", "connected", False, False),
        ("project", "http", "pending", False, False),
        ("project", "http", "failed", True, False),
        ("project", "stdio", "connected", False, False),
        ("user", "stdio", "connected", False, False),
        ("user", "stdio", "pending", False, False),
        ("user", "stdio", "failed", True, False),
        ("user", "http", "connected", False, True),
        ("project", "http", "disabled", False, True),
        ("project", "http", "failed", False, True),
        ("user", "stdio", "stopped", False, True),
    ],
)
def test_workspace_switch_respects_mcp_project_lifecycle(
    real_web, source, transport, status, task_running, allowed
):
    web = real_web
    config = ServerConfig(
        name="project-tool",
        source=source,
        url="https://example.invalid/mcp" if transport == "http" else "",
        command="never-start-this-command" if transport == "stdio" else "",
    )
    state = ServerState(config=config, status=status)
    state.task = SimpleNamespace(done=lambda: not task_running)
    web.conv.mcp = SimpleNamespace(states={config.name: state})
    other = web.tmp / "project-b"
    other.mkdir()
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    if allowed:
        assert response.status_code == 200, response.text
        assert Path.cwd() == other
    else:
        assert response.status_code in (400, 409), response.text
        assert Path.cwd() == web.root


def test_workspace_switch_rejects_active_goal_and_resets_session_approvals(real_web):
    web = real_web
    other = web.tmp / "project-b"
    other.mkdir()
    web.bridge.goal_state = GoalState(goal="active project task", active=True)
    web.bridge.approval_policy.set_tool_override("test_write", "allow")
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code in (400, 409), response.text
    assert Path.cwd() == web.root
    assert web.bridge.approval_policy.tool_overrides["test_write"] == "allow"
    web.bridge.goal_state.active = False
    response = _post(web, "/api/workspaces/switch", {"path": str(other)})
    assert response.status_code == 200, response.text
    assert "test_write" not in web.bridge.approval_policy.tool_overrides


def test_workspace_browser_only_lists_directories(real_web):
    web = real_web
    (web.root / "child").mkdir()
    (web.root / "file.txt").write_text("not a directory", encoding="utf-8")
    response = requests.get(
        web.url + "/api/workspaces/browse",
        params={"path": str(web.root)},
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert Path(data["path"]) == web.root
    assert Path(data["parent"]) == web.root.parent
    assert [entry["name"] for entry in data["directories"]] == ["child"]
    catalog = requests.get(web.url + "/api/workspaces", timeout=5).json()
    assert Path(catalog["current"]) == web.root
    assert isinstance(catalog["recent"], list)
    assert isinstance(catalog["roots"], list)


def test_submit_reserves_turn_before_worker_thread_starts(real_web, monkeypatch):
    with monkeypatch.context() as patch:
        started = _defer_workers(patch)
        assert real_web.bridge.submit_prompt("first") is True
        assert real_web.bridge.submit_prompt("second") is False
        assert len(started) == 1
        assert real_web.bridge.get_state_snapshot()["busy"] is True


def test_stop_before_worker_start_does_not_request_model(real_web, monkeypatch):
    web = real_web
    streamed = []

    def fake_stream(prompt, **kwargs):
        streamed.append(prompt)
        return iter(())

    web.conv.get_response_stream = fake_stream
    with monkeypatch.context() as patch:
        started = _defer_workers(patch)
        assert web.bridge.submit_prompt("cancel before worker starts") is True
    response = _post(web, "/api/cancel")
    assert response.status_code == 200, response.text
    assert len(started) == 1
    started[0].run()
    assert streamed == []
    assert web.bridge.get_state_snapshot()["busy"] is False


def test_stop_during_prelude_does_not_request_model(real_web, monkeypatch):
    web = real_web
    streamed = []
    token = CancelToken()
    monkeypatch.setattr(
        web.bridge.controller, "_prelude", lambda prompt: token.cancel()
    )
    monkeypatch.setattr(
        web.conv,
        "get_response_stream",
        lambda prompt, **kwargs: streamed.append(prompt) or iter(()),
    )
    events = web.bridge.broadcaster.subscribe()
    web.bridge.controller.run_turn("stop while fetching context", cancel_token=token)
    assert streamed == []
    assert events.get(timeout=1)["cancelled"] is True
    assert web.bridge.controller.busy is False
    web.bridge.broadcaster.unsubscribe(events)


def test_cancelled_tool_worker_keeps_workspace_reserved_until_it_exits(real_web):
    web = real_web
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    observed = []

    def delayed_tool():
        started.set()
        assert release.wait(5)
        observed.append(Path.cwd())
        finished.set()
        return "harmless completed tool"

    web.executor.register_spec(
        ToolSpec(
            name="delayed_read",
            description="Harmless blocking regression fixture",
            parameters={"type": "object", "properties": {}},
            func=delayed_tool,
            tier=ApprovalTier.READ,
            read_only=True,
            reports_progress=True,
        )
    )

    def scripted_stream(**kwargs):
        yield StreamChunk(
            tool_call_delta={
                "tool_calls": [
                    {
                        "id": "delayed-1",
                        "function": {"name": "delayed_read", "arguments": "{}"},
                    }
                ]
            }
        )

    web.model.chat_stream = scripted_stream
    other = web.tmp / "project-b"
    other.mkdir()
    events = web.bridge.broadcaster.subscribe()
    try:
        assert web.bridge.submit_prompt("run harmless delayed tool")
        assert started.wait(3)
        assert _post(web, "/api/cancel").status_code == 200
        assert web.bridge.get_state_snapshot()["busy"] is True
        response = _post(web, "/api/workspaces/switch", {"path": str(other)})
        assert response.status_code == 409, response.text
        assert Path.cwd() == web.root
    finally:
        release.set()
        assert finished.wait(3)
        for _ in range(100):
            try:
                event = events.get(timeout=3)
            except queue.Empty:
                break
            if event["type"] == "state_updated" and not event["state"]["busy"]:
                break
        web.bridge.broadcaster.unsubscribe(events)
    assert web.bridge.get_state_snapshot()["busy"] is False
    assert observed == [web.root]
    assert _post(web, "/api/workspaces/switch", {"path": str(other)}).status_code == 200


def test_autonomous_round_gap_stays_reserved_and_stop_prevents_continuation(
    real_web, monkeypatch
):
    web = real_web
    turns = []
    gap_checks = []

    def fake_turn(prompt, **kwargs):
        turns.append(prompt)
        web.bridge._on_controller_event(
            TurnCompleted(content="More work remains", usage=None, cancelled=False)
        )

    def stop_in_gap(seconds):
        gap_checks.append(seconds)
        assert web.bridge.get_state_snapshot()["busy"] is True
        assert web.bridge.submit_prompt("conflicting user turn") is False
        web.bridge.cancel()

    monkeypatch.setattr(web.bridge.controller, "run_turn", fake_turn)
    monkeypatch.setattr("neow.web.server.time.sleep", stop_in_gap)
    with monkeypatch.context() as patch:
        started = _defer_workers(patch)
        assert web.bridge.start_goal("finish the project") is True
    assert len(started) == 1
    started[0].run()
    assert len(turns) == 1
    assert gap_checks == [0.3]
    assert web.bridge.goal_state.active is False
    assert web.bridge.get_state_snapshot()["busy"] is False
    assert len(web.bridge.timeline) == 2


@pytest.mark.parametrize("kind", ["approval", "ask_user"])
def test_cancellation_cannot_publish_resolution_before_request(
    real_web, monkeypatch, kind
):
    web = real_web
    before_publish = threading.Event()
    release_publish = threading.Event()
    cancel_started = threading.Event()
    cancel_done = threading.Event()
    published = []
    original_publish = web.bridge.broadcaster.publish

    def delayed_publish(event_type, payload):
        if event_type == f"{kind}_request":
            before_publish.set()
            assert release_publish.wait(3)
        published.append(event_type)
        original_publish(event_type, payload)

    monkeypatch.setattr(web.bridge.broadcaster, "publish", delayed_publish)
    answers = []

    def callback():
        if kind == "approval":
            return web.executor.approval_callback("test_write", {}, "test approval")
        return web.conv.ask_user_callback("test question", [])

    requester = threading.Thread(target=lambda: answers.append(callback()), daemon=True)

    def cancel():
        cancel_started.set()
        web.bridge.cancel()
        cancel_done.set()

    stopper = threading.Thread(target=cancel, daemon=True)
    try:
        requester.start()
        assert before_publish.wait(2)
        stopper.start()
        assert cancel_started.wait(2)
        cancel_done.wait(0.1)
    finally:
        release_publish.set()
        requester.join(timeout=3)
        if stopper.ident is not None:
            stopper.join(timeout=3)
    assert not requester.is_alive()
    assert not stopper.is_alive()
    assert published.index(f"{kind}_request") < published.index(f"{kind}_resolved")
    assert answers == ([False] if kind == "approval" else [""])


def test_file_references_load_plain_quoted_and_windows_paths(real_web, monkeypatch):
    web = real_web
    (web.root / "plain.py").write_text("PLAIN_SOURCE", encoding="utf-8")
    (web.root / "space name.py").write_text("QUOTED_SOURCE", encoding="utf-8")
    folder = web.root / "nested"
    folder.mkdir()
    (folder / "win.py").write_text("WINDOWS_SOURCE", encoding="utf-8")
    nested_reference = str(Path("nested") / "win.py")
    prompt = f'Review @plain.py @"space name.py" @{nested_reference}'
    with monkeypatch.context() as patch:
        started = _defer_workers(patch)
        assert web.bridge.submit_prompt(prompt) is True
    assert len(started) == 1
    assert web.conv.context_files == {
        str((web.root / "plain.py").resolve()): "PLAIN_SOURCE",
        str((web.root / "space name.py").resolve()): "QUOTED_SOURCE",
        str((folder / "win.py").resolve()): "WINDOWS_SOURCE",
    }
    assert web.bridge.timeline[-1]["text"] == prompt


@pytest.mark.parametrize(
    "bad_reference",
    ["missing", "outside", "absolute_outside", "binary", "directory", "unclosed"],
)
def test_invalid_file_reference_rejects_whole_submission(real_web, bad_reference):
    web = real_web
    (web.root / "valid.py").write_text("VALID_SOURCE", encoding="utf-8")
    (web.tmp / "outside.py").write_text("PRIVATE_SOURCE", encoding="utf-8")
    (web.root / "binary.bin").write_bytes(b"text\x00binary")
    (web.root / "directory").mkdir()
    reference = {
        "missing": "@missing.py",
        "outside": "@../outside.py",
        "absolute_outside": f'@"{web.tmp / "outside.py"}"',
        "binary": "@binary.bin",
        "directory": "@directory",
        "unclosed": '@"unterminated path.py',
    }[bad_reference]
    existing = str(web.root / "existing.py")
    web.conv.context_files[existing] = "preserve existing context"
    web.bridge.timeline.append({"kind": "user", "text": "preserve prior turn"})
    before_timeline = list(web.bridge.timeline)
    response = _post(web, "/api/chat", {"prompt": f"Review @valid.py {reference}"})
    assert response.status_code == 400, response.text
    assert web.conv.context_files == {existing: "preserve existing context"}
    assert web.bridge.timeline == before_timeline
    assert web.bridge.get_state_snapshot()["busy"] is False


@pytest.mark.parametrize("limit", ["file_count", "total_characters"])
def test_file_reference_limits_reject_before_context_changes(real_web, limit):
    web = real_web
    if limit == "file_count":
        paths = [web.root / f"file-{index}.py" for index in range(17)]
        for path in paths:
            path.write_text("x", encoding="utf-8")
    else:
        paths = [web.root / "one.py", web.root / "two.py"]
        for path in paths:
            path.write_text("x" * 110_000, encoding="utf-8")
    prompt = "Review " + " ".join(f"@{path.name}" for path in paths)
    response = _post(web, "/api/chat", {"prompt": prompt})
    assert response.status_code == 400, response.text
    assert web.conv.context_files == {}
    assert web.bridge.timeline == []
    assert web.bridge.get_state_snapshot()["busy"] is False


def test_stop_resolves_blocked_approval_and_question_futures(real_web):
    web = real_web
    events = web.bridge.broadcaster.subscribe()
    answers = []
    approvals = []
    approval_worker = threading.Thread(
        target=lambda: approvals.append(
            web.executor.approval_callback("test", {}, "approve")
        ),
        daemon=True,
    )
    question_worker = threading.Thread(
        target=lambda: answers.append(web.conv.ask_user_callback("Continue?", [])),
        daemon=True,
    )
    approval_worker.start()
    assert events.get(timeout=3)["type"] == "approval_request"
    question_worker.start()
    assert events.get(timeout=3)["type"] == "ask_user_request"
    response = _post(web, "/api/cancel")
    assert response.status_code == 200
    approval_worker.join(timeout=2)
    question_worker.join(timeout=2)
    assert approvals == [False]
    assert answers == [""]
    assert web.bridge.get_state_snapshot()["pending_approvals"] == []
    assert web.bridge.get_state_snapshot()["pending_questions"] == []
    web.bridge.broadcaster.unsubscribe(events)


def test_clear_does_not_mutate_history_of_an_active_worker(real_web):
    web = real_web
    web.bridge.controller._busy = True
    web.bridge.goal_state = GoalState(goal="keep running", active=True)
    web.conv.messages.append({"role": "user", "content": "in-flight"})
    response = _post(web, "/api/clear")
    assert response.status_code in (400, 409)
    assert web.conv.messages == [{"role": "user", "content": "in-flight"}]
    assert web.bridge.goal_state.active is True


def test_clear_resets_goal_plan_skills_and_reports_fresh_state(real_web):
    web = real_web
    web.bridge.goal_state = GoalState(goal="between rounds", active=True)
    web.bridge.current_plan = "old plan"
    web.bridge.plan_pending_approval = True
    web.bridge.active_skills.add("old-skill")
    web.conv.messages.append({"role": "user", "content": "old message"})
    response = _post(web, "/api/clear")
    assert response.status_code == 200, response.text
    state = response.json()["state"]
    assert state["timeline"] == []
    assert state["goal"]["active"] is False
    assert state["plan"]["pending"] is False
    assert not web.bridge.active_skills
    assert not web.conv.messages


def test_plan_approval_while_busy_preserves_pending_plan(real_web):
    web = real_web
    web.bridge.current_plan = "awaiting approval"
    web.bridge.plan_pending_approval = True
    web.bridge.controller._busy = True
    response = _post(web, "/api/plan", {"action": "approve", "plan": "edited plan"})
    assert response.status_code in (400, 409) or response.json().get("ok") is False
    assert web.bridge.plan_pending_approval is True
    assert web.bridge.current_plan == "awaiting approval"


@pytest.mark.parametrize(
    "route,body",
    [
        ("/api/plan", {"action": "generate", "task": "plan a change"}),
        ("/api/compact", {}),
    ],
)
def test_busy_state_blocks_other_model_work(real_web, route, body):
    web = real_web
    web.bridge.controller._busy = True
    calls = []
    web.model.chat = lambda messages: calls.append(messages)
    response = _post(web, route, body)
    assert response.status_code in (400, 409) or response.json().get("ok") is False
    assert calls == []


def test_model_save_reports_activation_failure_truthfully(real_web, monkeypatch):
    web = real_web

    def fail_activation(name):
        raise ValueError("Gateway unavailable")

    monkeypatch.setattr(web.bridge, "select_model", fail_activation)
    response = _post(
        web,
        "/api/models/save",
        {
            "name": "saved-only",
            "provider": "openai-compatible",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "local-test",
            "activate": True,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["saved"] == "saved-only"
    assert data["activated"] is False
    assert "Gateway unavailable" in data["activation_error"]
    assert web.conv.model_client is web.model


def test_edit_model_connection_test_retains_saved_key(real_web, monkeypatch):
    web = real_web
    web.cfg.save_model(
        "edited",
        {
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "model": "fake-model",
            "api_key": "fake-regression-key",
        },
    )
    seen = []

    def fake_client(entry, name):
        seen.append(dict(entry))
        return SimpleNamespace(validate_connection=lambda: True)

    monkeypatch.setattr("neow.web.server.build_model_client", fake_client)
    response = _post(
        web,
        "/api/models/test",
        {
            "name": "edited",
            "is_edit": True,
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "model": "fake-model",
            "api_key": "",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    assert seen[0]["api_key"] == "fake-regression-key"


def test_edit_model_catalog_fetch_retains_saved_key(real_web, monkeypatch):
    web = real_web
    web.cfg.save_model(
        "edited",
        {
            "provider": "openai-compatible",
            "base_url": "https://example.invalid/v1",
            "model": "fake-model",
            "api_key": "fake-regression-key",
        },
    )
    seen = []

    def fake_fetch(base_url, **kwargs):
        seen.append(kwargs)
        return [{"id": "fake-model"}]

    monkeypatch.setattr("neow.web.server.fetch_endpoint_models", fake_fetch)
    response = _post(
        web,
        "/api/models/fetch",
        {
            "name": "edited",
            "is_edit": True,
            "base_url": "https://example.invalid/v1",
            "api_key": "",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["models"] == ["fake-model"]
    assert seen[0]["api_key"] == "fake-regression-key"


def test_disabling_skill_removes_its_instructions(real_web):
    web = real_web
    skill_dir = web.root / ".neow" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    marker = "UNIQUE_TEST_SKILL_INSTRUCTION"
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: test-skill\ndescription: regression test\n---\n{marker}",
        encoding="utf-8",
    )
    response = _post(web, "/api/skills/toggle", {"name": "test-skill"})
    assert response.json()["active"] is True
    assert any(marker in str(message.get("content")) for message in web.conv.messages)
    response = _post(web, "/api/skills/toggle", {"name": "test-skill"})
    assert response.json()["active"] is False
    assert not any(
        marker in str(message.get("content")) for message in web.conv.messages
    )


def test_file_search_finds_files_beyond_initial_listing_limit(real_web):
    web = real_web
    for index in range(225):
        (web.root / f"early-{index:03}.txt").write_text("x", encoding="utf-8")
    (web.root / "zz-target-needle.py").write_text("pass", encoding="utf-8")
    response = requests.get(web.url + "/api/files", params={"q": "needle"}, timeout=5)
    data = response.json()
    assert data["query"] == "needle"
    assert [file["path"] for file in data["files"]] == ["zz-target-needle.py"]
    assert data["truncated"] is False


def test_file_tree_lists_only_direct_children_with_folders_first(real_web):
    web = real_web
    (web.root / "src" / "nested").mkdir(parents=True)
    (web.root / "empty").mkdir()
    (web.root / "src" / "app.py").write_text("pass", encoding="utf-8")
    (web.root / "src" / "nested" / "deep.py").write_text("pass", encoding="utf-8")
    (web.root / "README.md").write_text("# Demo", encoding="utf-8")
    for ignored in (".git", ".cache", "node_modules", "__pycache__", "dist"):
        (web.root / ignored).mkdir()
    (web.root / ".env").write_text("ignored", encoding="utf-8")
    (web.root / ".neow.json").write_text("{}", encoding="utf-8")

    response = requests.get(web.url + "/api/files/tree", timeout=5)
    assert response.status_code == 200, response.text
    listing = response.json()
    assert listing["path"] == ""
    assert listing["workspace_generation"] == web.bridge.workspace_generation
    assert [entry["name"] for entry in listing["entries"]] == [
        "empty",
        "src",
        ".neow.json",
        "README.md",
    ]
    assert listing["entries"][0]["kind"] == "directory"
    assert listing["entries"][-1]["kind"] == "file"
    assert listing["next_offset"] is None

    nested = requests.get(
        web.url + "/api/files/tree", params={"path": "src"}, timeout=5
    ).json()
    assert nested["entries"] == [
        {"name": "nested", "path": "src/nested", "kind": "directory"},
        {"name": "app.py", "path": "src/app.py", "kind": "file"},
    ]
    empty = requests.get(
        web.url + "/api/files/tree", params={"path": "empty"}, timeout=5
    ).json()
    assert empty["entries"] == []


def test_file_tree_pages_each_directory_without_hiding_later_files(real_web):
    web = real_web
    for index in range(205):
        (web.root / f"file-{index:03}.txt").write_text("x", encoding="utf-8")
    first = requests.get(web.url + "/api/files/tree", timeout=5).json()
    assert len(first["entries"]) == 200
    assert first["next_offset"] == 200
    second = requests.get(
        web.url + "/api/files/tree", params={"offset": 200}, timeout=5
    ).json()
    assert [entry["name"] for entry in second["entries"]] == [
        f"file-{index:03}.txt" for index in range(200, 205)
    ]
    assert second["next_offset"] is None


@pytest.mark.parametrize("path", ["../", "missing", "README.md", "../project-a-mimic"])
def test_file_tree_rejects_outside_missing_and_non_directory_paths(real_web, path):
    web = real_web
    (web.root / "README.md").write_text("# Demo", encoding="utf-8")
    (web.tmp / "project-a-mimic").mkdir(exist_ok=True)
    response = requests.get(
        web.url + "/api/files/tree", params={"path": path}, timeout=5
    )
    assert response.status_code == 400
    assert "error" in response.json()


def test_file_tree_rejects_absolute_paths_and_invalid_offsets(real_web):
    web = real_web
    for params in ({"path": str(web.tmp)}, {"offset": -1}, {"offset": "bad"}):
        response = requests.get(web.url + "/api/files/tree", params=params, timeout=5)
        assert response.status_code == 400, response.text


def test_file_tree_omits_external_links_and_directory_cycles(real_web):
    web = real_web
    outside = web.tmp / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("private", encoding="utf-8")
    try:
        (web.root / "outside-link").symlink_to(outside, target_is_directory=True)
        (web.root / "cycle").symlink_to(web.root, target_is_directory=True)
        (web.root / "secret-link.txt").symlink_to(outside / "secret.txt")
    except OSError:
        pytest.skip("Creating symlinks requires privileges on some Windows systems")
    listing = requests.get(web.url + "/api/files/tree", timeout=5).json()
    assert listing["entries"] == []
    response = requests.get(
        web.url + "/api/files/tree", params={"path": "outside-link"}, timeout=5
    )
    assert response.status_code == 400


def test_file_tree_omits_directory_aliases_without_platform_specific_apis(
    real_web, monkeypatch
):
    web = real_web
    alias = web.root / "junction"
    alias.mkdir()
    original_resolve = Path.resolve

    def resolve_alias(path, *args, **kwargs):
        if path == alias:
            return web.root
        return original_resolve(path, *args, **kwargs)

    # Simulate a Windows junction without requiring symlink privileges.
    monkeypatch.setattr(Path, "resolve", resolve_alias)
    listing = requests.get(web.url + "/api/files/tree", timeout=5).json()
    assert listing["entries"] == []


def test_local_server_rejects_foreign_origins_and_hosts(real_web):
    web = real_web
    foreign = {"Origin": "https://untrusted.example"}
    assert (
        requests.get(web.url + "/api/state", headers=foreign, timeout=5).status_code
        == 403
    )
    assert (
        requests.post(
            web.url + "/api/mode",
            json={"approval_mode": "yolo"},
            headers=foreign,
            timeout=5,
        ).status_code
        == 403
    )
    assert (
        requests.get(
            web.url + "/api/state",
            headers={"Host": "untrusted.example"},
            timeout=5,
        ).status_code
        == 403
    )
    response = requests.get(
        web.url + "/api/state", headers={"Origin": web.url}, timeout=5
    )
    assert response.status_code == 200
    assert response.headers.get("Access-Control-Allow-Origin") != "*"
    assert web.bridge.approval_policy.mode == ApprovalMode.WRITE
