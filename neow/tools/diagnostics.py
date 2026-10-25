"""Post-edit static & syntax diagnostics for modified files."""

from __future__ import annotations

import ast
import json
from pathlib import Path


def check_file_diagnostics(file_path: str) -> str:
    """Run fast syntax/structural checks on *file_path*.

    Returns an empty string if the file has no syntax errors or is an
    unsupported format, or a ``[Diagnostics] ⚠ ...`` notice if errors exist.
    """
    try:
        path = Path(file_path)
        if not path.is_file():
            return ""
        suffix = path.suffix.lower()
        if suffix not in (".py", ".json", ".toml", ".yaml", ".yml"):
            return ""
        content = path.read_text(encoding="utf-8")
    except Exception:
        return ""

    if suffix == ".py":
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError as err:
            loc = f"line {err.lineno}"
            if err.offset:
                loc += f", col {err.offset}"
            snippet = f"\n  > {err.text.strip()}" if err.text else ""
            return (
                f"\n[Diagnostics] ⚠ Python SyntaxError in {file_path} ({loc}): "
                f"{err.msg}{snippet}"
            )
        return ""

    if suffix == ".json":
        if not content.strip():
            return f"\n[Diagnostics] ⚠ JSON file {file_path} is empty."
        try:
            json.loads(content)
        except json.JSONDecodeError as err:
            return (
                f"\n[Diagnostics] ⚠ JSONDecodeError in {file_path} "
                f"(line {err.lineno}, col {err.colno}): {err.msg}"
            )
        return ""

    if suffix == ".toml":
        try:
            import tomllib

            tomllib.loads(content)
        except ImportError:
            return ""
        except Exception as err:
            return f"\n[Diagnostics] ⚠ TOMLDecodeError in {file_path}: {err}"
        return ""

    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]

            yaml.safe_load(content)
        except ImportError:
            return ""
        except Exception as err:
            return f"\n[Diagnostics] ⚠ YAMLError in {file_path}: {err}"
        return ""

    return ""


def append_diagnostics(file_path: str, message: str) -> str:
    """Append any syntax diagnostic warning to a file tool's result message."""
    diag = check_file_diagnostics(file_path)
    return f"{message}{diag}" if diag else message


__all__ = ["append_diagnostics", "check_file_diagnostics"]
