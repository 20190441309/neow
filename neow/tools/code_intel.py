"""AST symbol outline and repository map (Repo Map) tools."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import List, Optional

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".tox",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".eggs",
}

CODE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
}

_GENERIC_SYMBOL_PATTERNS = [
    re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(?:function|class|interface|type|enum|struct|trait|impl|fn|func|def)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)"
    ),
    re.compile(
        r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait|mod)\s+"
        r"([A-Za-z_][A-Za-z0-9_]*)"
    ),
]


def _format_py_args(args: ast.arguments) -> str:
    names = [a.arg for a in args.posonlyargs + args.args]
    if args.vararg:
        names.append(f"*{args.vararg.arg}")
    names.extend(f"{a.arg}=*" for a in args.kwonlyargs)
    if args.kwarg:
        names.append(f"**{args.kwarg.arg}")
    if len(names) > 6:
        names = names[:6] + ["…"]
    return ", ".join(names)


def _python_outline(content: str) -> List[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError as err:
        return [f"⚠ SyntaxError at line {err.lineno}: {err.msg}"]

    lines: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            bases = [
                ast.unparse(b) if hasattr(ast, "unparse") else "" for b in node.bases
            ]
            base_str = f"({', '.join(b for b in bases if b)})" if bases else ""
            lines.append(f"class {node.name}{base_str}  [L{node.lineno}-L{end}]")
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = (
                        "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                    )
                    sig = _format_py_args(item.args)
                    lines.append(f"  {prefix} {item.name}({sig})  [L{item.lineno}]")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
            sig = _format_py_args(node.args)
            lines.append(f"{prefix} {node.name}({sig})  [L{node.lineno}-L{end}]")
    return lines


def _generic_outline(content: str) -> List[str]:
    lines: List[str] = []
    for idx, raw_line in enumerate(content.splitlines(), 1):
        for pattern in _GENERIC_SYMBOL_PATTERNS:
            match = pattern.match(raw_line)
            if match:
                cleaned = raw_line.strip().rstrip("{:").strip()
                if len(cleaned) > 90:
                    cleaned = cleaned[:90] + "…"
                lines.append(f"{cleaned}  [L{idx}]")
                break
    return lines


def extract_symbols(file_path: Path) -> List[str]:
    """Return a list of symbol signature lines for *file_path*."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    if file_path.suffix.lower() == ".py":
        return _python_outline(content)
    return _generic_outline(content)


def file_outline(file_path: str) -> str:
    """Return the AST/symbol outline (classes, functions, line numbers) of a file."""
    path = Path(file_path)
    if not path.exists():
        return f"Error: File not found: {file_path}"
    if not path.is_file():
        return f"Error: Not a file: {file_path}"
    symbols = extract_symbols(path)
    if not symbols:
        return f"{file_path}: (no top-level classes or functions detected)"
    return f"# Outline: {file_path}\n" + "\n".join(f"  {s}" for s in symbols)


def repo_map(
    directory: str = ".",
    query: Optional[str] = None,
    max_files: int = 25,
) -> str:
    """Build a structural repository map of files and their symbol outlines."""
    root = Path(directory)
    if not root.exists():
        return f"Error: Directory not found: {directory}"

    candidates: List[Path] = []
    q_words = [w.lower() for w in (query or "").split() if w.strip()]

    for cur, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")
        )
        for fname in sorted(files):
            if fname.startswith("."):
                continue
            fpath = Path(cur) / fname
            if fpath.suffix.lower() not in CODE_EXTENSIONS:
                continue
            candidates.append(fpath)

    def _score(p: Path) -> tuple:
        rel = str(p.relative_to(root)).replace("\\", "/").lower()
        is_test = "test" in rel
        q_hits = sum(1 for w in q_words if w in rel) if q_words else 0
        depth = rel.count("/")
        return (-q_hits, is_test, depth, rel)

    candidates.sort(key=_score)
    selected = candidates[: max(1, min(int(max_files or 25), 60))]
    if not selected:
        return f"No source code files found in {directory}"

    sections: List[str] = [
        f"# Repository Map ({len(selected)}/{len(candidates)} source files shown)"
    ]
    for fpath in selected:
        rel = str(fpath.relative_to(root)).replace("\\", "/")
        symbols = extract_symbols(fpath)
        if symbols:
            shown = symbols[:25]
            more = (
                [f"  … (+{len(symbols) - 25} more symbols)"]
                if len(symbols) > 25
                else []
            )
            sections.append(f"\n{rel}:\n" + "\n".join(f"  {s}" for s in shown + more))
        else:
            sections.append(f"\n{rel}: (module)")
    return "\n".join(sections)


__all__ = ["extract_symbols", "file_outline", "repo_map"]
