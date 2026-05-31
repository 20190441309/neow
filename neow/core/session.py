"""Session persistence for Neow CLI."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from neow.utils.logger import logger


class SessionManager:
    """Manages session save/load/list/delete as JSON files."""

    def __init__(self, sessions_dir: Path):
        """Initialize session manager.

        Args:
            sessions_dir: Directory to store session files.
        """
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._session_tree = None  # lazy init

    def save(self, conversation: Any, name: Optional[str] = None) -> str:
        """Save current conversation to a JSON file.

        Args:
            conversation: ConversationManager instance.
            name: Optional session name. Auto-generated if None.

        Returns:
            Session name.
        """
        if not name:
            name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        data = {
            "name": name,
            "created_at": datetime.now().isoformat(),
            "model": getattr(conversation.model_client, "model", "unknown"),
            "messages": conversation.messages,
            "context_files": conversation.context_files,
            "web_cache": conversation.web_cache,
            "system_prompt": conversation.system_prompt,
        }

        file_path = self.sessions_dir / f"{name}.json"
        file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Session saved: {name}")
        return name

    def load(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a session by name (fuzzy match).

        Args:
            name: Session name to search for.

        Returns:
            Session data dict, or None if not found.
        """
        file_path = self._find_session(name)
        if not file_path:
            return None

        data = json.loads(file_path.read_text(encoding="utf-8"))
        logger.info(f"Session loaded: {data.get('name', name)}")
        return data

    def restore(self, name: str, conversation: Any) -> bool:
        """Restore a session into a ConversationManager.

        Args:
            name: Session name.
            conversation: ConversationManager to restore into.

        Returns:
            True if restored, False if session not found.
        """
        data = self.load(name)
        if not data:
            return False

        conversation.messages.clear()
        conversation.messages.extend(data.get("messages", []))
        conversation.context_files.clear()
        conversation.context_files.update(data.get("context_files", {}))
        conversation.web_cache.clear()
        # Restore web cache — WebContent is a simple dataclass, reconstruct from dict
        for url, wc_data in data.get("web_cache", {}).items():
            if isinstance(wc_data, dict) and "url" in wc_data:
                from neow.tools.web import WebContent
                conversation.web_cache[url] = WebContent(
                    url=wc_data.get("url", url),
                    title=wc_data.get("title", ""),
                    text=wc_data.get("text", ""),
                    code_blocks=[tuple(b) for b in wc_data.get("code_blocks", [])],
                    content_type=wc_data.get("content_type", "webpage"),
                )
            elif hasattr(wc_data, 'url'):
                # Already a WebContent object (shouldn't happen from JSON but be safe)
                conversation.web_cache[url] = wc_data
        conversation.system_prompt = data.get("system_prompt", "")
        conversation._structure_injected = False
        logger.info(f"Session restored: {name}")
        return True

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions sorted by date (newest first).

        Returns:
            List of session metadata dicts.
        """
        sessions = []
        for file_path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                sessions.append({
                    "name": data.get("name", file_path.stem),
                    "created_at": data.get("created_at", ""),
                    "model": data.get("model", "unknown"),
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue

        sessions.sort(key=lambda s: s["created_at"], reverse=True)
        return sessions

    def export_markdown(self, conversation: Any, name: Optional[str] = None) -> str:
        """Export conversation as Markdown file.

        Args:
            conversation: ConversationManager instance.
            name: Optional filename (without extension).

        Returns:
            Path to the exported file.
        """
        if not name:
            name = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        model = getattr(conversation.model_client, "model", "unknown")
        lines = [
            f"# Neow Session: {name}",
            f"",
            f"**Model:** {model}",
            f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"---",
            f"",
        ]

        for msg in conversation.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not content:
                continue
            if role == "user":
                lines.append(f"## User\n\n{content}\n")
            elif role == "assistant":
                lines.append(f"## Assistant\n\n{content}\n")

        md_content = "\n".join(lines)
        export_path = self.sessions_dir / f"{name}.md"
        export_path.write_text(md_content, encoding="utf-8")
        logger.info(f"Session exported: {export_path}")
        return str(export_path)

    def _find_session(self, name: str) -> Optional[Path]:
        """Find a session file by exact or fuzzy name match.

        Args:
            name: Session name to find.

        Returns:
            Path to session file, or None.
        """
        exact = self.sessions_dir / f"{name}.json"
        if exact.exists():
            return exact

        for file_path in self.sessions_dir.glob("*.json"):
            if name in file_path.stem:
                return file_path

        return None

    @property
    def session_tree(self):
        """Lazily initialized SessionTree instance."""
        if self._session_tree is None:
            from neow.core.session_tree import SessionTree
            self._session_tree = SessionTree(self.sessions_dir)
        return self._session_tree

    def load_tree(self, name: str):
        """Return SessionTree for a session, or None."""
        path = self.session_tree.find_session(name)
        if path:
            return self.session_tree
        return None