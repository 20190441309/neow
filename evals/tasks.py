"""Fixed eval task set: one scripted model run each, scored against the
real filesystem + a subprocess sanity check (not just string matching).

Add a task by appending to TASKS. ``replies`` is consumed one entry per
model request (see ScriptedClient) — a tool-calling round and the final
text-only round each need their own entry. edit_file/write_file require a
prior read_file of the same path in the same run (read-before-edit guard).
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from tests.test_agent_loop import _call


@dataclass
class EvalTask:
    id: str
    description: str
    prompt: str
    replies: List[Dict[str, Any]]
    check: Callable[[Path], Tuple[bool, str]]
    setup: Dict[str, str] = field(default_factory=dict)
    # "smoke": generic coverage. "regression": reproduces a specific failure
    # logged under evals/failures/ — see evals/failures/README.md.
    category: str = "smoke"


def _run_py(work_dir: Path, code: str) -> Tuple[bool, str]:
    """Run *code* with ``work_dir`` on sys.path; (ok, stdout/stderr tail)."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return False, (result.stdout + result.stderr)[-500:]
    return True, result.stdout.strip()


def _check_create_file_basic(work_dir: Path) -> Tuple[bool, str]:
    path = work_dir / "math_utils.py"
    if not path.exists():
        return False, "math_utils.py was not created"
    return _run_py(work_dir, "import math_utils; assert math_utils.add(2, 3) == 5")


def _check_fix_bug_edit(work_dir: Path) -> Tuple[bool, str]:
    content = (work_dir / "calc.py").read_text()
    if "a * b" not in content:
        return False, f"calc.py was not fixed:\n{content}"
    return _run_py(work_dir, "import calc; assert calc.multiply(3, 4) == 12")


def _check_multi_file_refactor(work_dir: Path) -> Tuple[bool, str]:
    a = (work_dir / "a.py").read_text()
    b = (work_dir / "b.py").read_text()
    if "def say_hello" not in a:
        return False, f"a.py still missing say_hello:\n{a}"
    if "greet" in b or "say_hello" not in b:
        return False, f"b.py was not updated:\n{b}"
    return _run_py(
        work_dir, "from a import say_hello; assert say_hello('x') == 'Hello, x'"
    )


TASKS: List[EvalTask] = [
    EvalTask(
        id="create_file_basic",
        description="Create a new file with a working function from scratch.",
        prompt="Create math_utils.py with an add(a, b) function that returns their sum.",
        replies=[
            {
                "content": "I'll create the file.",
                "tool_calls": [
                    _call(
                        "c1",
                        "create_file",
                        file_path="math_utils.py",
                        content="def add(a, b):\n    return a + b\n",
                    )
                ],
            },
            {"content": "Done."},
        ],
        check=_check_create_file_basic,
    ),
    EvalTask(
        id="fix_bug_edit",
        description="Read a buggy file, then fix it with edit_file (read-before-edit path).",
        setup={"calc.py": "def multiply(a, b):\n    return a + b\n"},
        prompt=(
            "There's a bug in calc.py's multiply function: it adds instead of "
            "multiplying. Fix it."
        ),
        replies=[
            {
                "content": "Let me look.",
                "tool_calls": [_call("c1", "read_file", file_path="calc.py")],
            },
            {
                "content": "Found it.",
                "tool_calls": [
                    _call(
                        "c2",
                        "edit_file",
                        file_path="calc.py",
                        old_text="return a + b",
                        new_text="return a * b",
                        first_only=True,
                    )
                ],
            },
            {"content": "Fixed."},
        ],
        check=_check_fix_bug_edit,
    ),
    EvalTask(
        id="multi_file_refactor",
        description="Rename a function across its definition and a usage site in another file.",
        setup={
            "a.py": "def greet(name):\n    return f'Hello, {name}'\n",
            "b.py": "from a import greet\n\nprint(greet('world'))\n",
        },
        prompt="Rename the function `greet` to `say_hello` everywhere: its definition in a.py and the usage in b.py.",
        replies=[
            {
                "content": "Reading both files.",
                "tool_calls": [
                    _call("c1", "read_file", file_path="a.py"),
                    _call("c2", "read_file", file_path="b.py"),
                ],
            },
            {
                "content": "Renaming.",
                "tool_calls": [
                    _call(
                        "c3",
                        "edit_file",
                        file_path="a.py",
                        old_text="def greet(name):",
                        new_text="def say_hello(name):",
                    ),
                    _call(
                        "c4",
                        "edit_file",
                        file_path="b.py",
                        old_text="from a import greet",
                        new_text="from a import say_hello",
                    ),
                    _call(
                        "c5",
                        "edit_file",
                        file_path="b.py",
                        old_text="print(greet('world'))",
                        new_text="print(say_hello('world'))",
                    ),
                ],
            },
            {"content": "Renamed."},
        ],
        check=_check_multi_file_refactor,
    ),
]
