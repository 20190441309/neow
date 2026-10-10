"""Command sandbox (plan task 5.3, experimental)."""

import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest

from neow.core.approval import ApprovalMode, ApprovalPolicy
from neow.core.executor import ToolExecutor
from neow.cli.main import setup_tools
from neow.tools import sandbox
from neow.tools.command import execute_command

BWRAP = shutil.which("bwrap")
needs_bwrap = pytest.mark.skipif(BWRAP is None, reason="bwrap not installed")


@pytest.fixture(autouse=True)
def reset_sandbox():
    yield
    sandbox.configure()  # back to off for other tests


@pytest.fixture
def project(tmp_path, monkeypatch):
    work = tmp_path / "project"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


@pytest.fixture
def outside():
    """A directory outside the project and the temp dir."""
    path = Path(tempfile.mkdtemp(prefix=".neow-sandbox-test-", dir=Path.home()))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_bwrap_command_line(project):
    sandbox.configure(mode="auto", bwrap="/opt/bwrap", writable=["~/cache"])
    argv, reason = sandbox.sandbox_argv("make test", str(project), platform="linux")
    assert reason == "" and argv[0] == "/opt/bwrap"
    assert argv[1:4] == ["--ro-bind", "/", "/"]
    real = str(project.resolve())
    assert ["--bind", real, real] == argv[argv.index(real) - 1 :][:3]
    assert "--unshare-net" in argv
    assert argv[argv.index("--chdir") + 1] == real
    assert argv[-3:] == ["/bin/sh", "-c", "make test"]

    sandbox.configure(mode="auto", bwrap="/opt/bwrap", network=True)
    argv, _ = sandbox.sandbox_argv("x", str(project), platform="linux")
    assert "--unshare-net" not in argv


def test_macos_profile(project):
    sandbox.configure(mode="auto")
    profile = sandbox._seatbelt_profile(str(project))
    assert "(deny file-write*)" in profile and "(deny network*)" in profile
    assert f'(subpath "{project.resolve()}")' in profile
    _, reason = sandbox.sandbox_argv("x", str(project), platform="win32")
    assert "no sandbox" in reason


def test_modes_without_a_sandbox(project, monkeypatch):
    monkeypatch.setattr(sandbox.shutil, "which", lambda name: None)
    sandbox.configure(mode="off")
    assert sandbox.plan("ls", str(project)) == (None, "")

    sandbox.configure(mode="strict")
    result = execute_command("touch made.txt", cwd=str(project))
    assert result.startswith("Error: sandbox required") and "bwrap" in result
    assert not (project / "made.txt").exists()  # refused, not run

    sandbox.configure(mode="auto")
    first = execute_command("echo hi", cwd=str(project))
    assert first.startswith("[sandbox unavailable") and first.endswith("hi\n")
    assert execute_command("echo hi", cwd=str(project)) == "hi\n"  # warned once
    sandbox.configure(mode="nonsense")
    assert sandbox.current().mode == "off"


def test_approval_prompt_says_whether_sandboxed(project, monkeypatch):
    executor = ToolExecutor()
    setup_tools(executor)
    executor.approval_policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    reasons = []
    executor.approval_callback = lambda name, args, reason: reasons.append(reason)
    sandbox.configure(mode="auto", bwrap="/opt/bwrap")
    monkeypatch.setattr(sandbox.sys, "platform", "linux")
    with pytest.raises(Exception):
        executor.execute("execute_command", {"command": "ls"})
    assert "sandboxed: writes limited to the project" in reasons[-1]

    sandbox.configure(mode="off")
    with pytest.raises(Exception):
        executor.execute("execute_command", {"command": "ls"})
    assert "sandbox" not in reasons[-1]


@needs_bwrap
def test_sandbox_blocks_write_outside_cwd(project, outside):
    sandbox.configure(mode="strict")
    inside = execute_command("echo ok > inside.txt && cat inside.txt", cwd=str(project))
    assert inside == "ok\n"
    escaped = execute_command(f"echo x > {outside}/escape.txt", cwd=str(project))
    assert escaped.startswith("Error: exit code") and "Read-only" in escaped
    assert not (outside / "escape.txt").exists()
    # Temp files still work (compilers, test runners).
    assert execute_command(
        f"f={tempfile.gettempdir()}/neow-sbx-$$.txt; echo t > $f && rm $f && echo done",
        cwd=str(project),
    ).endswith("done\n")


@needs_bwrap
def test_sandbox_blocks_network(project):
    # A port open on the host's loopback: reachable only from the host's
    # network namespace.
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    probe = (
        'python3 -c "import socket; '
        f"socket.create_connection(('127.0.0.1', {port}), timeout=2); "
        "print('connected')\" 2>&1 | tail -1"
    )
    try:
        sandbox.configure(mode="strict")
        assert "refused" in execute_command(probe, cwd=str(project))
        sandbox.configure(mode="strict", network=True)
        assert execute_command(probe, cwd=str(project)) == "connected\n"
    finally:
        server.close()


@needs_bwrap
def test_sandboxed_command_still_times_out(project):
    sandbox.configure(mode="strict")
    started = time.monotonic()
    result = execute_command("sleep 30", timeout=1, cwd=str(project))
    assert result.startswith("Error: Command timed out after 1 seconds")
    assert time.monotonic() - started < 10
