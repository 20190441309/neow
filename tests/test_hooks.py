"""User-configured hooks (plan task 5.1)."""

import json
import shlex
import sys
import time
from types import SimpleNamespace

from neow.core.agent_loop import AgentLoop
from neow.core.approval import ApprovalMode, ApprovalPolicy, ApprovalTier
from neow.core.executor import ToolExecutor
from neow.core.hooks import HookRunner, parse_hooks
from neow.core.plugin import EventBus
from neow.core.tools_registry import ToolSpec
from tests.test_agent_loop import _call, _conversation


def _script(tmp_path, name, body):
    """A Python hook script; returns the shell command that runs it."""
    path = tmp_path / f"{name}.py"
    path.write_text("import json, sys\npayload = json.load(sys.stdin)\n" + body)
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(path))}"


def _executor(calls):
    """Executor with a ``shout`` tool (exec tier) that records its arguments."""
    executor = ToolExecutor()

    def shout(text: str) -> str:
        calls.append(text)
        return text.upper()

    executor.register_spec(
        ToolSpec(
            name="shout",
            description="shout",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            func=shout,
            tier=ApprovalTier.EXEC,
        )
    )
    return executor


def _turn(hooks_config, calls, tmp_path, approve=None, script=None):
    executor = _executor(calls)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    executor.approval_callback = approve or (lambda *a: True)
    conv, client = _conversation(
        script
        or [{"tool_calls": [_call("c1", "shout", text="hi")]}, {"content": "ok"}],
        executor,
    )
    conv.hooks = HookRunner(hooks_config, session_id="s1", cwd=str(tmp_path))
    events = [c.progress for c in AgentLoop(conv).run("go") if c.progress]
    return conv, events, client


def _tool_result(conv):
    return next(m["content"] for m in conv.messages if m["role"] == "tool")


def test_pre_tool_hook_blocks_with_exit_2(tmp_path):
    calls, asked = [], []
    guard = _script(tmp_path, "guard", "sys.stderr.write('no shouting'); sys.exit(2)")
    hooks = {"pre_tool_use": [{"matcher": "shout", "command": guard}]}
    conv, events, _ = _turn(
        hooks, calls, tmp_path, approve=lambda *a: asked.append(a) or True
    )
    assert calls == [] and asked == []  # blocked before the approval prompt
    assert _tool_result(conv) == "Error: blocked by hook: no shouting"
    assert [e["status"] for e in events if e["type"] == "tool_end"] == ["denied"]

    # A matcher for another tool leaves this one alone.
    calls = []
    other = {"pre_tool_use": [{"matcher": "edit_file|write_file", "command": guard}]}
    conv, _, _ = _turn(other, calls, tmp_path)
    assert calls == ["hi"] and _tool_result(conv) == "HI"


def test_hook_can_rewrite_input(tmp_path):
    calls = []
    rewrite = _script(
        tmp_path,
        "rewrite",
        "text = payload['tool_input']['text']\n"
        "print(json.dumps({'tool_input': {'text': text + ' (checked)'}}))\n",
    )
    conv, _, _ = _turn(
        {
            "PreToolUse": [
                {"matcher": "shout", "hooks": [{"type": "command", "command": rewrite}]}
            ]
        },
        calls,
        tmp_path,
    )
    assert calls == ["hi (checked)"]
    assert _tool_result(conv) == "HI (CHECKED)"

    # JSON decision "block" with exit 0 also blocks.
    calls = []
    deny = _script(
        tmp_path, "deny", "print(json.dumps({'decision': 'block', 'reason': 'nope'}))"
    )
    conv, _, _ = _turn({"pre_tool_use": [{"command": deny}]}, calls, tmp_path)
    assert calls == [] and "nope" in _tool_result(conv)


def test_hook_timeout_does_not_block_loop(tmp_path):
    calls = []
    slow = _script(tmp_path, "slow", "import time; time.sleep(10)")
    broken = _script(tmp_path, "broken", "sys.exit(1)")
    hooks = {
        "pre_tool_use": [
            {"command": slow, "timeout": 0.5},
            {"command": broken},
            {"command": "/nonexistent/hook-binary"},
        ]
    }
    started = time.monotonic()
    conv, _, _ = _turn(hooks, calls, tmp_path)
    assert time.monotonic() - started < 5
    assert calls == ["hi"] and _tool_result(conv) == "HI"  # warnings only


