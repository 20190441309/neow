"""Background daemon/task manager for long-running processes."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional


@dataclass
class BackgroundTask:
    """State of a single background process."""

    task_id: str
    command: str
    cwd: str
    process: subprocess.Popen
    started_at: float = field(default_factory=time.time)
    lines: Deque[str] = field(default_factory=lambda: deque(maxlen=500))
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    @property
    def returncode(self) -> Optional[int]:
        return self.process.poll()

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.time() - self.started_at)

    def append_line(self, line: str) -> None:
        with self._lock:
            self.lines.append(line.rstrip("\r\n"))

    def tail(self, count: int = 50) -> List[str]:
        with self._lock:
            items = list(self.lines)
        return items[-max(1, count) :]


class BackgroundTaskManager:
    """Manages background processes spawned during a session."""

    def __init__(self) -> None:
        self._tasks: Dict[str, BackgroundTask] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def start(self, command: str, cwd: Optional[str] = None) -> BackgroundTask:
        """Start a command in the background and buffer its output."""
        from pathlib import Path
        from neow.tools.command import _get_shell_for_windows, get_session_cwd

        effective_cwd = cwd or str(get_session_cwd() or Path.cwd())
        with self._lock:
            self._counter += 1
            task_id = f"bg-{self._counter}"

        options = dict(
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            cwd=effective_cwd,
        )
        if sys.platform == "win32":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            shell_path = _get_shell_for_windows()
            if shell_path:
                proc = subprocess.Popen(
                    [shell_path, "-NoProfile", "-Command", command], **options
                )
            else:
                proc = subprocess.Popen(command, shell=True, **options)
        else:
            proc = subprocess.Popen(
                command, shell=True, start_new_session=True, **options
            )

        task = BackgroundTask(
            task_id=task_id,
            command=command,
            cwd=effective_cwd,
            process=proc,
        )
        with self._lock:
            self._tasks[task_id] = task

        reader = threading.Thread(
            target=self._read_output,
            args=(task,),
            daemon=True,
            name=f"neow-{task_id}",
        )
        reader.start()
        return task

    @staticmethod
    def _read_output(task: BackgroundTask) -> None:
        stream = task.process.stdout
        if stream is None:
            return
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                task.append_line(line)
        except Exception:
            pass

    def get(self, task_id: str) -> Optional[BackgroundTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> List[BackgroundTask]:
        with self._lock:
            return list(self._tasks.values())

    def stop(self, task_id: str) -> bool:
        """Stop a running background task by ID."""
        task = self.get(task_id)
        if task is None:
            return False
        proc = task.process
        if proc.poll() is not None:
            return True
        if sys.platform == "win32":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
                proc.wait(0.5)
            except Exception:
                pass
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            import os

            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(proc.pid, sig)
                    proc.wait(0.5)
                    break
                except Exception:
                    continue
        return True

    def stop_all(self) -> int:
        """Stop all running background tasks. Returns number stopped."""
        stopped = 0
        for task in self.list_tasks():
            if task.is_running:
                self.stop(task.task_id)
                stopped += 1
        return stopped


# Global singleton manager for the active process
_GLOBAL_MANAGER = BackgroundTaskManager()


def get_background_manager() -> BackgroundTaskManager:
    """Return the global background task manager."""
    return _GLOBAL_MANAGER


def background_task(
    action: str,
    command: str = "",
    task_id: str = "",
    lines: int = 50,
) -> str:
    """Manage background tasks (start, status, output, stop, list).

    Args:
        action: One of 'start', 'status', 'output', 'stop', 'list'.
        command: Shell command to start when action == 'start'.
        task_id: Task ID (e.g. 'bg-1') for 'status', 'output', or 'stop'.
        lines: Number of recent log lines to return (default 50).

    Returns:
        Formatted status or output string.
    """
    manager = get_background_manager()
    act = (action or "list").strip().lower()

    if act == "start":
        if not command.strip():
            return "Error: 'command' is required when action is 'start'."
        task = manager.start(command.strip())
        # Wait briefly to capture immediate startup errors or port bindings
        time.sleep(0.15)
        preview = "\n".join(task.tail(10))
        status_str = "running" if task.is_running else f"exited ({task.returncode})"
        msg = (
            f"Started background task {task.task_id} [{status_str}] "
            f"(PID {task.process.pid}): {task.command}"
        )
        if preview:
            msg += f"\nInitial output:\n{preview}"
        return msg

    if act == "list":
        tasks = manager.list_tasks()
        if not tasks:
            return "No background tasks."
        out = []
        for t in tasks:
            st = "running" if t.is_running else f"exited ({t.returncode})"
            out.append(f"{t.task_id}  [{st}]  {int(t.elapsed_seconds)}s  {t.command}")
        return "\n".join(out)

    if act in ("status", "output"):
        if not task_id:
            return "Error: 'task_id' is required for status/output."
        task = manager.get(task_id)
        if task is None:
            return f"Error: unknown background task '{task_id}'."
        st = "running" if task.is_running else f"exited ({task.returncode})"
        log_lines = "\n".join(task.tail(lines)) or "(no output yet)"
        return (
            f"Task {task.task_id} [{st}] ({int(task.elapsed_seconds)}s): "
            f"{task.command}\n{log_lines}"
        )

    if act == "stop":
        if not task_id:
            return "Error: 'task_id' is required for stop."
        task = manager.get(task_id)
        if task is None:
            return f"Error: unknown background task '{task_id}'."
        manager.stop(task_id)
        return f"Stopped background task {task_id}: {task.command}"

    return (
        f"Error: unknown action '{action}'. "
        "Valid actions: start, list, status, output, stop."
    )
