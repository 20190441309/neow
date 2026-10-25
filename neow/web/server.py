"""HTTP + SSE server and WebSessionBridge for Neow Web Studio."""

from __future__ import annotations

import difflib
import json
import mimetypes
import os
import queue
import socket
import threading
import time
import uuid
import webbrowser
from concurrent.futures import Future
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.background_tasks import get_background_manager
from neow.core.config import Config, ConfigError
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

STATIC_DIR = Path(__file__).parent / "static"
WRITE_TOOLS = {"write_file", "edit_file", "create_file", "hashline_edit"}


class EventBroadcaster:
    """Thread-safe SSE broadcaster with in-memory event log."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: List[queue.Queue] = []

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
        msg = {"type": event_type, "ts": time.time(), **payload}
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
        self.approval_policy = approval_policy or getattr(
            getattr(conversation, "tool_executor", None),
            "approval_policy",
            ApprovalPolicy(),
        )
        self.event_bus = event_bus
        self.web_fetcher = web_fetcher
        self.broadcaster = EventBroadcaster()

        self._lock = threading.Lock()
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._pending_questions: Dict[str, Dict[str, Any]] = {}
        self._file_snapshots: Dict[str, str] = {}
        self.timeline: List[Dict[str, Any]] = []
        self.goal_state = GoalState(goal="", active=False)
        self.current_plan: str = ""
        self.plan_pending_approval: bool = False
        self.active_skills: set[str] = set()

        # Wire approval & ask_user callbacks on the executor
        executor = getattr(self.conversation, "tool_executor", None)
        if executor is not None:
            executor.approval_policy = self.approval_policy
            executor.confirm_callback = ApprovalBridge(request=self._on_approval_req)
            executor.ask_user_callback = self._on_ask_user_req

        self.controller = ChatController(
            self.conversation,
            event_callback=self._on_controller_event,
            approval_bridge=(executor.confirm_callback if executor else None),
            token_tracker=self.token_tracker,
            event_bus=self.event_bus,
            web_fetcher=self.web_fetcher,
        )

    # -- state snapshot ------------------------------------------------

    def get_state_snapshot(self) -> Dict[str, Any]:
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
            "busy": self.controller.busy,
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
        return {
            "input_tokens": getattr(tracker, "total_input_tokens", 0),
            "output_tokens": getattr(tracker, "total_output_tokens", 0),
            "total_tokens": getattr(tracker, "total_tokens", 0),
            "cost": round(float(getattr(tracker, "total_cost", 0.0) or 0.0), 4),
        }

    @staticmethod
    def _git_branch() -> str:
        try:
            from neow.tools.git import current_branch

            return current_branch() or ""
        except Exception:
            return ""

    # -- controller event handling -------------------------------------

    def _on_controller_event(self, event: Any) -> None:
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
                },
            )
            self._handle_post_turn_goal(event.content, event.cancelled)
        elif isinstance(event, TurnFailed):
            with self._lock:
                self.timeline.append({"kind": "error", "message": event.message})
            if self.goal_state.active:
                self.goal_state.active = False
                self._broadcast_goal()
            self.broadcaster.publish("turn_failed", {"message": event.message})

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
        with self._lock:
            item = self._pending_approvals.pop(req_id, None)
        if not item:
            return False
        future: Future = item["future"]
        tool: str = item["tool"]
        approved = decision in ("allow_once", "allow_always")
        if decision == "allow_always" and self.approval_policy is not None:
            try:
                self.approval_policy.set_tool_override(tool, "allow")
            except Exception:
                pass
        if not future.done():
            future.set_result(approved)
        self.broadcaster.publish(
            "approval_resolved",
            {"id": req_id, "tool": tool, "decision": decision, "approved": approved},
        )
        return True

    def _on_ask_user_req(
        self, question: str, options: Optional[List[str]] = None
    ) -> str:
        req_id = uuid.uuid4().hex[:10]
        future: Future = Future()
        opts = list(options or [])
        with self._lock:
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
                self._pending_questions.pop(req_id, None)

    def resolve_ask_user(self, req_id: str, answer: str) -> bool:
        with self._lock:
            item = self._pending_questions.pop(req_id, None)
        if not item:
            return False
        future: Future = item["future"]
        if not future.done():
            future.set_result(answer)
        self.broadcaster.publish("ask_user_resolved", {"id": req_id, "answer": answer})
        return True

    # -- chat, goal, plan actions --------------------------------------

    def submit_prompt(self, prompt: str, *, display_prompt: str = "") -> bool:
        text = (prompt or "").strip()
        if not text or self.controller.busy:
            return False
        shown = (display_prompt or text).strip()
        with self._lock:
            self.timeline.append({"kind": "user", "text": shown})
        self.broadcaster.publish("user_message", {"text": shown})
        threading.Thread(
            target=self.controller.run_turn, args=(text,), daemon=True
        ).start()
        return True

    def start_goal(self, goal_text: str) -> bool:
        text = (goal_text or "").strip()
        if not text or self.controller.busy:
            return False
        self.goal_state = GoalState(goal=text, active=True, current_round=1)
        self._broadcast_goal()
        kickoff = build_goal_initial_prompt(text)
        return self.submit_prompt(
            kickoff,
            display_prompt=(
                f"🎯 启动 /goal 自主模式 "
                f"(Round 1/{self.goal_state.max_rounds}): {text}"
            ),
        )

    def stop_goal(self) -> None:
        self.goal_state.active = False
        self._broadcast_goal()
        if self.controller.busy:
            self.controller.cancel()

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

        def _delayed_next() -> None:
            time.sleep(0.3)
            if self.goal_state.active and not self.controller.busy:
                self.submit_prompt(
                    next_prompt,
                    display_prompt=(
                        f"🔄 /goal 自动推进 Round "
                        f"{self.goal_state.current_round}/{self.goal_state.max_rounds}"
                    ),
                )

        threading.Thread(target=_delayed_next, daemon=True).start()

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
        self.current_plan = (res.content or "").strip()
        self.plan_pending_approval = True
        self.broadcaster.publish(
            "plan_updated",
            {"text": self.current_plan, "pending": self.plan_pending_approval},
        )
        return {"text": self.current_plan, "pending": True}

    def approve_plan(self, edited_plan: str = "") -> bool:
        plan_body = (edited_plan or self.current_plan).strip()
        if not plan_body:
            return False
        self.current_plan = plan_body
        self.plan_pending_approval = False
        self.broadcaster.publish(
            "plan_updated", {"text": self.current_plan, "pending": False}
        )
        exec_prompt = (
            "The user has APPROVED the following implementation plan. "
            "Execute it step by step and verify your changes:\n\n"
            f"{plan_body}"
        )
        return self.submit_prompt(
            exec_prompt, display_prompt="✅ 已批准实施计划，开始按步骤执行"
        )

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

    def select_model(self, name: str) -> Dict[str, Any]:
        if self.controller.busy:
            raise ConfigError("请等待当前对话回合结束后再切换模型")
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

    def save_model_entry(
        self, payload: Dict[str, Any], *, activate: bool = True
    ) -> Dict[str, Any]:
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

        validate_model_entry(name, entry)
        self.config.save_model(name, entry)
        if activate:
            try:
                return self.select_model(name)
            except Exception:
                pass
        return {"saved": name}

    def delete_model_entry(self, name: str) -> Dict[str, Any]:
        client = getattr(self.conversation, "model_client", None)
        active = getattr(client, "config_name", None)
        if name == active:
            raise ConfigError("无法删除当前正在使用的模型，请先切换到其他模型")
        if len(self.config.models) <= 1:
            raise ConfigError("至少需要保留一个模型配置")
        self.config.delete_model(name)
        return {"deleted": name}

    # -- workspace files, tasks, skills --------------------------------

    def list_workspace_files(self, limit: int = 200) -> List[Dict[str, Any]]:
        root = Path.cwd()
        ignored = {
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
        files: List[Dict[str, Any]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(
                d for d in dirnames if d not in ignored and not d.startswith(".")
            )
            for fname in sorted(filenames):
                if fname.startswith(".") and fname not in (".neow.json",):
                    continue
                full = Path(dirpath) / fname
                try:
                    rel = full.relative_to(root).as_posix()
                    size = full.stat().st_size
                except OSError:
                    continue
                files.append({"path": rel, "size": size})
                if len(files) >= limit:
                    return files
        return files

    def read_workspace_file(self, rel_path: str) -> Dict[str, Any]:
        root = Path.cwd().resolve()
        target = (root / rel_path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise ConfigError("文件路径无效或不存在")
        content = target.read_text(encoding="utf-8", errors="replace")
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
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
            self._send_json({"files": self.bridge.list_workspace_files()})
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

        # Serve static UI files
        self._serve_static(route)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json()
        except Exception:
            self._send_json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return

        try:
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
                self.bridge.controller.cancel()
                self._send_json({"ok": True})
            elif route == "/api/clear":
                if self.bridge.controller.busy:
                    self.bridge.controller.cancel()
                self.bridge.conversation.clear_history()
                with self.bridge._lock:
                    self.bridge.timeline.clear()
                self.bridge.broadcaster.publish("cleared", {})
                self._send_json({"ok": True})
            elif route == "/api/compact":
                summary = self.bridge.conversation.compact()
                self.bridge.broadcaster.publish(
                    "notice", {"message": f"上下文已压缩: {summary}", "level": "info"}
                )
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
                mode_val = body.get("approval_mode")
                if mode_val in ("always-ask", "write", "yolo"):
                    self.bridge.approval_policy.set_mode(ApprovalMode(mode_val))
                effort_val = body.get("effort")
                client = getattr(self.bridge.conversation, "model_client", None)
                if effort_val in ("off", "low", "medium", "high") and client:
                    client.effort = None if effort_val == "off" else effort_val
                self._send_json(
                    {
                        "ok": True,
                        "approval_mode": self.bridge.approval_policy.mode.value,
                        "effort": getattr(client, "effort", None) or "off",
                    }
                )
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
                base_url = str(body.get("base_url") or "").strip()
                api_key = str(body.get("api_key") or "").strip()
                api_key_env = str(body.get("api_key_env") or "").strip()
                items = fetch_endpoint_models(
                    base_url, api_key=api_key, api_key_env=api_key_env
                )
                self._send_json({"ok": True, "models": [m["id"] for m in items]})
            elif route == "/api/models/sync":
                base_url = str(body.get("base_url") or "").strip()
                api_key = str(body.get("api_key") or "").strip()
                api_key_env = str(body.get("api_key_env") or "").strip()
                prefix = str(body.get("prefix") or "magpie").strip()
                if base_url:
                    count = sync_gateway_models(
                        self.bridge.config,
                        base_url=base_url,
                        api_key=api_key,
                        api_key_env=api_key_env,
                        prefix=prefix,
                    )
                else:
                    count = sync_magpie(self.bridge.config)
                preferred = get_preferred_magpie_model(self.bridge.config)
                if (
                    preferred
                    and getattr(self.bridge.conversation, "model_client", None) is None
                ):
                    try:
                        self.bridge.select_model(preferred)
                    except Exception:
                        pass
                self._send_json(
                    {"ok": True, "count": count, "preferred": preferred or ""}
                )
            elif route == "/api/models/test":
                name = str(body.get("name") or "test").strip() or "test"
                entry = {
                    "provider": str(
                        body.get("provider") or "openai-compatible"
                    ).strip(),
                    "base_url": str(body.get("base_url") or "").strip(),
                    "model": str(body.get("model") or "").strip(),
                    "api_key": str(body.get("api_key") or "").strip(),
                    "api_key_env": str(body.get("api_key_env") or "").strip(),
                }
                if (
                    not entry["api_key"]
                    and not entry["api_key_env"]
                    and is_local_endpoint(entry["base_url"])
                ):
                    entry["api_key"] = "local"
                validate_model_entry(name, entry)
                client = build_model_client(entry, name)
                sdk = getattr(client, "client", None)
                if sdk is not None and hasattr(sdk, "with_options"):
                    client.client = sdk.with_options(timeout=5, max_retries=0)
                ok = client.validate_connection()
                self._send_json({"ok": ok})
            elif route == "/api/goal":
                action = str(body.get("action") or "start")
                if action == "stop":
                    self.bridge.stop_goal()
                    self._send_json({"ok": True})
                else:
                    goal_text = str(body.get("goal") or "").strip()
                    ok = self.bridge.start_goal(goal_text)
                    self._send_json({"ok": ok})
            elif route == "/api/plan":
                action = str(body.get("action") or "generate")
                if action == "approve":
                    ok = self.bridge.approve_plan(str(body.get("plan") or ""))
                    self._send_json({"ok": ok})
                else:
                    res = self.bridge.generate_plan(str(body.get("task") or ""))
                    self._send_json({"ok": True, **res})
            elif route == "/api/tasks/kill":
                task_id = str(body.get("task_id") or "")
                ok = get_background_manager().stop(task_id)
                self._send_json({"ok": ok})
            elif route == "/api/skills/toggle":
                name = str(body.get("name") or "")
                if name in self.bridge.active_skills:
                    self.bridge.active_skills.remove(name)
                    active = False
                else:
                    content = load_skill_content(name, Path.cwd())
                    if content.startswith("Error:"):
                        self._send_json({"error": content}, HTTPStatus.NOT_FOUND)
                        return
                    self.bridge.active_skills.add(name)
                    if hasattr(self.bridge.conversation, "add_message"):
                        self.bridge.conversation.add_message(
                            "system", f"Activated skill '{name}':\n{content}"
                        )
                    active = True
                self._send_json({"ok": True, "active": active})
            else:
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ConfigError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_sse(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
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
