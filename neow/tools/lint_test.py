"""Lint and test detection and execution for Neow CLI."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from neow.utils.logger import logger


@dataclass
class LintResult:
    """Result of a lint run."""

    success: bool
    output: str
    command: str


@dataclass
class TestResult:
    """Result of a test run."""

    success: bool
    output: str
    command: str


def detect_lint_command(project_root: Path) -> Optional[str]:
    """Auto-detect lint command based on project configuration.

    Priority:
    1. pyproject.toml [tool.ruff] -> "ruff check ."
    2. pyproject.toml [tool.flake8] -> "flake8 ."
    3. .eslintrc* -> "npx eslint ."
    4. package.json scripts.lint -> "npm run lint"
    5. Makefile lint target -> "make lint"
    """
    project_root = Path(project_root)

    # 1. Check pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        if "[tool.ruff]" in content:
            return "ruff check ."
        if "[tool.flake8]" in content:
            return "flake8 ."

    # 2. Check .eslintrc files
    eslint_configs = [
        ".eslintrc",
        ".eslintrc.json",
        ".eslintrc.js",
        ".eslintrc.yml",
    ]
    for name in eslint_configs:
        if (project_root / name).exists():
            return "npx eslint ."

    # 3. Check package.json scripts.lint
    package_json = project_root / "package.json"
    if package_json.exists():
        import json

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "lint" in scripts:
                return "npm run lint"
        except (json.JSONDecodeError, KeyError):
            pass

    # 4. Check Makefile for lint target
    makefile = project_root / "Makefile"
    if makefile.exists():
        content = makefile.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("lint:") or stripped == "lint:":
                return "make lint"

    return None


def detect_test_command(project_root: Path) -> Optional[str]:
    """Auto-detect test command based on project configuration.

    Priority:
    1. pyproject.toml pytest config -> "pytest"
    2. package.json scripts.test -> "npm test"
    3. Makefile test target -> "make test"
    """
    project_root = Path(project_root)

    # 1. Check pyproject.toml for pytest config
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        if "[tool.pytest" in content:
            return "pytest"

    # 2. Check package.json scripts.test
    package_json = project_root / "package.json"
    if package_json.exists():
        import json

        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            if "test" in scripts:
                return "npm test"
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Check Makefile for test target
    makefile = project_root / "Makefile"
    if makefile.exists():
        content = makefile.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("test:") or stripped == "test:":
                return "make test"

    return None


def run_lint(
    project_root: Path, lint_command: Optional[str] = None
) -> LintResult:
    """Run linter on the project.

    Args:
        project_root: Root directory of the project.
        lint_command: Specific lint command to run. Auto-detected if None.

    Returns:
        LintResult with success status, output, and command used.
    """
    if lint_command is None:
        lint_command = detect_lint_command(project_root)
        if lint_command is None:
            return LintResult(
                success=False,
                output="No lint command detected for this project.",
                command="",
            )

    logger.info("Running lint: %s", lint_command)
    try:
        result = subprocess.run(
            lint_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(project_root),
        )
        output = result.stdout + result.stderr
        return LintResult(
            success=(result.returncode == 0),
            output=output,
            command=lint_command,
        )
    except subprocess.TimeoutExpired:
        return LintResult(
            success=False,
            output="Lint command timed out after 60 seconds.",
            command=lint_command,
        )
    except Exception as e:
        return LintResult(
            success=False,
            output=f"Error running lint: {e}",
            command=lint_command,
        )


def run_tests(
    project_root: Path, test_command: Optional[str] = None
) -> TestResult:
    """Run tests on the project.

    Args:
        project_root: Root directory of the project.
        test_command: Specific test command to run. Auto-detected if None.

    Returns:
        TestResult with success status, output, and command used.
    """
    if test_command is None:
        test_command = detect_test_command(project_root)
        if test_command is None:
            return TestResult(
                success=False,
                output="No test command detected for this project.",
                command="",
            )

    logger.info("Running tests: %s", test_command)
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(project_root),
        )
        output = result.stdout + result.stderr
        return TestResult(
            success=(result.returncode == 0),
            output=output,
            command=test_command,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            success=False,
            output="Test command timed out after 120 seconds.",
            command=test_command,
        )
    except Exception as e:
        return TestResult(
            success=False,
            output=f"Error running tests: {e}",
            command=test_command,
        )
