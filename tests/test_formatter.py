"""Tests for UI formatter functions."""

from neow.utils.formatter import (
    make_logo,
    format_user_panel,
    format_assistant_panel,
    format_tool_call_panel,
    format_tool_result_panel,
    format_diff,
    render_markdown,
    create_status_bar,
    _looks_like_markdown,
)


class TestLogo:
    def test_make_logo_returns_string(self):
        result = make_logo("deepseek-chat", "0.5")
        assert isinstance(result, str)
        assert len(result) > 50  # logo is substantial
        assert "deepseek-chat" in result
        assert "Ready" in result

    def test_make_logo_no_model(self):
        result = make_logo("", "0.5")
        assert isinstance(result, str)
        assert len(result) > 50
        assert "Ready" in result

    def test_make_logo_default_version(self):
        result = make_logo("test-model")
        assert isinstance(result, str)


class TestUserPanel:
    def test_format_user_panel_returns_panel(self):
        from rich.panel import Panel
        result = format_user_panel("hello world")
        assert isinstance(result, Panel)

    def test_format_user_panel_contains_text(self):
        result = format_user_panel("test message")
        from rich.console import Console
        import io
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        console.print(result)
        output = buf.getvalue()
        assert "test message" in output


class TestAssistantPanel:
    def test_format_assistant_panel_returns_panel(self):
        from rich.panel import Panel
        result = format_assistant_panel("response text")
        assert isinstance(result, Panel)

    def test_format_assistant_panel_with_markdown(self):
        from rich.panel import Panel
        result = format_assistant_panel("# Heading\n\nSome text")
        assert isinstance(result, Panel)


class TestToolCallPanel:
    def test_format_tool_call_panel_basic(self):
        from rich.panel import Panel
        result = format_tool_call_panel("edit_file", {"file_path": "test.py"})
        assert isinstance(result, Panel)

    def test_format_tool_call_panel_contains_tool_name(self):
        result = format_tool_call_panel("read_file", {"file_path": "main.py"})
        from rich.console import Console
        import io
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        console.print(result)
        output = buf.getvalue()
        assert "read_file" in output

    def test_format_tool_call_panel_known_tool_icon(self):
        """Known tools should get specific icons."""
        from rich.panel import Panel
        result = format_tool_call_panel("execute_command", {"command": "ls"})
        assert isinstance(result, Panel)

    def test_format_tool_call_panel_unknown_tool(self):
        """Unknown tools should get generic icon."""
        from rich.panel import Panel
        result = format_tool_call_panel("custom_tool", {"arg": "val"})
        assert isinstance(result, Panel)

    def test_format_tool_call_panel_long_value_truncated(self):
        """Long parameter values should be truncated."""
        long_val = "x" * 200
        result = format_tool_call_panel("read_file", {"content": long_val})
        from rich.console import Console
        import io
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        console.print(result)
        output = buf.getvalue()
        assert "..." in output

    def test_format_tool_call_panel_no_params(self):
        from rich.panel import Panel
        result = format_tool_call_panel("git_status", {})
        assert isinstance(result, Panel)


class TestToolResultPanel:
    def test_format_tool_result_panel_success(self):
        from rich.panel import Panel
        result = format_tool_result_panel("file content here", is_error=False)
        assert isinstance(result, Panel)

    def test_format_tool_result_panel_error(self):
        from rich.panel import Panel
        result = format_tool_result_panel("Error: not found", is_error=True)
        assert isinstance(result, Panel)

    def test_format_tool_result_panel_long_result_truncated(self):
        long_result = "x" * 1000
        result = format_tool_result_panel(long_result)
        from rich.console import Console
        import io
        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=80)
        console.print(result)
        output = buf.getvalue()
        # Truncated to 500 chars
        assert len(long_result) > 500


class TestDiffFormatting:
    def test_format_diff_additions(self):
        diff = "+new line added\n-old line removed"
        result = format_diff(diff)
        assert result is not None

    def test_format_diff_empty(self):
        result = format_diff("")
        from rich.text import Text
        assert isinstance(result, Text)

    def test_format_diff_none(self):
        result = format_diff("")
        from rich.text import Text
        assert isinstance(result, Text)


class TestMarkdownRendering:
    def test_render_markdown_heading(self):
        from rich.markdown import Markdown
        result = render_markdown("# Hello")
        assert isinstance(result, Markdown)

    def test_render_markdown_code_block(self):
        from rich.markdown import Markdown
        result = render_markdown("```python\nprint('hi')\n```")
        assert isinstance(result, Markdown)


class TestLooksLikeMarkdown:
    def test_heading_detected(self):
        assert _looks_like_markdown("# Heading") is True

    def test_bullet_list_detected(self):
        assert _looks_like_markdown("- item one") is True

    def test_code_fence_detected(self):
        assert _looks_like_markdown("```python\ncode\n```") is True

    def test_link_detected(self):
        assert _looks_like_markdown("[text](http://example.com)") is True

    def test_plain_text_not_markdown(self):
        assert _looks_like_markdown("just a plain sentence") is False

    def test_empty_string_not_markdown(self):
        assert _looks_like_markdown("") is False


class TestStatusBar:
    def test_create_status_bar_returns_string(self):
        result = create_status_bar("deepseek-chat", 1200, 128000, 0.03)
        assert isinstance(result, str)
        assert "deepseek-chat" in result

    def test_create_status_bar_shows_cost(self):
        result = create_status_bar("model", 0, 128000, 1.2345)
        assert "$1.2345" in result

    def test_create_status_bar_shows_branch(self):
        result = create_status_bar("model", 0, 128000, 0.0, "main")
        assert "main" in result

    def test_create_status_bar_shows_token_pct(self):
        result = create_status_bar("model", 50000, 100000, 0.0)
        assert "50%" in result

    def test_create_status_bar_zero_max_no_crash(self):
        result = create_status_bar("model", 0, 0, 0.0)
        assert isinstance(result, str)

    def test_create_status_bar_shows_progress_bar(self):
        result = create_status_bar("model", 0, 128000, 0.0)
        assert "0%" in result
        assert "█" in result or "░" in result