def test_post_tool_hook_receives_output(tmp_path):
    calls = []
    log = tmp_path / "post.json"
    record = _script(
        tmp_path,
        "record",
        f"open({str(log)!r}, 'w').write(json.dumps(payload))\n"
        "print(json.dumps({'decision': 'block', 'reason': 'run the linter'}))\n",
    )
    conv, _, _ = _turn(
        {"post_tool_use": [{"matcher": "shout", "command": record}]}, calls, tmp_path
    )
    payload = json.loads(log.read_text())
    assert payload["hook_event_name"] == "post_tool_use"
    assert payload["tool_name"] == "shout"
    assert payload["tool_input"] == {"text": "hi"}
    assert payload["tool_output"] == "HI"
    assert payload["session_id"] == "s1" and payload["cwd"] == str(tmp_path)
    # A post hook cannot undo the call, but its reason reaches the model.
    assert _tool_result(conv) == "HI\n\nHook feedback: run the linter"


def test_prompt_hooks_block_or_add_context_and_stop_fires(tmp_path):
    calls = []
    marker = tmp_path / "stopped.json"
    stop = _script(
        tmp_path, "stop", f"open({str(marker)!r}, 'w').write(json.dumps(payload))"
    )
    context = _script(tmp_path, "context", "print('Branch: main, tests are slow')")
    conv, _, client = _turn(
        {"user_prompt_submit": [{"command": context}], "stop": [{"command": stop}]},
        calls,
        tmp_path,
        script=[{"content": "done"}],
    )
    first_user = next(m for m in client.requests[0] if m["role"] == "user")
    assert "Branch: main, tests are slow" in str(first_user["content"])
    assert json.loads(marker.read_text())["last_message"] == "done"

    block = _script(
        tmp_path, "block", "sys.stderr.write('secrets in prompt'); sys.exit(2)"
    )
    conv, events, client = _turn(
        {"user_prompt_submit": [{"command": block}]}, calls, tmp_path
    )
    assert client.requests == [] and conv.messages == []
    assert "secrets in prompt" in events[0]["message"]


def test_parse_hooks_formats_and_event_bus(tmp_path):
    parsed = parse_hooks(
        {
            "PreToolUse": [
                {"matcher": "a|b", "hooks": [{"command": "x", "timeout": 5}]}
            ],
            "post_tool_use": [{"command": "y"}],
            "Nonsense": [{"command": "z"}],
            "stop": [{"matcher": "("}],  # no command: skipped
        }
    )
    assert set(parsed) == {"pre_tool_use", "post_tool_use"}
    hook = parsed["pre_tool_use"][0]
    assert hook.timeout == 5 and hook.matches("a") and not hook.matches("ab")

    bus, seen = EventBus(), []
    bus.on("pre_tool_use", lambda **kw: seen.append(kw["tool_name"]))
    runner = HookRunner({}, event_bus=bus, cwd=str(tmp_path))
    runner.run("pre_tool_use", "shout", tool_input={})
    assert seen == ["shout"]


def test_hooks_guard_subagent_tools(tmp_path):
    from neow.core.sub_agent import SubAgent

    calls = []
    guard = _script(tmp_path, "guard", "sys.stderr.write('blocked'); sys.exit(2)")
    prompt_log = tmp_path / "prompts.txt"
    prompt_hook = _script(
        tmp_path, "prompt", f"open({str(prompt_log)!r}, 'a').write('x')"
    )
    executor = _executor(calls)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.YOLO)
    parent, _ = _conversation(
        [{"tool_calls": [_call("s1", "shout", text="hi")]}, {"content": "report"}],
        executor,
    )
    parent.hooks = HookRunner(
        {
            "pre_tool_use": [{"command": guard}],
            "user_prompt_submit": [{"command": prompt_hook}],
        },
        cwd=str(tmp_path),
    )
    sub = SubAgent(parent, agent_type="general")
    assert sub.run("do it") == "report"
    assert calls == []  # the parent's tool hook applied inside the sub-agent
    assert not prompt_log.exists()  # but turn-level hooks did not fire


def test_repository_config_cannot_define_hooks(tmp_path, capsys):
    from neow.cli.main import setup_hooks

    cfg = SimpleNamespace(
        hooks={"pre_tool_use": [{"command": "true"}]},
        user_owned=False,
        source_path=tmp_path / ".neow.json",
    )
    runner = setup_hooks(cfg)
    assert runner.hooks == {}
    assert "忽略" in capsys.readouterr().out
    owned = setup_hooks(SimpleNamespace(hooks=cfg.hooks, user_owned=True))
    assert set(owned.hooks) == {"pre_tool_use"}
