"""JSONL-backed session tree for Neow CLI.

Each session is a single .jsonl file:
  Line 0  → metadata header  {"type":"meta","name":…,"model":…,"leafId":…,"createdAt":…}
  Line 1+ → message entries   {"id":…,"parentId":…,"role":…,"content":…,"timestamp":…,"metadata":…}
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from neow.utils.logger import logger


class SessionTree:
    """Append-only JSONL session storage with tree structure."""

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _new_id() -> str:
        return uuid4().hex

    def _path(self, name: str) -> Path:
        return self.sessions_dir / f"{name}.jsonl"

    def _read_lines(self, name: str) -> List[dict]:
        path = self._path(name)
        if not path.exists():
            return []
        lines = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if raw:
                lines.append(json.loads(raw))
        return lines

    def _write_lines(self, name: str, lines: List[dict]) -> None:
        path = self._path(name)
        with open(path, "w", encoding="utf-8") as f:
            for entry in lines:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _append_line(self, name: str, entry: dict) -> None:
        path = self._path(name)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _read_meta(self, name: str) -> Optional[dict]:
        lines = self._read_lines(name)
        if lines and lines[0].get("type") == "meta":
            return lines[0]
        return None

    def _update_meta(self, name: str, **fields) -> None:
        lines = self._read_lines(name)
        if not lines or lines[0].get("type") != "meta":
            return
        lines[0].update(fields)
        self._write_lines(name, lines)

    # ── public API ─────────────────────────────────────────────────────────

    def create(self, name: str, model: str) -> str:
        """Create a new JSONL session. Returns the session name."""
        meta = {
            "type": "meta",
            "name": name,
            "model": model,
            "leafId": None,
            "createdAt": datetime.now().isoformat(),
        }
        self._append_line(name, meta)
        logger.info(f"Session tree created: {name}")
        return name

    def append(
        self,
        name: str,
        role: str,
        content: Any,
        metadata: Optional[dict] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        """Append a message entry. Returns the new entry id."""
        meta = self._read_meta(name)
        if meta is None:
            raise FileNotFoundError(f"Session not found: {name}")

        entry_id = self._new_id()
        leaf_id = meta.get("leafId")
        resolved_parent = parent_id if parent_id is not None else leaf_id

        entry: Dict[str, Any] = {
            "id": entry_id,
            "parentId": resolved_parent,
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        if metadata:
            entry["metadata"] = metadata

        self._append_line(name, entry)
        self._update_meta(name, leafId=entry_id)
        return entry_id

    def get_messages(self, name: str) -> List[Dict[str, Any]]:
        """Reconstruct linear conversation by walking leaf→root."""
        lines = self._read_lines(name)
        if not lines:
            return []

        by_id: Dict[str, dict] = {}
        for entry in lines:
            if entry.get("type") == "meta":
                continue
            by_id[entry["id"]] = entry

        meta = lines[0] if lines[0].get("type") == "meta" else None
        leaf_id = meta.get("leafId") if meta else None
        if not leaf_id or leaf_id not in by_id:
            return []

        chain: List[dict] = []
        current = leaf_id
        while current and current in by_id:
            chain.append(by_id[current])
            current = by_id[current].get("parentId")
        chain.reverse()

        messages: List[Dict[str, Any]] = []
        for entry in chain:
            msg: Dict[str, Any] = {
                "role": entry["role"],
                "content": entry["content"],
            }
            if "metadata" in entry:
                # Flatten common metadata keys into the message dict
                for k, v in entry["metadata"].items():
                    msg[k] = v
            messages.append(msg)
        return messages

    def get_leaf_id(self, name: str) -> Optional[str]:
        """Return the current leafId for a session."""
        meta = self._read_meta(name)
        if meta is None:
            return None
        return meta.get("leafId")

    def set_leaf_id(self, name: str, leaf_id: str) -> None:
        """Update the leafId pointer."""
        self._update_meta(name, leafId=leaf_id)

    def get_tree(self, name: str) -> Dict[str, Any]:
        """Return full tree: {id: {id, parentId, role, content_preview, children}}."""
        lines = self._read_lines(name)
        nodes: Dict[str, Dict[str, Any]] = {}
        for entry in lines:
            if entry.get("type") == "meta":
                continue
            eid = entry["id"]
            content = entry.get("content", "")
            if isinstance(content, list):
                preview = "[multipart content]"
            else:
                preview = str(content)[:80]
            nodes[eid] = {
                "id": eid,
                "parentId": entry.get("parentId"),
                "role": entry.get("role"),
                "content_preview": preview,
                "children": [],
            }
        # Wire children
        for nid, node in nodes.items():
            pid = node["parentId"]
            if pid and pid in nodes:
                nodes[pid]["children"].append(nid)
        return nodes

    def branch_at(self, name: str, entry_id: str) -> str:
        """Set leafId to entry_id, effectively branching. Returns entry_id."""
        # Verify entry exists
        lines = self._read_lines(name)
        by_id = {e["id"]: e for e in lines if e.get("type") != "meta"}
        if entry_id not in by_id:
            raise ValueError(f"Entry not found: {entry_id}")

        current_leaf = self.get_leaf_id(name)
        if current_leaf and current_leaf != entry_id:
            # Mark orphaned path in metadata for future reference
            orphans = self._find_orphans(lines, current_leaf, entry_id)
            if orphans:
                logger.info(
                    f"Branching at {entry_id[:8]}: {len(orphans)} orphaned messages"
                )

        self.set_leaf_id(name, entry_id)
        return entry_id

    def _find_orphans(
        self, lines: List[dict], current_leaf: str, target_id: str
    ) -> List[str]:
        """Find entry ids that will be unreachable after branching."""
        by_id = {e["id"]: e for e in lines if e.get("type") != "meta"}

        # Build ancestor set of target
        target_ancestors = set()
        cur = target_id
        while cur and cur in by_id:
            target_ancestors.add(cur)
            cur = by_id[cur].get("parentId")

        # Walk current leaf path; entries not in target ancestors are orphans
        orphans = []
        cur = current_leaf
        while cur and cur in by_id:
            if cur not in target_ancestors:
                orphans.append(cur)
            cur = by_id[cur].get("parentId")
        return orphans

    def get_children(self, name: str, entry_id: str) -> List[str]:
        """Return all direct child entry ids of the given entry."""
        lines = self._read_lines(name)
        children = []
        for entry in lines:
            if entry.get("type") == "meta":
                continue
            if entry.get("parentId") == entry_id:
                children.append(entry["id"])
        return children

    def delete_session(self, name: str) -> bool:
        """Delete the JSONL file. Returns True if deleted."""
        path = self._path(name)
        if path.exists():
            os.remove(path)
            logger.info(f"Session tree deleted: {name}")
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all JSONL sessions sorted by creation date (newest first)."""
        sessions = []
        for f in self.sessions_dir.glob("*.jsonl"):
            meta = self._read_meta(f.stem)
            if meta:
                sessions.append({
                    "name": meta.get("name", f.stem),
                    "model": meta.get("model", "unknown"),
                    "created_at": meta.get("createdAt", ""),
                    "leaf_id": meta.get("leafId"),
                })
        sessions.sort(key=lambda s: s["created_at"], reverse=True)
        return sessions

    def find_session(self, name: str) -> Optional[Path]:
        """Fuzzy-find a session file by name."""
        exact = self._path(name)
        if exact.exists():
            return exact
        for f in self.sessions_dir.glob("*.jsonl"):
            if name in f.stem:
                return f
        return None

    # ── legacy import / export ─────────────────────────────────────────────

    def export_to_legacy(self, name: str) -> Dict[str, Any]:
        """Export JSONL session to old JSON format dict."""
        meta = self._read_meta(name)
        if not meta:
            raise FileNotFoundError(f"Session not found: {name}")
        messages = self.get_messages(name)
        return {
            "name": meta.get("name", name),
            "created_at": meta.get("createdAt", ""),
            "model": meta.get("model", "unknown"),
            "messages": messages,
            "context_files": {},
            "web_cache": {},
            "system_prompt": "",
        }

    def import_from_legacy(self, data: Dict[str, Any], name: str) -> str:
        """Import from old JSON format, creating a JSONL session. Returns name."""
        model = data.get("model", "unknown")
        self.create(name, model)

        messages = data.get("messages", [])
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # Separate known metadata fields from the message
            metadata_keys = {"tool_call_id", "tool_calls", "type", "name"}
            meta = {k: msg[k] for k in metadata_keys if k in msg}
            self.append(name, role, content, metadata=meta if meta else None)

        logger.info(f"Imported legacy session: {name}")
        return name
