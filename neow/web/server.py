"""HTTP + SSE server and WebSessionBridge for Neow Web Studio."""

from __future__ import annotations

import difflib
import json
import mimetypes
import os
import queue
import re
import socket
import threading
import time
import uuid
import webbrowser
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime
from functools import wraps
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.background_tasks import get_background_manager
from neow.core.config import Config, ConfigError
from neow.core.cancellation import CancelToken
from neow.core.goal import (
    GoalState,
    build_goal_continuation_prompt,
    build_goal_initial_prompt,
    is_goal_achieved,
)
from neow.core.skills import discover_skills, load_skill_content
from neow.models.factory import PROVIDERS, build_model_client, create_model_client
from neow.models.management import (
    PROVIDER_PRESETS,
    fetch_endpoint_models,
    get_preferred_magpie_model,
    is_local_endpoint,
    sync_gateway_models,
    sync_magpie,
    validate_model_entry,
)
from neow.tui.bridge.controller import ApprovalBridge, ChatController
from neow.tui.bridge.events import (
    ContentDelta,
    Notice,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStarted,
    TodosUpdated,
    ToolFinished,
    ToolProgress,
    ToolStarted,
    TurnCompleted,
    TurnFailed,
)
from neow.web.workspaces import (
    browse_workspaces,
    validate_request_origin,
    validate_workspace_path,
    workspace_roots,
)

STATIC_DIR = Path(__file__).parent / "static"
WRITE_TOOLS = {"write_file", "edit_file", "create_file", "hashline_edit"}
FILE_REFERENCE = re.compile(r"""(?<!\S)@(?:"([^"]+)"|'([^']+)'|([^\s]+))""")
IGNORED_WORKSPACE_DIRECTORIES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
}


class SessionBusyError(ConfigError):
    """A conflicting operation still owns the shared conversation."""


