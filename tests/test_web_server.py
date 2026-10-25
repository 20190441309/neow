"""Tests for Neow Web Studio HTTP + SSE server and WebSessionBridge."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import requests

from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.config import Config
from neow.tui.bridge.events import ToolFinished, ToolStarted
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
            confirm_callback=None,
            ask_user_callback=None,
        )
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
        ok = conv.tool_executor.confirm_callback(
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
        ans = conv.tool_executor.ask_user_callback("Which port?", ["7860", "8080"])
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
