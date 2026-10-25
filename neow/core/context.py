"""Context manager for Neow CLI."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from neow.tools.code_intel import extract_symbols


class ContextManager:
    """Manages project context for AI model."""

    def __init__(self, project_root: str):
        """Initialize context manager.

        Args:
            project_root: Root directory of the project.
        """
        self.project_root = Path(project_root)
        self.file_cache: Dict[str, str] = {}

    def get_project_structure(self, max_depth: int = 3) -> Dict[str, Any]:
        """Get project directory structure.

        Args:
            max_depth: Maximum depth to traverse.

        Returns:
            Dictionary representing project structure.
        """
        structure: Dict[str, Any] = {}
        self._build_structure(self.project_root, structure, max_depth, 0)
        return structure

    def _build_structure(
        self, path: Path, structure: Dict, max_depth: int, current_depth: int
    ) -> None:
        """Recursively build directory structure."""
        if current_depth >= max_depth:
            return

        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith(".") or item.name in (
                    "__pycache__",
                    "node_modules",
                    ".git",
                    "venv",
                    ".venv",
                ):
                    continue

                if item.is_dir():
                    structure[item.name] = {}
                    self._build_structure(
                        item, structure[item.name], max_depth, current_depth + 1
                    )
                else:
                    structure[item.name] = None
        except PermissionError:
            pass

    def get_relevant_files(
        self, query: str, max_files: int = 10
    ) -> List[Dict[str, str]]:
        """Get files relevant to a query, enriched with AST/symbol outlines.

        Args:
            query: Search query.
            max_files: Maximum number of files to return.

        Returns:
            List of dictionaries with 'path', 'content', and optional 'symbols' keys.
        """
        relevant_files = []
        query_lower = query.lower()

        query_words = [w for w in query_lower.split() if len(w) >= 2]
        if not query_words and query_lower:
            query_words = [query_lower]

        scored_candidates = []

        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file():
                continue

            if file_path.name.startswith(".") or any(
                part.startswith(".")
                or part in ("__pycache__", "node_modules", ".venv", "venv")
                for part in file_path.parts
            ):
                continue

            name_lower = file_path.name.lower()
            score = sum(3 for word in query_words if word in name_lower)

            symbols = extract_symbols(file_path)
            symbol_names = " ".join(s.lower() for s in symbols)
            score += sum(2 for word in query_words if word in symbol_names)

            if score > 0:
                scored_candidates.append((score, file_path, symbols))

        scored_candidates.sort(key=lambda item: (-item[0], str(item[1])))

        for _score, file_path, symbols in scored_candidates[:max_files]:
            content = self._read_file(file_path)
            if content:
                rel_path = str(file_path.relative_to(self.project_root))
                symbol_outline = "\n".join(symbols[:25])
                relevant_files.append(
                    {
                        "path": rel_path,
                        "content": content[:1000],
                        "symbols": symbol_outline,
                    }
                )

        return relevant_files

    def _read_file(self, file_path: Path) -> Optional[str]:
        """Read file content with caching."""
        cache_key = str(file_path)
        if cache_key in self.file_cache:
            return self.file_cache[cache_key]

        try:
            content = file_path.read_text(encoding="utf-8")
            self.file_cache[cache_key] = content
            return content
        except (UnicodeDecodeError, PermissionError):
            return None

    def build_context(self, user_input: str) -> str:
        """Build context string for AI model."""
        context_parts = []

        structure = self.get_project_structure(max_depth=2)
        context_parts.append("Project structure:")
        context_parts.append(self._format_structure(structure, indent=2))

        relevant_files = self.get_relevant_files(user_input)
        if relevant_files:
            context_parts.append("\nRelevant files:")
            for file_info in relevant_files:
                context_parts.append(f"\n{file_info['path']}:")
                if file_info.get("symbols"):
                    context_parts.append("Symbols:")
                    context_parts.append(file_info["symbols"])
                context_parts.append(file_info["content"])

        return "\n".join(context_parts)

    def _format_structure(self, structure: Dict, indent: int = 0) -> str:
        """Format structure dictionary as string."""
        lines = []
        prefix = " " * indent

        for key, value in structure.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}/")
                if value:
                    lines.append(self._format_structure(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}")

        return "\n".join(lines)
