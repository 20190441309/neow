"""Project memory: instructions from AGENTS.md / NEOW.md files.

Files are loaded from the most general to the most specific, so later ones
take precedence when they disagree:

1. ``~/.neow/NEOW.md`` (user-wide preferences)
2. every directory from the git root down to the working directory:
   ``AGENTS.md`` then ``NEOW.md``

A line holding only ``@relative/path.md`` imports that file in place.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

MEMORY_FILENAMES = ("AGENTS.md", "NEOW.md")
MAX_IMPORT_DEPTH = 5
DEFAULT_LIMIT = 40_000
_IMPORT = re.compile(r"^@(\S+\.md)\s*$")

INIT_PROMPT = """\
Create an AGENTS.md file at the repository root for coding agents working on \
this project.

First explore the repository: README, package/build files (pyproject.toml, \
package.json, Makefile, ...), test and lint configuration, CI workflows and \
the directory layout. Then write a concise AGENTS.md (well under 200 lines) \
covering:
- what the project is and how the code is organised
- how to install dependencies, build, run the tests and the linters (exact \
commands)
- code style and conventions that are not obvious from the code
- anything an agent must not do (generated files, protected directories, ...)

Only state what you verified in the repository. If AGENTS.md already exists, \
read it and improve it instead of starting over. Use create_file for a new \
file or write_file to replace an existing one, so the user can review it."""


@dataclass
class MemoryFile:
    path: Path
    chars: int


@dataclass
class Memory:
    files: List[MemoryFile] = field(default_factory=list)
    text: str = ""
    warnings: List[str] = field(default_factory=list)


def find_git_root(start: Path) -> Optional[Path]:
    for directory in [start, *start.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def project_root(cwd: Path) -> Path:
    """Git root of *cwd*, or *cwd* itself outside a repository."""
    cwd = Path(cwd).resolve()
    return find_git_root(cwd) or cwd


def discover_memory_files(cwd: Path, home: Optional[Path] = None) -> List[Path]:
    """Memory files in load order (most general first)."""
    cwd = Path(cwd).resolve()
    home = Path(home) if home is not None else Path.home()
    found: List[Path] = []
    user_file = home / ".neow" / "NEOW.md"
    if user_file.is_file():
        found.append(user_file)
    root = project_root(cwd)
    directories = [root]
    if cwd != root:
        relative = cwd.relative_to(root)
        current = root
        for part in relative.parts:
            current = current / part
            directories.append(current)
    for directory in directories:
        for name in MEMORY_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                found.append(candidate)
    return found


def _expand(
    path: Path, depth: int, seen: Set[Path], warnings: List[str]
) -> str:
    """File text with ``@imports`` inlined (bounded depth, no cycles)."""
    resolved = path.resolve()
    if resolved in seen:
        return ""
    seen.add(resolved)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        warnings.append(f"cannot read {path}: {exc}")
        return ""
    lines = []
    for line in text.splitlines():
        match = _IMPORT.match(line.strip())
        if not match:
            lines.append(line)
            continue
        target = (path.parent / match.group(1)).expanduser()
        if depth >= MAX_IMPORT_DEPTH:
            warnings.append(
                f"{path}: import of {match.group(1)} skipped (max depth "
                f"{MAX_IMPORT_DEPTH})"
            )
            continue
        if not target.is_file():
            warnings.append(f"{path}: imported file not found: {match.group(1)}")
            continue
        lines.append(_expand(target, depth + 1, seen, warnings).rstrip("\n"))
    return "\n".join(lines).strip() + "\n"


def load_memory(
    cwd: Path, home: Optional[Path] = None, limit: int = DEFAULT_LIMIT
) -> Memory:
    """Load and combine memory files for *cwd*.

    Beyond *limit* characters the most general content is dropped first,
    since more specific files are the ones that should win.
    """
    memory = Memory()
    sections = []
    seen: Set[Path] = set()
    for path in discover_memory_files(cwd, home=home):
        body = _expand(path, 0, seen, memory.warnings)
        if not body.strip():
            continue
        memory.files.append(MemoryFile(path=path, chars=len(body)))
        sections.append(f"### {_display(path, home)}\n{body}")

    kept: List[str] = []
    budget = limit
    for section in reversed(sections):
        if len(section) <= budget:
            kept.insert(0, section)
            budget -= len(section)
            continue
        if budget > 200:
            kept.insert(0, "… (truncated)\n" + section[-budget:])
        memory.warnings.append(
            f"memory files exceed {limit} characters; the most general "
            "content was dropped"
        )
        break
    if kept:
        memory.text = (
            "\n## Project Memory\n"
            "Instructions from the user's memory files. Follow them; later "
            "(more specific) files take precedence.\n\n" + "\n".join(kept)
        )
    return memory


def add_memory_note(cwd: Path, note: str) -> Path:
    """Append ``- note`` to the project's NEOW.md (created if missing)."""
    path = project_root(cwd) / "NEOW.md"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    path.write_text(f"{existing}- {note.strip()}\n", encoding="utf-8")
    return path


def _display(path: Path, home: Optional[Path]) -> str:
    home = Path(home) if home is not None else Path.home()
    try:
        return "~/" + str(path.relative_to(home))
    except ValueError:
        return str(path)


__all__ = [
    "INIT_PROMPT",
    "Memory",
    "MemoryFile",
    "add_memory_note",
    "discover_memory_files",
    "load_memory",
    "project_root",
]
