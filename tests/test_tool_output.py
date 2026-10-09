"""Bounded tool output and paged read_file (plan task 2.1)."""

import json

import pytest

from neow.core.agent_loop import truncate_tool_output
from neow.core.config import Config
from neow.tools.file_ops import edit_file, read_file
from neow.tools.hashline_edit import compute_hash
from tests.test_agent_loop import _call, _conversation


def _lines(n):
    return "".join(f"line {i}\n" for i in range(1, n + 1))


def test_read_file_numbers_lines_and_keeps_hashline(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("first\nsecond\n")
    result = read_file(str(path))
    expected_hash = compute_hash("first\nsecond\n")
    assert result.splitlines()[:2] == ["     1\tfirst", "     2\tsecond"]
    assert result.splitlines()[-1] == f"¶{path}#{expected_hash}"


def test_read_file_offset_limit_numbered(tmp_path):
    path = tmp_path / "big.txt"
    content = _lines(2500)
    path.write_text(content)

    first = read_file(str(path))
    assert first.splitlines()[0] == "     1\tline 1"
    assert "  2000\tline 2000" in first
    assert "line 2001" not in first
    assert "Showing lines 1-2000 of 2500. Use offset=2001 to read more." in first

    page = read_file(str(path), offset=2401, limit=50)
    assert page.splitlines()[0] == "  2401\tline 2401"
    assert "  2450\tline 2450" in page and "line 2451" not in page
    # The anchor always covers the whole file, so hashline_edit still works.
    assert page.splitlines()[-1].endswith(f"#{compute_hash(content)}")


def test_read_file_offset_past_end(tmp_path):
    path = tmp_path / "short.txt"
    path.write_text("one\ntwo\n")
    assert "only 2 lines" in read_file(str(path), offset=10)


def test_read_file_long_line_truncated(tmp_path):
    path = tmp_path / "min.js"
    path.write_text("x" * 5000 + "\n")
    line = read_file(str(path)).splitlines()[0]
    assert len(line) < 2100 and line.endswith("… [line truncated, 5000 chars]")


def test_read_file_binary_detected(tmp_path):
    path = tmp_path / "logo.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(100))
    result = read_file(str(path))
    assert result.startswith("Binary file")
    assert "\x00" not in result


def test_read_file_empty(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("")
    assert read_file(str(path)).startswith("(empty file)")


def test_edit_after_numbered_read_still_matches(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("def f():\n    return 1\n")
    copied = read_file(str(path)).splitlines()[1]  # "     2\t    return 1"

    edit_file(str(path), old_text=copied, new_text="     2\t    return 2")

    assert path.read_text() == "def f():\n    return 2\n"


def test_tool_output_truncated_head_tail():
    text = "".join(f"{i:05d}\n" for i in range(20000))  # 120,000 chars
    out = truncate_tool_output(text, limit=1000)
    assert len(out) < 1200
    assert out.startswith("00000\n")
    assert out.rstrip().endswith("19999")
    assert "[truncated 119000 chars" in out
    assert truncate_tool_output("short", limit=1000) == "short"


def test_loop_bounds_tool_results_in_history():
    class Loud:
        def execute(self, name, args):
            return "x" * 50_000

    script = [
        {"content": "", "tool_calls": [_call("c1", "execute_command", command="cat")]},
        {"content": "done"},
    ]
    conv, client = _conversation(script, Loud(), max_tool_output_chars=2000)
    list(conv.get_response_stream("go"))
    result = next(m["content"] for m in conv.messages if m["role"] == "tool")
    assert len(result) < 2200 and "truncated" in result
    # The model saw the bounded version too.
    sent = [m for m in client.requests[1] if m["role"] == "tool"][0]["content"]
    assert sent == result


@pytest.mark.parametrize("value, expected", [(None, 30000), (5000, 5000), (0, 30000)])
def test_agent_config_max_tool_output_chars(tmp_path, value, expected):
    path = tmp_path / "c.json"
    agent = {} if value is None else {"max_tool_output_chars": value}
    path.write_text(json.dumps({"agent": agent}))
    assert Config(path).agent["max_tool_output_chars"] == expected
