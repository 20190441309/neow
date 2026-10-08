"""Approval bridge and modal tests (plan task 10)."""

import threading
from concurrent.futures import Future

from textual.app import App

from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.tui.bridge import ApprovalBridge
from neow.tui.screens.approval import ApprovalDecision, ApprovalModal, apply_decision
from tests.tui.conftest import FakeConversation, _chat_app


def test_bridge_allow_and_deny():
    allow = ApprovalBridge(
        request=lambda tool, params, reason, fut: fut.set_result(True)
    )
    assert allow("edit_file", {}, "write") is True
    deny = ApprovalBridge(
        request=lambda tool, params, reason, fut: fut.set_result(False)
    )
    assert deny("edit_file", {}, "write") is False


def test_bridge_timeout_denies():
    bridge = ApprovalBridge(request=lambda *args: None, timeout=0.01)
    assert bridge("edit_file", {}, "write") is False


def test_bridge_cancel_denies():
    def request(tool, params, reason, future):
        future.cancel()

    bridge = ApprovalBridge(request=request)
    assert bridge("edit_file", {}, "write") is False


def _modal_host(callback, **kwargs):
    class ModalHost(App):
        def on_mount(self):
            self.push_screen(ApprovalModal(**kwargs), callback)

    return ModalHost()


async def test_modal_keys_return_decision():
    cases = [
        ("y", ApprovalDecision.ALLOW_ONCE),
        ("a", ApprovalDecision.ALLOW_ALWAYS),
        ("n", ApprovalDecision.DENY),
        ("escape", ApprovalDecision.DENY),
    ]
    for key, expected in cases:
        results = []
        app = _modal_host(
            results.append,
            tool="execute_command",
            params={"command": "npm test"},
            reason="exec",
        )
        async with app.run_test() as pilot:
            await pilot.press(key)
            await pilot.pause()
        assert results == [expected], key


def test_always_sets_policy_override():
    policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    future = Future()
    apply_decision(ApprovalDecision.ALLOW_ALWAYS, policy, "execute_command", future)
    assert policy.tool_overrides["execute_command"] == "allow"
    assert future.result() is True


async def test_approval_flow_end_to_end():
    """Worker thread blocks on the bridge; modal resolves the future."""

    app = _chat_app(FakeConversation(script=[]))
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        result = {}

        def worker():
            result["approved"] = app.approval_bridge(
                "execute_command", {"command": "npm test"}, "exec"
            )

        thread = threading.Thread(target=worker)
        thread.start()
        await pilot.pause(0.4)
        await pilot.press("y")
        await pilot.pause(0.2)
        thread.join(timeout=5)
        assert result["approved"] is True


async def test_approval_fits_narrow_terminal():
    app = _modal_host(
        lambda decision: None,
        tool="execute_command",
        params={"command": "x" * 200},
        reason="review",
    )
    async with app.run_test(size=(40, 14)) as pilot:
        await pilot.pause()
        box = app.screen.query_one(".approval-box")
        assert box.region.x >= 0
        assert box.region.right <= 40
        assert box.region.bottom <= 14
