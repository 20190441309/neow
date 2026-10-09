"""File checkpoints for ``/rewind``.

Every user turn opens a checkpoint. The first time a tool changes a file in
that turn, the file's previous content (or the fact that it did not exist)
is saved under ``~/.neow/checkpoints/<session>/<turn>/``. Rewinding to a
turn restores every file changed since then and can also cut the
conversation back to just before that turn.

Only changes made through Neow's file tools are tracked: what a shell
command (``execute_command``) or an MCP tool changed cannot be undone, and
``/rewind`` says so. Git history is never touched.
"""

import json
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from neow.utils.logger import logger

ROOT = Path.home() / ".neow" / "checkpoints"
KEEP_TURNS = 50
KEEP_SESSIONS = 20


@dataclass
class RewindResult:
    restored: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)  # changes we cannot undo
    messages_removed: int = 0

    def summary(self) -> str:
        lines = []
        if self.restored:
            lines.append(
                f"已恢复 {len(self.restored)} 个文件：{', '.join(self.restored)}"
            )
        if self.deleted:
            lines.append(f"已删除新建的文件：{', '.join(self.deleted)}")
        if self.messages_removed:
            lines.append(f"对话已回退（移除 {self.messages_removed} 条消息）")
        if not lines:
            lines.append("没有需要恢复的内容")
        if self.commands:
            shown = "; ".join(c[:60] for c in self.commands[:5])
            lines.append(f"⚠ 以下命令造成的改动无法回退：{shown}")
        return "\n".join(lines)