def idle_action(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._operation_scope(method.__name__):
            return method(self, *args, **kwargs)

    return guarded


class EventBroadcaster:
    """Thread-safe SSE broadcaster with in-memory event log."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: List[queue.Queue] = []
        self.generation: Callable[[], int] = lambda: 0

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1024)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        msg = {
            "type": event_type,
            "ts": time.time(),
            "workspace_generation": self.generation(),
            **payload,
        }
        with self._lock:
            dead: List[queue.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                self._subscribers.remove(q)


class WebSessionBridge:
    """Connects a ConversationManager to the Web Studio HTTP/SSE endpoints."""

    def __init__(
        self,
        conversation: Any,
        *,
        config: Optional[Config] = None,
        token_tracker: Any = None,
        approval_policy: Optional[ApprovalPolicy] = None,
        event_bus: Any = None,
        web_fetcher: Any = None,
    ) -> None:
        self.conversation = conversation
        self.config = config or Config()
        self.token_tracker = token_tracker or getattr(
            conversation, "token_tracker", None
        )
        self.approval_policy = (
            approval_policy
            or getattr(
                getattr(conversation, "tool_executor", None),
                "approval_policy",
                None,
            )
            or ApprovalPolicy()
        )
        self.event_bus = event_bus
        self.web_fetcher = web_fetcher
        self.broadcaster = EventBroadcaster()

        self._lock = threading.RLock()
        self._request_context = threading.local()
        self._operation: Optional[str] = None
        self._operation_owner: Optional[int] = None
        self._turn_token: Optional[CancelToken] = None
        self._cancel_requested = False
        self.workspace_generation = 0
        self._goal_generation = 0
        self._next_goal_prompt: Optional[tuple[str, str]] = None
        self._recent_workspaces = [str(Path.cwd().resolve())]
        self._approval_defaults = dict(self.approval_policy.tool_overrides)
        self.broadcaster.generation = lambda: self.workspace_generation
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._pending_questions: Dict[str, Dict[str, Any]] = {}
        self._file_snapshots: Dict[str, str] = {}
        self.timeline: List[Dict[str, Any]] = []
        self.goal_state = GoalState(goal="", active=False)
        self.current_plan: str = ""
        self.plan_pending_approval: bool = False
        self.active_skills: set[str] = set()

        # These callbacks live on different objects in the actual tool pipeline.
        approval_bridge = ApprovalBridge(request=self._on_approval_req)
        executor = getattr(self.conversation, "tool_executor", None)
        if executor is not None:
            executor.approval_policy = self.approval_policy
            executor.approval_callback = approval_bridge
        self.conversation.ask_user_callback = self._on_ask_user_req
        self.conversation.wait_for_tool_workers = True
        if self.config.source_path is not None:
            self.config.source_path = self.config.source_path.resolve()

        self.controller = ChatController(
            self.conversation,
            event_callback=self._on_controller_event,
            approval_bridge=approval_bridge,
            token_tracker=self.token_tracker,
            event_bus=self.event_bus,
            web_fetcher=self.web_fetcher,
        )

    @property
    def busy(self) -> bool:
        return self._operation is not None or self.controller.busy

    def _publish_state(self) -> None:
        self.broadcaster.publish("state_updated", {"state": self.get_state_snapshot()})

    def _check_request_generation(self) -> None:
        expected = getattr(self._request_context, "generation", None)
        if expected is not None and (
            type(expected) is not int or expected != self.workspace_generation
        ):
            raise SessionBusyError("工作区已在其他页面更新，请刷新确认当前项目后再操作")

    @contextmanager
    def _operation_scope(self, name: str):
        owner = threading.get_ident()
        with self._lock:
            self._check_request_generation()
            nested = self._operation_owner == owner
            if not nested:
                if (
                    self.busy
                    or self._pending_approvals
                    or self._pending_questions
                    or (self.goal_state.active and name != "clear")
                ):
                    raise SessionBusyError("当前操作尚未结束，请等待完成或先停止任务")
                self._operation = name
                self._operation_owner = owner
                self._cancel_requested = False
                self._publish_state()
        try:
            yield
        finally:
            if not nested:
                with self._lock:
                    self._operation = None
                    self._operation_owner = None
                    self._publish_state()

    # -- state snapshot ------------------------------------------------

    def get_state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def _snapshot_unlocked(self) -> Dict[str, Any]:
        client = getattr(self.conversation, "model_client", None)
        model_name = getattr(client, "config_name", None) or (
            getattr(client, "model", None) if client else None
        )
        effort = getattr(client, "effort", "medium") if client else "medium"
        mode = (
            self.approval_policy.mode.value
            if self.approval_policy is not None
            else "write"
        )
        usage = self._token_summary()
        todos = list(getattr(self.conversation, "todos", None) or [])
        with self._lock:
            approvals = [
                {
                    "id": aid,
                    "tool": item["tool"],
                    "params": item["params"],
                    "reason": item["reason"],
                }
                for aid, item in self._pending_approvals.items()
            ]
            questions = [
                {
                    "id": qid,
                    "question": item["question"],
                    "options": item["options"],
                }
                for qid, item in self._pending_questions.items()
            ]
            timeline_copy = list(self.timeline)

        return {
            "busy": self.busy,
            "workspace_generation": self.workspace_generation,
            "cwd": str(Path.cwd()),
            "git_branch": self._git_branch(),
            "active_model": model_name,
            "model_id": getattr(client, "model", "") if client else "",
            "effort": effort or "off",
            "approval_mode": mode,
            "usage": usage,
            "todos": todos,
            "goal": {
                "active": self.goal_state.active,
                "goal": self.goal_state.goal,
                "current_round": self.goal_state.current_round,
                "max_rounds": self.goal_state.max_rounds,
            },
            "plan": {
                "text": self.current_plan,
                "pending": self.plan_pending_approval,
            },
            "pending_approvals": approvals,
            "pending_questions": questions,
            "timeline": timeline_copy,
        }

    def _token_summary(self) -> Dict[str, Any]:
        tracker = self.token_tracker
        if tracker is None:
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cost": 0.0,
            }
        inputs = getattr(tracker, "session_input", 0)
        outputs = getattr(tracker, "session_output", 0)
        cost = tracker.get_session_cost() if hasattr(tracker, "get_session_cost") else 0
        return {
            "input_tokens": inputs,
            "output_tokens": outputs,
            "total_tokens": inputs + outputs,
            "cost": round(float(cost or 0.0), 4),
        }

    @staticmethod
    def _git_branch() -> str:
        try:
            from neow.tools.git import _run_git

            return _run_git(["branch", "--show-current"], cwd=str(Path.cwd())) or (
                "detached:"
                + _run_git(["rev-parse", "--short", "HEAD"], cwd=str(Path.cwd()))
            )
        except Exception:
            return ""

    # -- controller event handling -------------------------------------

    def _on_controller_event(self, event: Any) -> None:
        with self._lock:
            self._apply_controller_event(event)

    def _apply_controller_event(self, event: Any) -> None:
        if isinstance(event, ReasoningStarted):
            self.broadcaster.publish("reasoning_started", {})
        elif isinstance(event, ReasoningDelta):
            self.broadcaster.publish("reasoning_delta", {"text": event.text})
        elif isinstance(event, ReasoningEnd):
            item = {
                "kind": "reasoning",
                "text": event.reasoning,
                "duration": round(event.duration, 2),
            }
            with self._lock:
                self.timeline.append(item)
            self.broadcaster.publish(
                "reasoning_end",
                {"text": event.reasoning, "duration": round(event.duration, 2)},
            )
        elif isinstance(event, ContentDelta):
            self.broadcaster.publish("content_delta", {"text": event.text})
        elif isinstance(event, ToolStarted):
            self._capture_pre_tool_snapshot(event.call_id, event.name, event.args)
            self.broadcaster.publish(
                "tool_started",
                {
                    "call_id": event.call_id,
                    "name": event.name,
                    "args": event.args,
                },
            )
        elif isinstance(event, ToolProgress):
            self.broadcaster.publish(
                "tool_progress",
                {
                    "call_id": event.call_id,
                    "name": event.name,
                    "message": event.message,
                },
            )
        elif isinstance(event, ToolFinished):
            diff_text = self._compute_post_tool_diff(event.call_id, event.name)
            payload = {
                "call_id": event.call_id,
                "name": event.name,
                "result": event.result,
                "is_error": event.is_error,
                "denied": event.denied,
                "diff": diff_text,
            }
            with self._lock:
                self.timeline.append({"kind": "tool", **payload})
            self.broadcaster.publish("tool_finished", payload)
        elif isinstance(event, TodosUpdated):
            todos = [dict(t) for t in event.todos]
            self.broadcaster.publish("todos_updated", {"todos": todos})
        elif isinstance(event, Notice):
            with self._lock:
                self.timeline.append(
                    {"kind": "notice", "message": event.message, "level": event.level}
                )
            self.broadcaster.publish(
                "notice", {"message": event.message, "level": event.level}
            )
        elif isinstance(event, TurnCompleted):
            if event.content:
                with self._lock:
                    self.timeline.append({"kind": "assistant", "text": event.content})
            self.broadcaster.publish(
                "turn_completed",
                {
                    "content": event.content,
                    "usage": self._token_summary(),
                    "cancelled": event.cancelled,
                    "busy": self.busy,
                },
            )
            self._handle_post_turn_goal(event.content, event.cancelled)
        elif isinstance(event, TurnFailed):
            with self._lock:
                self.timeline.append({"kind": "error", "message": event.message})
            if self.goal_state.active:
                self.goal_state.active = False
                self._broadcast_goal()
            self.broadcaster.publish(
                "turn_failed", {"message": event.message, "busy": self.busy}
            )

    def _capture_pre_tool_snapshot(
        self, call_id: str, name: str, args: Dict[str, Any]
    ) -> None:
        if name not in WRITE_TOOLS or not call_id:
            return
        raw_path = args.get("path") or args.get("file_path")
        if not raw_path:
            return
        try:
            target = Path(str(raw_path))
            if not target.is_absolute():
                target = Path.cwd() / target
            old_text = (
                target.read_text(encoding="utf-8", errors="replace")
                if target.exists() and target.is_file()
                else ""
            )
            with self._lock:
                self._file_snapshots[call_id] = f"{target}|||{old_text}"
        except Exception:
            pass

    def _compute_post_tool_diff(self, call_id: str, name: str) -> str:
        if name not in WRITE_TOOLS or not call_id:
            return ""
        with self._lock:
            snap = self._file_snapshots.pop(call_id, "")
        if not snap or "|||" not in snap:
            return ""
        path_str, old_text = snap.split("|||", 1)
        try:
            target = Path(path_str)
            new_text = (
                target.read_text(encoding="utf-8", errors="replace")
                if target.exists() and target.is_file()
                else ""
            )
            if old_text == new_text:
                return ""
            rel = (
                str(target.relative_to(Path.cwd()))
                if target.is_relative_to(Path.cwd())
                else target.name
            )
            diff_lines = list(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    n=3,
                )
            )
            return "".join(diff_lines[:200])
        except Exception:
            return ""

    # -- approval & ask_user bridges -----------------------------------

    def _on_approval_req(
        self, tool: str, params: Dict[str, Any], reason: str, future: Future
    ) -> None:
        req_id = uuid.uuid4().hex[:10]
        with self._lock:
            if self._cancel_requested:
                if not future.done():
                    future.set_result(False)
                return
            self._pending_approvals[req_id] = {
                "tool": tool,
                "params": params,
                "reason": reason,
                "future": future,
            }
            self.broadcaster.publish(
                "approval_request",
                {"id": req_id, "tool": tool, "params": params, "reason": reason},
            )

    def resolve_approval(self, req_id: str, decision: str) -> bool:
        if decision not in ("allow_once", "allow_always", "deny"):
            raise ConfigError("无效的审批决定")
        with self._lock:
            self._check_request_generation()
            item = self._pending_approvals.pop(req_id, None)
            if not item:
                return False
            future: Future = item["future"]
            tool: str = item["tool"]
            approved = decision in ("allow_once", "allow_always")
            if decision == "allow_always":
                self.approval_policy.set_tool_override(tool, "allow")
            if not future.done():
                future.set_result(approved)
            self.broadcaster.publish(
                "approval_resolved",
                {
                    "id": req_id,
                    "tool": tool,
                    "decision": decision,
                    "approved": approved,
                },
            )
        return True

    def _on_ask_user_req(
        self, question: str, options: Optional[List[str]] = None
    ) -> str:
        req_id = uuid.uuid4().hex[:10]
        future: Future = Future()
        opts = list(options or [])
        with self._lock:
            if self._cancel_requested:
                return ""
            self._pending_questions[req_id] = {
                "question": question,
                "options": opts,
                "future": future,
            }
            self.broadcaster.publish(
                "ask_user_request",
                {"id": req_id, "question": question, "options": opts},
            )
        try:
            return str(future.result(timeout=600.0) or "")
        except Exception:
            return ""
        finally:
            with self._lock:
                if self._pending_questions.pop(req_id, None) is not None:
                    self.broadcaster.publish(
                        "ask_user_resolved", {"id": req_id, "answer": ""}
                    )

    def resolve_ask_user(self, req_id: str, answer: str) -> bool:
        with self._lock:
            self._check_request_generation()
            item = self._pending_questions.pop(req_id, None)
            if not item:
                return False
            future: Future = item["future"]
            if not future.done():
                future.set_result(answer)
            self.broadcaster.publish(
                "ask_user_resolved", {"id": req_id, "answer": answer}
            )
        return True

    # -- chat, goal, plan actions --------------------------------------

    def _resolve_pending(self) -> None:
        with self._lock:
            for req_id in list(self._pending_approvals):
                self.resolve_approval(req_id, "deny")
            for req_id in list(self._pending_questions):
                self.resolve_ask_user(req_id, "")

    def cancel(self) -> None:
        with self._lock:
            self._check_request_generation()
            self._cancel_requested = True
            self._goal_generation += 1
            self._next_goal_prompt = None
            self.goal_state.active = False
            if self._turn_token is not None:
                self._turn_token.cancel()
            self.controller.cancel()
            self._resolve_pending()
            self._broadcast_goal()

    def _read_prompt_references(self, text: str) -> Dict[str, str]:
        references: Dict[str, str] = {}
        total = 0
        for match in FILE_REFERENCE.finditer(text):
            path = next(value for value in match.groups() if value is not None)
            preview = self.read_workspace_file(path)
            if preview["truncated"]:
                raise ConfigError(f"引用文件过大，请使用 read_file 分段读取: {path}")
            absolute = str((Path.cwd() / preview["path"]).resolve())
            references[absolute] = preview["content"]
            total += len(preview["content"])
            if len(references) > 16 or total > 200000:
                raise ConfigError("单条消息最多引用 16 个文件、合计 200000 字符")
        return references

    def submit_prompt(self, prompt: str, *, display_prompt: str = "") -> bool:
        text = (prompt or "").strip()
        if not text:
            return False
        shown = (display_prompt or text).strip()
        with self._lock:
            self._check_request_generation()
            if (
                self.busy
                or self.goal_state.active
                or self._pending_approvals
                or self._pending_questions
            ):
                return False
            # Reserve before spawning: controller.busy is not set until the worker runs.
            references = self._read_prompt_references(text)
            self._operation = "turn"
            self._cancel_requested = False
            token = self._turn_token = CancelToken()
            if references:
                self.conversation.context_files.update(references)
            self.timeline.append({"kind": "user", "text": shown})
            self.broadcaster.publish("user_message", {"text": shown})
            self._publish_state()

        def run() -> None:
            next_text, next_token = text, token
            try:
                while True:
                    self.controller.run_turn(next_text, cancel_token=next_token)
                    with self._lock:
                        self._resolve_pending()
                        continuation = self._next_goal_prompt
                        generation = self._goal_generation
                        self._next_goal_prompt = None
                        if not continuation or not self.goal_state.active:
                            break
                    # Keep the reservation through autonomous round boundaries.
                    time.sleep(0.3)
                    with self._lock:
                        if (
                            not self.goal_state.active
                            or generation != self._goal_generation
                        ):
                            break
                        next_text = continuation[0]
                        next_token = self._turn_token = CancelToken()
                        self.timeline.append({"kind": "user", "text": continuation[1]})
                        self.broadcaster.publish(
                            "user_message", {"text": continuation[1]}
                        )
                        self._publish_state()
            except Exception as exc:
                self._on_controller_event(TurnFailed(str(exc)))
            finally:
                with self._lock:
                    self._resolve_pending()
                    self._operation = None
                    self._turn_token = None
                    self._publish_state()

        try:
            threading.Thread(target=run, daemon=True).start()
        except Exception:
            with self._lock:
                self._operation = None
                self._turn_token = None
                self._publish_state()
            raise
        return True

    def start_goal(self, goal_text: str) -> bool:
        text = (goal_text or "").strip()
        with self._lock:
            self._check_request_generation()
            if not text or self.busy or self.goal_state.active:
                return False
            kickoff = build_goal_initial_prompt(text)
            if not self.submit_prompt(kickoff, display_prompt=f"启动 /goal: {text}"):
                return False
            self._goal_generation += 1
            self.goal_state = GoalState(goal=text, active=True, current_round=1)
            self._broadcast_goal()
            return True

    def stop_goal(self) -> None:
        self.cancel()

    def _broadcast_goal(self) -> None:
        self.broadcaster.publish(
            "goal_updated",
            {
                "active": self.goal_state.active,
                "goal": self.goal_state.goal,
                "current_round": self.goal_state.current_round,
                "max_rounds": self.goal_state.max_rounds,
            },
        )

    def _handle_post_turn_goal(self, content: str, cancelled: bool) -> None:
        if not self.goal_state.active:
            return
        if cancelled:
            self.goal_state.active = False
            self._broadcast_goal()
            return
        todos = list(getattr(self.conversation, "todos", None) or [])
        if is_goal_achieved(content or "", todos=todos):
            self.goal_state.active = False
            self._broadcast_goal()
            self.broadcaster.publish(
                "notice",
                {"message": "🎯 /goal 目标已达成，自主巡航结束！", "level": "info"},
            )
            return
        if self.goal_state.current_round >= self.goal_state.max_rounds:
            self.goal_state.active = False
            self._broadcast_goal()
            self.broadcaster.publish(
                "notice",
                {
                    "message": (
                        f"🎯 已达到最大自主轮次 ({self.goal_state.max_rounds})，已暂停。"
                    ),
                    "level": "warn",
                },
            )
            return

        self.goal_state.current_round += 1
        self._broadcast_goal()
        next_prompt = build_goal_continuation_prompt(self.goal_state, todos=todos)

        self._next_goal_prompt = (
            next_prompt,
            f"/goal 自动推进 Round "
            f"{self.goal_state.current_round}/{self.goal_state.max_rounds}",
        )

    @idle_action
    def generate_plan(self, task_text: str) -> Dict[str, Any]:
        task = (task_text or "").strip()
        if not task:
            raise ConfigError("请输入需要规划的任务描述")
        client = getattr(self.conversation, "model_client", None)
        if client is None:
            raise ConfigError("请先配置并选择模型")
        plan_prompt = (
            "You are in READ-ONLY Architect Planning Mode.\n"
            "Create a structured, step-by-step implementation plan in Markdown for:\n\n"
            f"{task}\n\n"
            "Include: 1. Goal & Scope, 2. Files to Modify/Create, "
            "3. Step-by-Step Changes, 4. Verification Plan."
        )
        res = client.chat([{"role": "user", "content": plan_prompt}])
        if self.token_tracker is not None and getattr(res, "usage", None):
            self.token_tracker.record(res.usage, getattr(client, "model", "unknown"))
        if self._cancel_requested:
            raise ConfigError("规划已停止；未覆盖之前的计划")
        self.current_plan = (res.content or "").strip()
        self.plan_pending_approval = True
        self.broadcaster.publish(
            "plan_updated",
            {"text": self.current_plan, "pending": self.plan_pending_approval},
        )
        return {"text": self.current_plan, "pending": True}

    def approve_plan(self, edited_plan: str = "") -> bool:
        with self._lock:
            self._check_request_generation()
            plan_body = (edited_plan or self.current_plan).strip()
            if not plan_body or not self.plan_pending_approval or self.busy:
                return False
            exec_prompt = (
                "The user has APPROVED the following implementation plan. "
                "Execute it step by step and verify your changes:\n\n"
                f"{plan_body}"
            )
            if not self.submit_prompt(
                exec_prompt, display_prompt="已批准实施计划，开始按步骤执行"
            ):
                return False
            self.current_plan = plan_body
            self.plan_pending_approval = False
            self.broadcaster.publish(
                "plan_updated", {"text": plan_body, "pending": False}
            )
            return True

    # -- model management ----------------------------------------------

    def get_models_catalog(self) -> Dict[str, Any]:
        client = getattr(self.conversation, "model_client", None)
        current = getattr(client, "config_name", None)
        items: List[Dict[str, Any]] = []
        for name, entry in self.config.models.items():
            items.append(
                {
                    "name": name,
                    "provider": entry.get("provider") or "auto",
                    "model": entry.get("model") or "",
                    "base_url": entry.get("base_url") or "",
                    "display_name": entry.get("display_name")
                    or entry.get("model")
                    or name,
                    "source": entry.get("source") or "custom",
                    "api_key_env": entry.get("api_key_env") or "",
                    "has_key": bool(entry.get("api_key") or entry.get("api_key_env")),
                    "active": name == current,
                }
            )
        return {
            "current": current,
            "models": items,
            "presets": PROVIDER_PRESETS,
            "providers": list(PROVIDERS),
        }

    @idle_action
    def select_model(self, name: str) -> Dict[str, Any]:
        client = create_model_client(self.config, name)
        sdk = getattr(client, "client", None)
        if sdk is not None and hasattr(sdk, "with_options"):
            client.client = sdk.with_options(timeout=5, max_retries=0)
        try:
            ok = client.validate_connection()
        finally:
            if sdk is not None:
                client.client = sdk
        if not ok:
            raise ConfigError("连接失败，请检查 API 地址、模型 ID 和 Key")
        self.config.set_default_model(name)
        self.conversation.model_client = client
        self.conversation.model_setup_notice = None
        self.broadcaster.publish(
            "model_switched",
            {"active_model": name, "model_id": getattr(client, "model", "")},
        )
        return {"active_model": name, "model_id": getattr(client, "model", "")}

    def model_entry_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        is_edit = bool(payload.get("is_edit"))
        existing = self.config.stored_model_entry(name) if is_edit and name else {}
        entry = dict(existing)
        base_url = str(payload.get("base_url") or "").strip()
        entry.update(
            provider=str(payload.get("provider") or "openai-compatible").strip(),
            base_url=base_url,
            model=str(payload.get("model") or "").strip(),
        )
        key = str(payload.get("api_key") or "").strip()
        env_name = str(payload.get("api_key_env") or "").strip()
        if key:
            entry.update(api_key=key, api_key_env="")
        elif env_name:
            entry.update(api_key="", api_key_env=env_name)
        elif (
            not entry.get("api_key")
            and not entry.get("api_key_env")
            and is_local_endpoint(base_url)
        ):
            entry.update(api_key="local", api_key_env="")
        return entry

    @idle_action
    def save_model_entry(
        self, payload: Dict[str, Any], *, activate: bool = True
    ) -> Dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        entry = self.model_entry_from_payload(payload)
        validate_model_entry(name, entry)
        self.config.save_model(name, entry)
        if activate:
            try:
                return {"saved": name, "activated": True, **self.select_model(name)}
            except Exception as exc:
                return {"saved": name, "activated": False, "activation_error": str(exc)}
        return {"saved": name, "activated": False}

    @idle_action
    def delete_model_entry(self, name: str) -> Dict[str, Any]:
        client = getattr(self.conversation, "model_client", None)
        active = getattr(client, "config_name", None)
        if name == active:
            raise ConfigError("无法删除当前正在使用的模型，请先切换到其他模型")
        if len(self.config.models) <= 1:
            raise ConfigError("至少需要保留一个模型配置")
        self.config.delete_model(name)
        return {"deleted": name}

    @idle_action
    def fetch_models(self, payload: Dict[str, Any]) -> List[str]:
        entry = self.model_entry_from_payload(payload)
        items = fetch_endpoint_models(
            entry["base_url"],
            api_key=entry.get("api_key", ""),
            api_key_env=entry.get("api_key_env", ""),
        )
        return [item["id"] for item in items]

    @idle_action
    def test_model(self, payload: Dict[str, Any]) -> bool:
        name = str(payload.get("name") or "test").strip() or "test"
        entry = self.model_entry_from_payload(payload)
        validate_model_entry(name, entry)
        client = build_model_client(entry, name)
        sdk = getattr(client, "client", None)
        if sdk is not None and hasattr(sdk, "with_options"):
            client.client = sdk.with_options(timeout=5, max_retries=0)
        try:
            return bool(client.validate_connection())
        finally:
            if sdk is not None:
                client.client = sdk

    @idle_action
    def sync_models(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        base_url = str(payload.get("base_url") or "").strip()
        if base_url:
            count = sync_gateway_models(
                self.config,
                base_url=base_url,
                api_key=str(payload.get("api_key") or "").strip(),
                api_key_env=str(payload.get("api_key_env") or "").strip(),
                prefix=str(payload.get("prefix") or "magpie").strip(),
            )
        else:
            count = sync_magpie(self.config)
        preferred = get_preferred_magpie_model(self.config)
        result = {"count": count, "preferred": preferred or "", "activated": False}
        if preferred and getattr(self.conversation, "model_client", None) is None:
            try:
                result.update(self.select_model(preferred), activated=True)
            except Exception as exc:
                result["activation_error"] = str(exc)
        return result

    @idle_action
    def set_mode(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = payload.get("approval_mode")
        effort = payload.get("effort")
        if mode is not None and mode not in ("always-ask", "write", "yolo"):
            raise ConfigError("无效的审批模式")
        if effort is not None and effort not in ("off", "low", "medium", "high"):
            raise ConfigError("无效的思考强度")
        if mode is not None:
            self.approval_policy.set_mode(ApprovalMode(mode))
        client = getattr(self.conversation, "model_client", None)
        if effort is not None and client is not None:
            client.effort = None if effort == "off" else effort
        return {
            "approval_mode": self.approval_policy.mode.value,
            "effort": getattr(client, "effort", None) or "off",
        }

    @idle_action
    def compact(self) -> str:
        summary = self.conversation.compact()
        self.broadcaster.publish(
            "notice", {"message": f"上下文已压缩: {summary}", "level": "info"}
        )
        return summary

    @idle_action
    def toggle_skill(self, name: str) -> bool:
        prefix = f"Activated skill '{name}':\n"
        if name in self.active_skills:
            self.active_skills.remove(name)
            messages = getattr(self.conversation, "messages", [])
            messages[:] = [
                message
                for message in messages
                if not (
                    message.get("role") == "system"
                    and str(message.get("content", "")).startswith(prefix)
                )
            ]
            return False
        content = load_skill_content(name, Path.cwd())
        if content.startswith("Error:"):
            raise ConfigError(content)
        self.conversation.add_message("system", prefix + content)
        self.active_skills.add(name)
        return True

    def _reset_session(self) -> None:
        self.cancel()
        self.conversation.clear_history()
        for name in ("context_files", "web_cache", "_pending_images"):
            value = getattr(self.conversation, name, None)
            if value is not None:
                value.clear()
        for name, value in (
            ("pending_lint_feedback", None),
            ("_structure_injected", False),
            ("_structure_text", None),
            ("_usage_tokens", 0),
            ("_usage_anchor", None),
            ("_usage_length", 0),
        ):
            setattr(self.conversation, name, value)
        context = getattr(self.conversation, "context_manager", None)
        if context is not None:
            context.file_cache.clear()
        self.timeline.clear()
        self._file_snapshots.clear()
        self.current_plan = ""
        self.plan_pending_approval = False
        self.active_skills.clear()
        self.goal_state = GoalState(goal="", active=False)
        self.approval_policy.tool_overrides = dict(self._approval_defaults)
        self._cancel_requested = False
        self.workspace_generation += 1

    def clear_session(self) -> Dict[str, Any]:
        with self._lock:
            with self._operation_scope("clear"):
                self._reset_session()
            state = self.get_state_snapshot()
            self.broadcaster.publish("cleared", {"state": state})
            return state

    def get_workspaces(self) -> Dict[str, Any]:
        return {
            "current": str(Path.cwd()),
            "recent": [
                {"path": path, "name": Path(path).name or path}
                for path in self._recent_workspaces
            ],
            "roots": workspace_roots(Path.cwd()),
        }

    def _check_workspace_runtime(self) -> None:
        if self.goal_state.active:
            raise SessionBusyError("请先停止自主任务，再切换项目")
        if any(task.is_running for task in get_background_manager().list_tasks()):
            raise SessionBusyError("仍有后台任务运行，请先在后台任务面板停止它们")
        if self.config.source_path is not None and not self.config.user_owned:
            raise ConfigError(
                "当前配置来自项目目录，请使用用户配置或 --config 重新启动后切换项目"
            )
        hooks = getattr(self.conversation, "hooks", None)
        if getattr(hooks, "hooks", None):
            raise ConfigError(
                "当前启用了工作目录相关的 Hooks，请在目标目录重新启动以安全切换"
            )
        mcp = getattr(self.conversation, "mcp", None)
        for server in list(getattr(mcp, "states", {}).values()):
            cfg = server.config
            scoped = cfg.source == "project" or cfg.transport == "stdio"
            task = getattr(server, "task", None)
            if scoped and (
                server.status in ("connected", "pending")
                or (task is not None and not task.done())
            ):
                raise ConfigError(
                    "当前有项目级或本地 MCP 连接，请在目标目录重新启动以安全切换"
                )
        registry = getattr(
            getattr(self.conversation, "tool_executor", None), "registry", []
        )
        if any(spec.source.startswith("plugin:") for spec in registry) or getattr(
            self.event_bus, "_handlers", {}
        ):
            raise ConfigError("当前启用了自定义插件，请在目标目录重新启动以安全切换")

    def _archive_session(self) -> Optional[str]:
        conv = self.conversation
        if not any(
            (
                getattr(conv, "messages", []),
                self.timeline,
                self.current_plan,
                getattr(conv, "context_files", {}),
                getattr(conv, "web_cache", {}),
                getattr(conv, "todos", []),
                getattr(conv, "_pending_images", []),
            )
        ):
            return None
        name = f"web_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "cwd": str(Path.cwd()),
            "model": getattr(getattr(conv, "model_client", None), "model", "unknown"),
            "messages": getattr(conv, "messages", []),
            "context_files": getattr(conv, "context_files", {}),
            "web_cache": getattr(conv, "web_cache", {}),
            "todos": getattr(conv, "todos", []),
            "system_prompt": getattr(conv, "system_prompt", ""),
            "timeline": self.timeline,
            "plan": self.current_plan,
            "plan_pending": self.plan_pending_approval,
            "active_skills": sorted(self.active_skills),
            "pending_images": getattr(conv, "_pending_images", []),
            "goal": asdict(self.goal_state),
        }

        def serialize(value):
            if is_dataclass(value):
                return asdict(value)
            if isinstance(value, Path):
                return str(value)
            raise TypeError(f"Cannot archive {type(value).__name__}")

        raw = json.dumps(data, ensure_ascii=False, indent=2, default=serialize)
        directory = Path.home() / ".neow" / "sessions"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / f"{name}.tmp"
        temporary.write_text(raw, encoding="utf-8")
        temporary.replace(directory / f"{name}.json")
        return name

    def switch_workspace(self, raw_path: str) -> Dict[str, Any]:
        from neow.core.checkpoints import CheckpointStore
        from neow.core.context import ContextManager
        from neow.core.memory import load_memory
        from neow.core.prompts import get_system_prompt
        from neow.tools.command import reset_session_cwd

        with self._lock:
            self._check_request_generation()
            target = validate_workspace_path(raw_path, Path.cwd())
            if target == Path.cwd().resolve():
                return self.get_state_snapshot()
            with self._operation_scope("workspace"):
                self._check_workspace_runtime()
                old_cwd = Path.cwd()
                memory = load_memory(target)
                context = ContextManager(str(target))
                old_checkpoints = getattr(self.conversation, "checkpoints", None)
                checkpoint_root = getattr(old_checkpoints, "root", None)
                checkpoints = CheckpointStore(root=checkpoint_root)
                self._archive_session()
                # Retain the launch config, never rebase its secrets into the new repo.
                if self.config.source_path is not None:
                    self.config.source_path = self.config.source_path.resolve()
                try:
                    os.chdir(target)
                    system_prompt = get_system_prompt()
                except Exception:
                    os.chdir(old_cwd)
                    raise
                self._reset_session()
                reset_session_cwd()
                self.conversation.context_manager = context
                self.conversation.memory = memory
                self.conversation.system_prompt = system_prompt
                self.conversation.checkpoints = checkpoints
                executor = getattr(self.conversation, "tool_executor", None)
                if executor is not None:
                    executor.checkpoints = checkpoints
                    known = getattr(executor, "_known_files", None)
                    if known is not None:
                        known.clear()
                hooks = getattr(self.conversation, "hooks", None)
                if hooks is not None:
                    hooks.cwd = str(target)
                    hooks.session_id = uuid.uuid4().hex
                recent = [str(target), str(old_cwd), *self._recent_workspaces]
                self._recent_workspaces = list(dict.fromkeys(recent))[:12]
            state = self.get_state_snapshot()
            self.broadcaster.publish("workspace_changed", {"state": state})
            return state

    # -- workspace files, tasks, skills --------------------------------

    def list_workspace_files(
        self, limit: int = 200, query: str = ""
    ) -> List[Dict[str, Any]]:
        root = Path.cwd()
        files: List[Dict[str, Any]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in IGNORED_WORKSPACE_DIRECTORIES and not d.startswith(".")
            )
            for fname in sorted(filenames):
                if fname.startswith(".") and fname not in (".neow.json",):
                    continue
                full = Path(dirpath) / fname
                try:
                    rel = full.relative_to(root).as_posix()
                    if query.casefold() not in rel.casefold():
                        continue
                    if not full.resolve().is_relative_to(root.resolve()):
                        continue
                    size = full.stat().st_size
                except OSError:
                    continue
                files.append({"path": rel, "size": size})
                if len(files) >= limit:
                    return files
        return files

    def list_workspace_directory(
        self, rel_path: str = "", offset: int = 0, limit: int = 200
    ) -> Dict[str, Any]:
        """List one directory without recursively walking a large project."""
        root = Path.cwd().resolve()
        relative = Path(rel_path)
        if relative.is_absolute() or relative.drive or offset < 0:
            raise ConfigError("目录路径或分页参数无效")
        try:
            target = (root / relative).resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_dir():
                raise ConfigError("目录路径无效或不在当前项目内")
            items = []
            with os.scandir(target) as entries:
                for entry in entries:
                    if entry.name.startswith(".") and entry.name != ".neow.json":
                        continue
                    try:
                        path = Path(entry.path)
                        resolved = path.resolve()
                        if not resolved.is_relative_to(root):
                            continue
                        is_dir = entry.is_dir()
                        if is_dir:
                            # Do not recurse through directory links or junction cycles.
                            if (
                                entry.name in IGNORED_WORKSPACE_DIRECTORIES
                                or entry.is_symlink()
                                or resolved != path
                            ):
                                continue
                        elif not entry.is_file():
                            continue
                        items.append(
                            {
                                "name": entry.name,
                                "path": path.relative_to(root).as_posix(),
                                "kind": "directory" if is_dir else "file",
                            }
                        )
                    except (OSError, RuntimeError):
                        continue
        except (OSError, RuntimeError) as exc:
            raise ConfigError("文件夹不存在或无法读取") from exc
        items.sort(
            key=lambda item: (
                item["kind"] != "directory",
                item["name"].casefold(),
                item["name"],
            )
        )
        end = offset + limit
        return {
            "path": "" if target == root else target.relative_to(root).as_posix(),
            "entries": items[offset:end],
            "next_offset": end if end < len(items) else None,
        }

    def read_workspace_file(self, rel_path: str) -> Dict[str, Any]:
        root = Path.cwd().resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ConfigError("文件路径无效或不存在")
        try:
            with target.open("r", encoding="utf-8-sig") as stream:
                content = stream.read(50001)
        except (UnicodeError, OSError) as exc:
            raise ConfigError("此文件无法作为 UTF-8 文本预览或引用") from exc
        if "\0" in content:
            raise ConfigError("二进制文件不支持文本预览或引用")
        return {
            "path": target.relative_to(root).as_posix(),
            "content": content[:50000],
            "truncated": len(content) > 50000,
        }


class _WebRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler serving static assets, JSON APIs, and `/api/events` SSE."""

    bridge: WebSessionBridge

    def log_message(self, format: str, *args: Any) -> None:
        # Keep console clean during interactive use
        pass

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2_000_000 or length < 0:
            raise ValueError("Request body too large")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _authorize(self) -> bool:
        host, port = self.server.server_address[:2]
        if self.headers.get(
            "Sec-Fetch-Site"
        ) == "same-site" or not validate_request_origin(
            self.headers.get("Host"),
            self.headers.get("Origin"),
            self.headers.get("Sec-Fetch-Site"),
            host,
            port,
        ):
            self._send_json(
                {"error": "Only same-origin local requests are allowed"},
                HTTPStatus.FORBIDDEN,
            )
            return False
        return True

    def do_OPTIONS(self) -> None:
        if not self._authorize():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._authorize():
            return
        try:
            if urlparse(self.path).path == "/api/events":
                self._handle_sse()
            else:
                with self.bridge._lock:
                    self._dispatch_get()
        except (ConfigError, ValueError, OSError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _dispatch_get(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route == "/api/events":
            self._handle_sse()
            return
        if route == "/api/state":
            self._send_json(self.bridge.get_state_snapshot())
            return
        if route == "/api/models":
            self._send_json(self.bridge.get_models_catalog())
            return
        if route == "/api/files":
            text = (query.get("q") or [""])[0].strip()
            files = self.bridge.list_workspace_files(limit=201, query=text)
            self._send_json(
                {"files": files[:200], "truncated": len(files) > 200, "query": text}
            )
            return
        if route == "/api/files/tree":
            listing = self.bridge.list_workspace_directory(
                (query.get("path") or [""])[0],
                offset=int((query.get("offset") or ["0"])[0]),
            )
            self._send_json(
                {**listing, "workspace_generation": self.bridge.workspace_generation}
            )
            return
        if route == "/api/workspaces":
            self._send_json(self.bridge.get_workspaces())
            return
        if route == "/api/workspaces/browse":
            self._send_json(
                browse_workspaces((query.get("path") or [""])[0], Path.cwd())
            )
            return
        if route == "/api/file":
            rel = (query.get("path") or [""])[0]
            try:
                self._send_json(self.bridge.read_workspace_file(rel))
            except Exception as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/tasks":
            mgr = get_background_manager()
            tasks = [
                {
                    "task_id": t.task_id,
                    "command": t.command,
                    "cwd": t.cwd,
                    "status": "running" if t.is_running else "exited",
                    "pid": t.process.pid if t.process else None,
                    "exit_code": t.returncode,
                    "output": "\n".join(t.tail(40)),
                }
                for t in mgr.list_tasks()
            ]
            self._send_json({"tasks": tasks})
            return
        if route == "/api/skills":
            skills = [
                {
                    "name": s.name,
                    "description": s.description,
                    "path": str(s.path),
                    "active": s.name in self.bridge.active_skills,
                }
                for s in discover_skills(Path.cwd())
            ]
            self._send_json({"skills": skills})
            return
        if route == "/api/git":
            try:
                from neow.tools.git import git_diff, git_status

                self._send_json(
                    {
                        "branch": self.bridge._git_branch(),
                        "status": git_status() or "Working tree clean",
                        "diff": git_diff() or "",
                    }
                )
            except Exception as exc:
                self._send_json({"branch": "", "status": str(exc), "diff": ""})
            return

        if route.startswith("/api/"):
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        # Serve static UI files
        self._serve_static(route)

    def do_POST(self) -> None:
        if not self._authorize():
            return
        if self.headers.get_content_type() != "application/json":
            self._send_json(
                {"error": "Content-Type must be application/json"},
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            )
            return
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json()
        except Exception:
            self._send_json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return

        self.bridge._request_context.generation = body.get("workspace_generation")
        try:
            with self.bridge._lock:
                self.bridge._check_request_generation()
            if route == "/api/chat":
                prompt = str(body.get("prompt") or "").strip()
                if not prompt:
                    self._send_json({"error": "请输入消息内容"}, HTTPStatus.BAD_REQUEST)
                    return
                if not self.bridge.submit_prompt(prompt):
                    self._send_json(
                        {"error": "当前正在生成回复，请稍候或先点击停止"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                self._send_json({"ok": True})
            elif route == "/api/cancel":
                self.bridge.cancel()
                self._send_json({"ok": True})
            elif route == "/api/clear":
                self._send_json({"ok": True, "state": self.bridge.clear_session()})
            elif route == "/api/workspaces/switch":
                self._send_json(
                    {
                        "ok": True,
                        "state": self.bridge.switch_workspace(
                            str(body.get("path") or "")
                        ),
                    }
                )
            elif route == "/api/compact":
                summary = self.bridge.compact()
                self._send_json({"ok": True, "summary": summary})
            elif route == "/api/approval":
                req_id = str(body.get("id") or "")
                decision = str(body.get("decision") or "deny")
                ok = self.bridge.resolve_approval(req_id, decision)
                self._send_json({"ok": ok})
            elif route == "/api/ask_user":
                req_id = str(body.get("id") or "")
                answer = str(body.get("answer") or "")
                ok = self.bridge.resolve_ask_user(req_id, answer)
                self._send_json({"ok": ok})
            elif route == "/api/mode":
                self._send_json({"ok": True, **self.bridge.set_mode(body)})
            elif route == "/api/models/select":
                name = str(body.get("name") or "").strip()
                res = self.bridge.select_model(name)
                self._send_json({"ok": True, **res})
            elif route == "/api/models/save":
                res = self.bridge.save_model_entry(
                    body, activate=bool(body.get("activate", True))
                )
                self._send_json({"ok": True, **res})
            elif route == "/api/models/delete":
                name = str(body.get("name") or "").strip()
                res = self.bridge.delete_model_entry(name)
                self._send_json({"ok": True, **res})
            elif route == "/api/models/fetch":
                self._send_json({"ok": True, "models": self.bridge.fetch_models(body)})
            elif route == "/api/models/sync":
                self._send_json({"ok": True, **self.bridge.sync_models(body)})
            elif route == "/api/models/test":
                self._send_json({"ok": self.bridge.test_model(body)})
            elif route == "/api/goal":
                action = str(body.get("action") or "start")
                if action == "stop":
                    self.bridge.stop_goal()
                    self._send_json({"ok": True})
                else:
                    goal_text = str(body.get("goal") or "").strip()
                    ok = self.bridge.start_goal(goal_text)
                    self._send_json(
                        (
                            {"ok": True}
                            if ok
                            else {
                                "error": "无法启动自主任务，请检查任务内容并等待当前操作结束"
                            }
                        ),
                        HTTPStatus.OK if ok else HTTPStatus.CONFLICT,
                    )
            elif route == "/api/plan":
                action = str(body.get("action") or "generate")
                if action == "approve":
                    ok = self.bridge.approve_plan(str(body.get("plan") or ""))
                    self._send_json(
                        (
                            {"ok": True}
                            if ok
                            else {
                                "error": "无法执行计划，请等待当前操作结束并确认计划仍待审批"
                            }
                        ),
                        HTTPStatus.OK if ok else HTTPStatus.CONFLICT,
                    )
                else:
                    res = self.bridge.generate_plan(str(body.get("task") or ""))
                    self._send_json({"ok": True, **res})
            elif route == "/api/tasks/kill":
                task_id = str(body.get("task_id") or "")
                with self.bridge._lock:
                    self.bridge._check_request_generation()
                    ok = get_background_manager().stop(task_id)
                self._send_json({"ok": ok})
            elif route == "/api/skills/toggle":
                name = str(body.get("name") or "")
                self._send_json({"ok": True, "active": self.bridge.toggle_skill(name)})
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except SessionBusyError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except (ConfigError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            self.bridge._request_context.generation = None

    def _handle_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        sub = self.bridge.broadcaster.subscribe()
        try:
            # Send initial connected ping
            init_payload = json.dumps({"type": "connected", "ts": time.time()})
            self.wfile.write(f"data: {init_payload}\n\n".encode("utf-8"))
            self.wfile.flush()
            while True:
                try:
                    msg = sub.get(timeout=15.0)
                    raw = json.dumps(msg, ensure_ascii=False)
                    self.wfile.write(f"data: {raw}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.bridge.broadcaster.unsubscribe(sub)

    def _serve_static(self, route: str) -> None:
        rel = "index.html" if route in ("", "/") else route.lstrip("/")
        target = (STATIC_DIR / rel).resolve()
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            target = STATIC_DIR / "index.html"
        if not target.is_file():
            self._send_json({"error": "Static UI files missing"}, HTTPStatus.NOT_FOUND)
            return
        ctype, _ = mimetypes.guess_type(str(target))
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{ctype or 'text/html'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(content)


def _find_free_port(host: str, preferred: int = 7860) -> int:
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class WebServer:
    """Manage the lifecycle of the embedded Neow Web Studio HTTP server."""

    def __init__(
        self,
        bridge: WebSessionBridge,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self.bridge = bridge
        self.host = host
        self.port = port or _find_free_port(host, 7860)

        class BoundHandler(_WebRequestHandler):
            pass

        BoundHandler.bridge = bridge
        self._httpd = ThreadingHTTPServer((self.host, self.port), BoundHandler)
        self._httpd.daemon_threads = True
        self.port = int(self._httpd.server_address[1])
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start_background(self) -> str:
        if self._thread is not None and self._thread.is_alive():
            return self.url
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def serve_forever(self) -> None:
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass


def run_web_server(
    conversation: Any,
    *,
    config: Optional[Config] = None,
    token_tracker: Any = None,
    approval_policy: Optional[ApprovalPolicy] = None,
    event_bus: Any = None,
    web_fetcher: Any = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
    on_ready: Optional[Callable[[str], None]] = None,
) -> None:
    """Run Neow Web Studio in blocking mode (for `neow --web`)."""
    bridge = WebSessionBridge(
        conversation,
        config=config,
        token_tracker=token_tracker,
        approval_policy=approval_policy,
        event_bus=event_bus,
        web_fetcher=web_fetcher,
    )
    server = WebServer(bridge, host=host, port=port)
    url = server.url
    if on_ready:
        on_ready(url)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
