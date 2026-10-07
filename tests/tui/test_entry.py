"""入口模式选择测试（实现计划任务 1）。"""

import pytest
from click.testing import CliRunner

from neow.cli.main import main as cli_main
from neow.cli.mode import ModeError, RunMode, select_run_mode


def _m(**kw):
    base = dict(prompt=None, plain=False, tui=False, stdin_tty=True, stdout_tty=True)
    base.update(kw)
    return select_run_mode(**base)


def test_default_tty_is_tui():
    assert _m() is RunMode.TUI


def test_prompt_is_oneshot_even_non_tty():
    assert _m(prompt="hi", stdin_tty=False, stdout_tty=False) is RunMode.ONESHOT


def test_plain_flag():
    assert _m(plain=True) is RunMode.PLAIN


def test_tui_flag_non_tty_raises():
    with pytest.raises(ModeError):
        _m(tui=True, stdout_tty=False)


def test_plain_and_tui_conflict():
    with pytest.raises(ModeError):
        _m(plain=True, tui=True)


def test_no_tty_falls_back_plain():
    assert _m(stdout_tty=False) is RunMode.PLAIN


def test_piped_stdin_falls_back_plain():
    assert _m(stdin_tty=False) is RunMode.PLAIN


def test_tui_flag_tty():
    assert _m(tui=True) is RunMode.TUI


def test_cli_flags_conflict_exits_2():
    result = CliRunner().invoke(cli_main, ["--plain", "--tui"])
    assert result.exit_code == 2
    assert "mutually exclusive" in result.output


def test_cli_tui_non_tty_exits_2():
    result = CliRunner().invoke(cli_main, ["--tui"])
    assert result.exit_code == 2
    assert "TTY" in result.output