class CheckpointStore:
    """Checkpoints of one Neow session."""

    def __init__(
        self,
        root: Path = ROOT,
        session_id: Optional[str] = None,
        keep_turns: int = KEEP_TURNS,
    ):
        self.session_id = session_id or (
            time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        )
        self.root = Path(root)
        self.dir = self.root / self.session_id
        self.keep_turns = keep_turns
        self.current: Optional[int] = None
        self._lock = threading.Lock()
        self._next = 1 + max((t["turn"] for t in self.turns()), default=0)

    # -- recording ------------------------------------------------------

    def begin_turn(self, prompt: str, message_index: int) -> int:
        """Open the checkpoint for a new user turn."""
        with self._lock:
            turn = self._next
            self._next += 1
            self.current = turn
            self._write_meta(
                turn,
                {
                    "turn": turn,
                    "prompt": prompt,
                    "created": time.time(),
                    "message_index": message_index,
                    "files": {},
                    "commands": [],
                },
            )
            self._prune()
        return turn

    def before_mutation(self, file_path: str) -> None:
        """Save *file_path* as it was before this turn first changed it."""
        if self.current is None or not file_path:
            return
        path = str(Path(file_path).expanduser().resolve())
        with self._lock:
            meta = self._read_meta(self.current)
            if meta is None or path in meta["files"]:
                return
            source = Path(path)
            blob = None
            if source.is_file():
                blob = f"{len(meta['files'])}.bak"
                target = self._turn_dir(self.current) / "files" / blob
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            meta["files"][path] = blob  # None: the file did not exist
            self._write_meta(self.current, meta)

    def note_command(self, command: str) -> None:
        """Remember a shell command: its changes cannot be rewound."""
        if self.current is None:
            return
        with self._lock:
            meta = self._read_meta(self.current)
            if meta is not None:
                meta["commands"].append(command)
                self._write_meta(self.current, meta)

    # -- listing --------------------------------------------------------

    def turns(self) -> List[Dict[str, Any]]:
        """Checkpoints, oldest first."""
        found = []
        if self.dir.is_dir():
            for child in self.dir.iterdir():
                if child.name.isdigit():
                    meta = self._read_meta(int(child.name))
                    if meta is not None:
                        found.append(meta)
        return sorted(found, key=lambda m: m["turn"])

    def describe(self) -> str:
        turns = self.turns()
        if not turns:
            return "还没有检查点：每轮对话开始时自动创建。"
        lines = ["检查点（/rewind <编号> [files|chat|both]，默认 both）："]
        for meta in reversed(turns):
            prompt = " ".join(meta["prompt"].split())[:50]
            note = f"{len(meta['files'])} 个文件"
            if meta["commands"]:
                note += f" · {len(meta['commands'])} 条命令"
            lines.append(f"  #{meta['turn']}  {note}  “{prompt}”")
        return "\n".join(lines)

    # -- rewinding ------------------------------------------------------

    def rewind(
        self,
        turn: int,
        *,
        files: bool = True,
        conversation: Any = None,
    ) -> RewindResult:
        """Undo turn *turn* and everything after it.

        Files: each file changed since then gets the content it had before
        the earliest of those turns touched it (created files are deleted).
        Conversation: messages from that turn on are removed; they are kept
        in the checkpoint directory as ``discarded-<turn>.json``.
        """
        with self._lock:
            later = [m for m in self.turns() if m["turn"] >= turn]
            if not later or later[0]["turn"] != turn:
                raise ValueError(f"no checkpoint #{turn}")
            result = RewindResult()
            for meta in later:
                result.commands.extend(meta["commands"])
            if files:
                self._restore(later, result)
            if conversation is not None:
                index = later[0]["message_index"]
                removed = conversation.messages[index:]
                if removed:
                    (self.dir / f"discarded-{turn}.json").write_text(
                        json.dumps(removed, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )
                del conversation.messages[index:]
                result.messages_removed = len(removed)
            if files:
                for meta in later:
                    shutil.rmtree(self._turn_dir(meta["turn"]), ignore_errors=True)
                self.current = None
        return result

    def _restore(self, later: List[Dict[str, Any]], result: RewindResult) -> None:
        originals: Dict[str, tuple] = {}
        for meta in later:  # oldest first: the first record is the original
            for path, blob in meta["files"].items():
                originals.setdefault(path, (meta["turn"], blob))
        for path, (turn, blob) in originals.items():
            target = Path(path)
            try:
                if blob is None:
                    if target.exists():
                        target.unlink()
                        result.deleted.append(path)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(self._turn_dir(turn) / "files" / blob, target)
                    result.restored.append(path)
            except OSError as exc:
                logger.warning(f"Rewind could not restore {path}: {exc}")

    # -- storage --------------------------------------------------------

    def _turn_dir(self, turn: int) -> Path:
        return self.dir / str(turn)

    def _read_meta(self, turn: int) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(
                (self._turn_dir(turn) / "meta.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            return None

    def _write_meta(self, turn: int, meta: Dict[str, Any]) -> None:
        path = self._turn_dir(turn) / "meta.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    def _prune(self) -> None:
        turns = sorted(int(c.name) for c in self.dir.iterdir() if c.name.isdigit())
        for old in turns[: -self.keep_turns]:
            shutil.rmtree(self._turn_dir(old), ignore_errors=True)
        sessions = sorted(
            (c for c in self.root.iterdir() if c.is_dir()),
            key=lambda c: c.stat().st_mtime,
        )
        for old in sessions[:-KEEP_SESSIONS]:
            if old != self.dir:
                shutil.rmtree(old, ignore_errors=True)


def rewind_command(store: Optional[CheckpointStore], args: str, conversation: Any):
    """``/rewind`` and ``/rewind <n> [files|chat|both]``: ``(text, kind)``."""
    if store is None:
        return "检查点未启用。", "warn"
    parts = args.split()
    if not parts:
        return store.describe(), "info"
    number = parts[0].lstrip("#")
    mode = parts[1] if len(parts) > 1 else "both"
    if not number.isdigit() or mode not in ("files", "chat", "both") or len(parts) > 2:
        return "Usage: /rewind  |  /rewind <编号> [files|chat|both]", "error"
    try:
        result = store.rewind(
            int(number),
            files=mode in ("files", "both"),
            conversation=conversation if mode in ("chat", "both") else None,
        )
    except ValueError as exc:
        return str(exc), "error"
    return result.summary(), "warn" if result.commands else "info"


__all__ = ["CheckpointStore", "RewindResult", "rewind_command"]
