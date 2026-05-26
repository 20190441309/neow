"""Context manager for Neow CLI."""

from pathlib import Path
from typing import Any, Dict, List, Optional


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
                # Skip hidden files and common non-essential directories
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
        """Get files relevant to a query.

        Args:
            query: Search query.
            max_files: Maximum number of files to return.

        Returns:
            List of dictionaries with 'path' and 'content' keys.
        """
        relevant_files = []
        query_lower = query.lower()

        # Split query into words for matching
        query_words = query_lower.split()

        # Search for files that might be relevant
        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip hidden files and non-text files
            if file_path.name.startswith("."):
                continue

            # Check if file name matches any query word
            name_lower = file_path.name.lower()
            if any(word in name_lower for word in query_words):
                content = self._read_file(file_path)
                if content:
                    relevant_files.append(
                        {
                            "path": str(file_path.relative_to(self.project_root)),
                            "content": content[:1000],  # Limit content size
                        }
                    )

            if len(relevant_files) >= max_files:
                break

        return relevant_files

    def _read_file(self, file_path: Path) -> Optional[str]:
        """Read file content with caching.

        Args:
            file_path: Path to file.

        Returns:
            File content or None if cannot read.
        """
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
        """Build context string for AI model.

        Args:
            user_input: User input to analyze.

        Returns:
            Context string.
        """
        context_parts = []

        # Add project structure
        structure = self.get_project_structure(max_depth=2)
        context_parts.append("Project structure:")
        context_parts.append(self._format_structure(structure, indent=2))

        # Add relevant files
        relevant_files = self.get_relevant_files(user_input)
        if relevant_files:
            context_parts.append("\nRelevant files:")
            for file_info in relevant_files:
                context_parts.append(f"\n{file_info['path']}:")
                context_parts.append(file_info["content"])

        return "\n".join(context_parts)

    def _format_structure(self, structure: Dict, indent: int = 0) -> str:
        """Format structure dictionary as string.

        Args:
            structure: Structure dictionary.
            indent: Indentation level.

        Returns:
            Formatted string.
        """
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
