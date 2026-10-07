"""Clipboard helpers tests (TUI polish task 4)."""

from neow.tui.clipboard import extract_last_code_block


def test_extract_last_code_block():
    text = "a\n```python\nx = 1\n```\nb\n```bash\necho hi\n```\n"
    assert extract_last_code_block(text) == "echo hi"


def test_extract_no_code_block():
    assert extract_last_code_block("plain text") is None


def test_extract_unclosed_fence_returns_none():
    assert extract_last_code_block("```python\nx = 1") is None
