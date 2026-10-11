"""Run the eval suite (see evals/tasks.py) and report pass/fail + timing.

    python -m evals.runner            # human-readable table, exit 1 on any failure
    python -m evals.runner --json     # machine-readable report on stdout

Each task drives the real CLI (click's CliRunner) through the full headless
agent loop and real tool executor, with a ScriptedClient standing in for the
model. That protects the tool-execution path (file I/O, read-before-edit
guard, approval, checkpoints) with zero cost and no flakiness. It does not
judge model reasoning quality — see evals/README.md for the live-model mode.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, List
from unittest import mock

from click.testing import CliRunner

from evals.tasks import TASKS, EvalTask
from neow.cli import main as cli
from tests.test_agent_loop import ScriptedClient


@dataclass
class EvalResult:
    id: str
    category: str
    passed: bool
    message: str
    duration_ms: int


class _FakeClient(ScriptedClient):
    """A ScriptedClient that also satisfies the real client interface."""

    model = "eval-scripted"

    def validate_connection(self) -> bool:
        return True


@contextmanager
def _sandbox(home: Path, work: Path, client: _FakeClient) -> Iterator[None]:
    """Isolate one run: scratch HOME/cwd, a scripted model, no real network."""
    from neow.core import checkpoints

    cwd = os.getcwd()
    with (
        mock.patch.dict(os.environ, {"HOME": str(home)}),
        mock.patch.object(checkpoints, "ROOT", home / "checkpoints"),
        mock.patch.object(cli, "create_model_client", lambda cfg, name: client),
    ):
        try:
            os.chdir(work)
            yield
        finally:
            os.chdir(cwd)


def run_task(task: EvalTask, base_dir: Path) -> EvalResult:
    home, work = base_dir / "home", base_dir / "work"
    home.mkdir(parents=True)
    work.mkdir(parents=True)
    for rel, content in task.setup.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    # A real repo so the git auto-commit path runs (not a warning-and-skip).
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(
        ["git", "config", "user.email", "eval@neow.local"], cwd=work, check=True
    )
    subprocess.run(["git", "config", "user.name", "neow-eval"], cwd=work, check=True)
    if task.setup:
        subprocess.run(["git", "add", "-A"], cwd=work, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "setup"], cwd=work, check=True)

    client = _FakeClient(list(task.replies))
    started = time.monotonic()
    with _sandbox(home, work, client):
        result = CliRunner().invoke(
            cli.main,
            ["-p", task.prompt, "--output-format", "json", "--approval", "yolo"],
            catch_exceptions=False,
        )
    duration_ms = int((time.monotonic() - started) * 1000)

    if result.exit_code != 0:
        tail = (result.output or "")[-500:]
        return EvalResult(
            task.id,
            task.category,
            False,
            f"CLI exited {result.exit_code}: {tail}",
            duration_ms,
        )
    try:
        ok, message = task.check(work)
    except (
        Exception
    ) as exc:  # noqa: BLE001 - a broken check is still a failure to report
        return EvalResult(
            task.id, task.category, False, f"check raised: {exc}", duration_ms
        )
    return EvalResult(task.id, task.category, ok, message, duration_ms)


def run_all(tasks: List[EvalTask] = TASKS) -> List[EvalResult]:
    results = []
    for task in tasks:
        with tempfile.TemporaryDirectory(prefix="neow-eval-") as tmp:
            results.append(run_task(task, Path(tmp)))
    return results


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="print a JSON report instead of a table"
    )
    args = parser.parse_args(argv)

    results = run_all()

    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        width = max(len(r.id) for r in results)
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            print(
                f"[{mark}] {r.id.ljust(width)}  ({r.category})  {r.duration_ms:>5}ms  {r.message}"
            )
        passed = sum(r.passed for r in results)
        print(f"\n{passed}/{len(results)} passed")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
