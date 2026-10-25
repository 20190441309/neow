"""Comprehensive tests for the 4-stage agent capability upgrades (P0 -> P2)."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual.app import App
from textual.widgets import Input, OptionList

from neow.cli.commands import Command, parse_command
from neow.core.background_tasks import BackgroundTaskManager, background_task
from neow.core.context import ContextManager
from neow.core.context_masking import mask_old_observations
from neow.core.conversation import ConversationManager
from neow.core.skills import (
    discover_skills,
    format_skills_index,
    load_skill_content,
)
from neow.tools.builtin import builtin_specs
from neow.tools.code_intel import extract_symbols, file_outline, repo_map
from neow.tools.command import (
    execute_command,
    get_session_cwd,
    reset_session_cwd,
    set_session_cwd,
)
from neow.tools.diagnostics import append_diagnostics, check_file_diagnostics
from neow.tools.file_ops import create_file, edit_file, write_file
from neow.tui.commands import CommandDispatcher
from neow.tui.screens.ask_user_modal import AskUserModalScreen
from neow.tui.screens.plan_modal import PlanModalScreen
from neow.tui.screens.skills_modal import SkillsModalScreen
from neow.tui.screens.tasks_modal import TasksModalScreen


class _HostApp(App):
    pass


# ── Stage 1 (P0): Code Intelligence & Post-Edit Diagnostics ──────────


def test_post_edit_diagnostics_python_and_json(tmp_path: Path):
    good_py = tmp_path / "good.py"
    res_good = write_file(str(good_py), "def add(a, b):\n    return a + b\n")
    assert res_good == f"File written successfully: {good_py}"
    assert check_file_diagnostics(good_py) == ""

    bad_py = tmp_path / "bad.py"
    res_bad = create_file(str(bad_py), "def broken(\n    return 1\n")
    assert "[Diagnostics] ⚠" in res_bad
    assert "SyntaxError" in res_bad

    res_fixed = edit_file(
        str(bad_py),
        "def broken(\n    return 1\n",
        "def broken():\n    return 1\n",
    )
    assert "[Diagnostics]" not in res_fixed

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{invalid json", encoding="utf-8")
    diag_json = append_diagnostics(bad_json, "Saved")
    assert "[Diagnostics] ⚠" in diag_json
    assert "JSONDecodeError" in diag_json


def test_code_intel_symbols_outline_and_repo_map(tmp_path: Path):
    src = tmp_path / "service.py"
    src.write_text(
        "class OrderService:\n"
        "    def create_order(self, item: str) -> bool:\n"
        "        return True\n\n"
        "async def fetch_catalog():\n"
        "    pass\n",
        encoding="utf-8",
    )
    ts_src = tmp_path / "client.ts"
    ts_src.write_text(
        "export class ApiClient {}\nexport async function sendRequest() {}\n",
        encoding="utf-8",
    )

    syms = extract_symbols(src)
    joined = "\n".join(syms)
    assert "class OrderService" in joined
    assert "def create_order" in joined
    assert "async def fetch_catalog" in joined

    outline = file_outline(str(src))
    assert "class OrderService" in outline
    assert "async def fetch_catalog" in outline

    rmap = repo_map(str(tmp_path), query="Order")
    assert "service.py" in rmap
    assert "OrderService" in rmap

    ctx = ContextManager(str(tmp_path))
    rel = ctx.get_relevant_files("create_order")
    assert len(rel) >= 1
    assert rel[0]["path"] == "service.py"
    assert "create_order" in rel[0]["symbols"]


# ── Stage 2 (P1): ask_user Tool & /plan Approval Modal ───────────────


def test_ask_user_tool_and_modal(tmp_path: Path):
    conv = ConversationManager(model_client=None)
    fallback = conv.ask_user("Which DB?", ["SQLite", "Postgres"])
    assert "Non-interactive mode" in fallback
    assert "SQLite" in fallback

    conv.ask_user_callback = lambda q, opts: f"Selected {opts[1]} for {q}"
    ans = conv.ask_user("Which DB?", ["SQLite", "Postgres"])
    assert ans == "User answered: Selected Postgres for Which DB?"

    results = []

    async def _run():
        app = _HostApp()
        async with app.run_test() as pilot:
            app.push_screen(
                AskUserModalScreen(
                    question="请选择数据库方案",
                    options=["SQLite", "PostgreSQL"],
                    on_answer=results.append,
                )
            )
            await pilot.pause()
            inp = app.screen.query_one("#ask-custom-input", Input)
            inp.value = "DuckDB"
            await pilot.click("#submit-ask-btn")
            await pilot.pause()

    asyncio.run(_run())
    assert results == ["DuckDB"]


def test_plan_command_and_modal():
    parsed = parse_command("/plan 重构认证模块")
    assert parsed.command == Command.PLAN
    assert parsed.args == "重构认证模块"

    conv = ConversationManager(model_client=None)
    submitted = []
    disp = CommandDispatcher(
        conversation=conv,
        hooks={"submit": submitted.append},
    )
    res = disp.dispatch(parsed)
    assert "正在生成执行计划" in res.text
    assert len(submitted) == 1
    assert "todo_write" in submitted[0]

    res_approve = disp.dispatch(parse_command("/plan approve"))
    assert "已批准计划" in res_approve.text
    assert len(submitted) == 2

    approved = []

    async def _run():
        app = _HostApp()
        async with app.run_test() as pilot:
            app.push_screen(
                PlanModalScreen(
                    todos=[{"id": "1", "content": "Step 1", "status": "pending"}],
                    on_approve=approved.append,
                )
            )
            await pilot.pause()
            await pilot.click("#approve-plan-btn")
            await pilot.pause()

    asyncio.run(_run())
    assert approved == [""]


# ── Stage 3 (P1): Persistent Session CWD & Background Tasks ──────────


def test_persistent_session_cwd(tmp_path: Path):
    reset_session_cwd()
    try:
        assert get_session_cwd() is None
        sub = tmp_path / "subdir"
        sub.mkdir()
        res = execute_command(f'cd "{sub}"')
        assert "Changed directory to" in res
        assert get_session_cwd() == sub.resolve()

        nested = sub / "nested"
        nested.mkdir()
        set_session_cwd("nested")
        assert get_session_cwd() == nested.resolve()
    finally:
        reset_session_cwd()
        assert get_session_cwd() is None


def test_background_task_manager_and_modal():
    mgr = BackgroundTaskManager()
    task = mgr.start("python -c \"print('hello-bg')\"")

    for _ in range(30):
        if not task.is_running and task.tail():
            break
        time.sleep(0.05)
    assert "hello-bg" in "\n".join(task.tail())
    mgr.stop_all()

    out = background_task("list")
    assert isinstance(out, str)

    async def _run():
        app = _HostApp()
        async with app.run_test() as pilot:
            app.push_screen(TasksModalScreen(manager=mgr))
            await pilot.pause()
            assert app.screen.query_one("#tasks-list", OptionList) is not None
            await pilot.click("#close-tasks-btn")
            await pilot.pause()

    asyncio.run(_run())


# ── Stage 4 (P2): Observation Masking & On-Demand Skills ─────────────


def test_observation_masking_preserves_recent_and_masks_old():
    messages = []
    for i in range(6):
        messages.append(
            {
                "role": "assistant",
                "content": f"Turn {i}",
                "tool_calls": [{"id": f"call_{i}", "function": {"name": "read_file"}}],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": f"LINE_{i}_" + ("X" * 2000) + f"_END_{i}",
            }
        )

    masked = mask_old_observations(messages, keep_recent_turns=3, min_chars=500)
    assert len(messages[1]["content"]) > 2000
    assert "已折叠历史工具输出" in masked[1]["content"]
    assert "已折叠历史工具输出" in masked[3]["content"]
    assert "已折叠历史工具输出" in masked[5]["content"]
    assert masked[7]["content"] == messages[7]["content"]
    assert masked[9]["content"] == messages[9]["content"]
    assert masked[11]["content"] == messages[11]["content"]


def test_skills_discovery_loading_and_modal(tmp_path: Path):
    skill_dir = tmp_path / ".neow" / "skills" / "security-audit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: security-audit\n"
        "description: Perform OWASP security review\n"
        "---\n\n"
        "# Security Audit Steps\n1. Check SQLi\n2. Check XSS\n",
        encoding="utf-8",
    )

    skills = discover_skills(tmp_path)
    assert any(s.name == "security-audit" for s in skills)
    idx_text = format_skills_index(skills)
    assert "security-audit" in idx_text
    assert "Perform OWASP security review" in idx_text

    loaded = load_skill_content("security-audit", tmp_path)
    assert "# Security Audit Steps" in loaded
    assert "Check SQLi" in loaded

    loaded_events = []

    async def _run():
        app = _HostApp()
        async with app.run_test() as pilot:
            app.push_screen(
                SkillsModalScreen(
                    workspace_root=tmp_path,
                    on_load=lambda n, c: loaded_events.append((n, c)),
                )
            )
            await pilot.pause()
            await pilot.click("#load-skill-btn")
            await pilot.pause()

    asyncio.run(_run())
    assert len(loaded_events) == 1
    assert loaded_events[0][0] == "security-audit"


def test_builtin_specs_include_all_new_tools():
    names = {spec.name for spec in builtin_specs()}
    for expected in (
        "repo_map",
        "file_outline",
        "ask_user",
        "background_task",
        "load_skill",
    ):
        assert expected in names
