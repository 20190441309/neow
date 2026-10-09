"""Search tools for the agent: ``grep``, ``glob`` and ``list_dir``.

All three skip what git ignores: inside a repository the file list comes from
``git ls-files --cached --others --exclude-standard``; outside one, common
build and dependency directories (``SKIP_DIRS``) are skipped. ``grep`` uses
ripgrep when it is installed and falls back to Python otherwise.
"""

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from neow.utils.logger import logger

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".svn",
    ".hg",
    "venv",
    ".venv",
    "env",
    ".tox",
    "dist",
    "build",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
OUTPUT_MODES = ("files_with_matches", "content", "count")
GLOB_LIMIT = 200
LIST_DIR_LIMIT = 500
RG_TIMEOUT = 60
_BINARY_PROBE = 8192


class SearchToolError(Exception):
    """Invalid arguments or an unusable path."""


# ── file listing ─────────────────────────────────────────────────────────


def _git_files(root: Path) -> Optional[List[str]]:
    """Files under *root* (relative, ``/``-separated) that git does not ignore."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    names = proc.stdout.decode("utf-8", errors="replace").split("\0")
    # --cached still lists files deleted from the working tree.
    return sorted({n for n in names if n and (root / n).is_file()})


def _in_git(root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and proc.stdout.strip() == b"true"


def _walk_files(root: Path) -> List[str]:
    files = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_dir = Path(directory).relative_to(root)
        for name in sorted(names):
            files.append((rel_dir / name).as_posix())
    return files


def list_files(root: Path) -> List[str]:
    """Non-ignored files under *root*, relative to it."""
    files = _git_files(root)
    return files if files is not None else _walk_files(root)


def _resolve(path: str) -> Path:
    target = Path(path or ".").expanduser()
    if not target.exists():
        raise SearchToolError(f"Path not found: {path}")
    return target


def _display(path: Path) -> str:
    """*path* relative to the working directory when it is inside it."""
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix() or "."
    except ValueError:
        return str(path)


# ── glob patterns ────────────────────────────────────────────────────────


def _expand_braces(pattern: str) -> List[str]:
    match = re.search(r"\{([^{}]*)\}", pattern)
    if not match:
        return [pattern]
    head, tail = pattern[: match.start()], pattern[match.end():]
    expanded = []
    for option in match.group(1).split(","):
        expanded.extend(_expand_braces(head + option + tail))
    return expanded


def _glob_regex(pattern: str) -> str:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[":
            end = pattern.find("]", i + 1)
            if end == -1:
                out.append(re.escape("["))
                i += 1
            else:
                body = pattern[i + 1:end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return "".join(out)


@lru_cache(maxsize=64)
def _compile_glob(pattern: str) -> "re.Pattern[str]":
    options = [_glob_regex(p) for p in _expand_braces(pattern.lstrip("/"))]
    return re.compile("^(?:" + "|".join(options) + ")$")


def glob_match(rel_path: str, pattern: str) -> bool:
    """Shell-style match of a ``/``-separated relative path.

    ``*`` stays within one directory, ``**`` crosses directories and
    ``{a,b}`` lists alternatives. A pattern without ``/`` (``*.py``) only
    matches files directly in the searched directory.
    """
    return bool(_compile_glob(pattern).match(rel_path))


def _filter_match(rel_path: str, pattern: str) -> bool:
    """``grep`` filter: like ripgrep, a pattern without ``/`` tests the name."""
    if "/" not in pattern:
        return glob_match(rel_path.rsplit("/", 1)[-1], pattern)
    return glob_match(rel_path, pattern)


# ── grep ─────────────────────────────────────────────────────────────────

# One shown line: (line number, text, is_match); context lines are not matches.
Hit = Tuple[int, str, bool]


def _targets(target: Path, glob: Optional[str]) -> Tuple[Path, List[str]]:
    if target.is_file():
        return target.parent, [target.name]
    files = list_files(target)
    if glob:
        files = [f for f in files if _filter_match(f, glob)]
    return target, files


def _read_text(path: Path) -> Optional[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:_BINARY_PROBE]:
        return None
    return data.decode("utf-8", errors="replace")


def _python_grep(
    target: Path, regex: "re.Pattern[str]", glob: Optional[str], context: int
) -> Dict[str, List[Hit]]:
    base, files = _targets(target, glob)
    results: Dict[str, List[Hit]] = {}
    for rel in files:
        text = _read_text(base / rel)
        if text is None:
            continue
        lines = text.splitlines()
        matched = [i for i, line in enumerate(lines) if regex.search(line)]
        if not matched:
            continue
        shown = set()
        for i in matched:
            shown.update(range(max(0, i - context), min(len(lines), i + context + 1)))
        hits = set(matched)
        results[_display(base / rel)] = [
            (i + 1, lines[i], i in hits) for i in sorted(shown)
        ]
    return results


def _rg_grep(
    rg: str,
    target: Path,
    pattern: str,
    glob: Optional[str],
    context: int,
    case_insensitive: bool,
) -> Optional[Dict[str, List[Hit]]]:
    """Run ripgrep; ``None`` when it fails (the caller falls back to Python)."""
    cmd = [rg, "--json", "--hidden", "--glob", "!.git"]
    if not _in_git(target if target.is_dir() else target.parent):
        # Outside a repository the Python search skips SKIP_DIRS; match it.
        for name in sorted(SKIP_DIRS):
            cmd += ["--glob", f"!{name}"]
    if case_insensitive:
        cmd.append("--ignore-case")
    if context:
        cmd += ["--context", str(context)]
    if glob:
        cmd += ["--glob", glob]
    cmd += ["--regexp", pattern, "--", str(target)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=RG_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug(f"ripgrep failed, using Python search: {exc}")
        return None
    if proc.returncode not in (0, 1):  # 1 = no matches
        logger.debug(f"ripgrep exit {proc.returncode}: {proc.stderr[:200]!r}")
        return None
    results: Dict[str, List[Hit]] = {}
    for raw in proc.stdout.splitlines():
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("type") not in ("match", "context"):
            continue
        data = event["data"]
        path = data["path"].get("text")
        text = data["lines"].get("text")
        if path is None or text is None:  # non-UTF-8 bytes
            continue
        name = _display(Path(path))
        results.setdefault(name, []).append(
            (data["line_number"], text.rstrip("\r\n"), event["type"] == "match")
        )
    return results


def _limit(entries: List[str], head_limit: int, what: str) -> str:
    if len(entries) <= head_limit:
        return "\n".join(entries)
    return "\n".join(entries[:head_limit]) + (
        f"\n… showing {head_limit} of {len(entries)} {what}; narrow the search "
        "or raise head_limit"
    )


def grep(
    pattern: str,
    path: str = ".",
    glob: Optional[str] = None,
    output_mode: str = "files_with_matches",
    context: int = 0,
    case_insensitive: bool = False,
    head_limit: int = 100,
) -> str:
    """Search file contents for a regular expression."""
    if output_mode not in OUTPUT_MODES:
        raise SearchToolError(
            f"output_mode must be one of {', '.join(OUTPUT_MODES)}"
        )
    try:
        regex = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
    except re.error as exc:
        raise SearchToolError(f"Invalid regex {pattern!r}: {exc}") from exc
    target = _resolve(path)
    context = max(0, int(context or 0)) if output_mode == "content" else 0
    head_limit = max(1, int(head_limit or 100))

    results = None
    rg = shutil.which("rg")
    if rg:
        results = _rg_grep(rg, target, pattern, glob, context, case_insensitive)
    if results is None:
        results = _python_grep(target, regex, glob, context)
    if not results:
        return "No matches found"

    files = sorted(results)
    if output_mode == "files_with_matches":
        return _limit(files, head_limit, "files")
    if output_mode == "count":
        counts = [f"{f}:{sum(1 for h in results[f] if h[2])}" for f in files]
        return _limit(counts, head_limit, "files")
    lines: List[str] = []
    for name in files:
        previous = None
        for number, text, is_match in sorted(results[name]):
            if previous is not None and number > previous + 1:
                lines.append("--")
            sep = ":" if is_match else "-"
            lines.append(f"{name}{sep}{number}{sep}{text}")
            previous = number
    return _limit(lines, head_limit, "lines")


# ── glob / list_dir ──────────────────────────────────────────────────────


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def glob(pattern: str, path: str = ".") -> str:
    """Files matching *pattern*, most recently modified first."""
    root = _resolve(path)
    if not root.is_dir():
        raise SearchToolError(f"Not a directory: {path}")
    matches = [root / f for f in list_files(root) if glob_match(f, pattern)]
    if not matches:
        return "No files found"
    matches.sort(key=_mtime, reverse=True)
    return _limit([_display(m) for m in matches], GLOB_LIMIT, "files")


def _tree(paths: Iterable[str], depth: int) -> Dict:
    tree: Dict = {}
    for rel in paths:
        parts = rel.split("/")
        if len(parts) > depth:
            parts = parts[:depth]
            parts[-1] += "/"
        node = tree
        for i, part in enumerate(parts):
            if i < len(parts) - 1:
                node = node.setdefault(part + "/", {})
            else:
                node.setdefault(part, {})
    return tree


def _render(tree: Dict, prefix: str, out: List[str]) -> None:
    entries = sorted(tree, key=lambda n: (not n.endswith("/"), n.lower()))
    for name in entries:
        out.append(f"{prefix}{name}")
        _render(tree[name], prefix + "  ", out)


def list_dir(path: str = ".", depth: int = 1) -> str:
    """Directory tree (directories end with ``/``), ignoring what git ignores."""
    root = _resolve(path)
    if not root.is_dir():
        raise SearchToolError(f"Not a directory: {path}")
    depth = max(1, int(depth or 1))
    tree = _tree(list_files(root), depth)
    out: List[str] = [f"{_display(root)}/"]
    _render(tree, "  ", out)
    if len(out) == 1:
        return f"{_display(root)}/ (empty)"
    if len(out) > LIST_DIR_LIMIT + 1:
        out = out[: LIST_DIR_LIMIT + 1] + [
            f"… {len(out) - LIST_DIR_LIMIT - 1} more entries; list a subdirectory "
            "or lower depth"
        ]
    return "\n".join(out)


__all__ = [
    "SearchToolError",
    "glob",
    "glob_match",
    "grep",
    "list_dir",
    "list_files",
]
