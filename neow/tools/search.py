"""Code search tools for Neow CLI."""

import re
from pathlib import Path
from typing import Dict, List

from neow.utils.logger import logger


class SearchError(Exception):
    """Code search error."""

    pass


def search_code(
    query: str, directory: str, file_pattern: str = "*", max_results: int = 50
) -> List[Dict[str, str]]:
    """Search for code patterns in files.

    Args:
        query: Search query (supports regex).
        directory: Directory to search in.
        file_pattern: File pattern to match (e.g., "*.py").
        max_results: Maximum number of results.

    Returns:
        List of dictionaries with 'file', 'line', 'content' keys.

    Raises:
        SearchError: If search fails.
    """
    try:
        search_dir = Path(directory)
        if not search_dir.exists():
            raise SearchError(f"Directory not found: {directory}")

        results = []
        pattern = re.compile(query, re.IGNORECASE)
        SKIP_DIRS = {'.git', '__pycache__', 'node_modules', '.svn', '.hg', 'venv', '.venv', 'env', '.tox', 'dist', 'build', '.eggs', '.mypy_cache'}

        for file_path in search_dir.rglob(file_pattern):
            if not file_path.is_file():
                continue
            # Skip unwanted directories
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        results.append(
                            {
                                "file": str(file_path),
                                "line": str(line_num),
                                "content": line.strip(),
                            }
                        )

                        if len(results) >= max_results:
                            logger.debug(f"Reached max results ({max_results})")
                            return results
            except (UnicodeDecodeError, PermissionError):
                # Skip binary files or files without read permission
                continue

        logger.debug(f"Found {len(results)} results for query: {query}")
        return results

    except SearchError:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise SearchError(f"Search failed: {e}")
