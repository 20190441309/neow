"""Tests for web content fetching."""

import pytest
from unittest.mock import MagicMock, patch
from neow.tools.web import WebFetcher, WebContent


class TestWebContent:
    """Tests for WebContent dataclass."""

    def test_web_content_creation(self):
        content = WebContent(
            url="https://example.com",
            title="Example",
            text="Hello world",
            code_blocks=[],
            content_type="webpage",
        )
        assert content.url == "https://example.com"
        assert content.title == "Example"
        assert content.content_type == "webpage"

    def test_web_content_with_code_blocks(self):
        content = WebContent(
            url="https://example.com",
            title="Code Page",
            text="See the code below",
            code_blocks=[("python", "print('hello')")],
            content_type="webpage",
        )
        assert len(content.code_blocks) == 1
        assert content.code_blocks[0][0] == "python"


class TestWebFetcher:
    """Tests for WebFetcher."""

    def test_init_defaults(self):
        fetcher = WebFetcher({})
        assert fetcher.timeout == 10
        assert fetcher.max_length == 10000

    def test_init_custom_config(self):
        fetcher = WebFetcher({"timeout": 30, "max_content_length": 5000})
        assert fetcher.timeout == 30
        assert fetcher.max_length == 5000

    def test_is_github_url_issues(self):
        fetcher = WebFetcher({})
        assert fetcher._is_github_url("https://github.com/owner/repo/issues/42") is True
        assert fetcher._is_github_url("https://github.com/owner/repo/pull/100") is True

    def test_is_github_url_not_github(self):
        fetcher = WebFetcher({})
        assert fetcher._is_github_url("https://example.com") is False
        assert fetcher._is_github_url("https://google.com") is False

    def test_parse_github_url_issue(self):
        fetcher = WebFetcher({})
        result = fetcher._parse_github_url("https://github.com/owner/repo/issues/42")
        assert result == ("owner", "repo", "issues", "42")

    def test_parse_github_url_pr(self):
        fetcher = WebFetcher({})
        result = fetcher._parse_github_url("https://github.com/octocat/hello-world/pull/5")
        assert result == ("octocat", "hello-world", "pull", "5")

    def test_parse_github_url_invalid(self):
        fetcher = WebFetcher({})
        result = fetcher._parse_github_url("https://github.com/owner")
        assert result is None

    def test_clean_text_truncates(self):
        fetcher = WebFetcher({"max_content_length": 20})
        result = fetcher._clean_text("a" * 100)
        assert len(result) <= 23  # 20 + "..."

    def test_clean_text_removes_excess_whitespace(self):
        fetcher = WebFetcher({})
        result = fetcher._clean_text("hello   \n\n\n  world")
        assert "   " not in result
        assert "\n\n\n" not in result

    def test_extract_code_blocks(self):
        fetcher = WebFetcher({})
        html = '<pre><code class="language-python">print("hi")</code></pre>'
        blocks = fetcher._extract_code_blocks(html)
        assert len(blocks) == 1
        assert blocks[0][0] == "python"
        assert 'print("hi")' in blocks[0][1]

    def test_extract_code_blocks_no_language(self):
        fetcher = WebFetcher({})
        html = "<pre><code>some code</code></pre>"
        blocks = fetcher._extract_code_blocks(html)
        assert len(blocks) == 1
        assert blocks[0][0] == ""  # no language specified

    def test_extract_code_blocks_empty(self):
        fetcher = WebFetcher({})
        blocks = fetcher._extract_code_blocks("<p>No code here</p>")
        assert blocks == []

    @patch("neow.tools.web.requests.get")
    def test_fetch_webpage(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        fetcher = WebFetcher({})
        # Patch readability to return simple content
        with patch("neow.tools.web.Document") as mock_doc:
            mock_doc_instance = MagicMock()
            mock_doc_instance.title.return_value = "Test"
            mock_doc_instance.summary.return_value = "<p>Hello world</p>"
            mock_doc.return_value = mock_doc_instance

            content = fetcher.fetch("https://example.com")
            assert content.url == "https://example.com"
            assert content.title == "Test"
            assert "Hello world" in content.text
            assert content.content_type == "webpage"

    @patch("neow.tools.web.subprocess.run")
    def test_extract_github_issue(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"title": "Bug report", "body": "Something broke", "comments": []}',
        )
        fetcher = WebFetcher({})
        content = fetcher.extract_github("https://github.com/owner/repo/issues/42")
        assert content.content_type == "github_issue"
        assert "Bug report" in content.text or content.title == "Bug report"

    @patch("neow.tools.web.subprocess.run")
    def test_extract_github_pr(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"title": "Fix bug", "body": "Fixed it", "comments": []}',
        )
        fetcher = WebFetcher({})
        content = fetcher.extract_github("https://github.com/owner/repo/pull/5")
        assert content.content_type == "github_pr"

    def test_fetch_routes_github_to_extract_github(self):
        fetcher = WebFetcher({})
        with patch.object(fetcher, "extract_github") as mock_gh:
            mock_gh.return_value = WebContent(
                url="https://github.com/o/r/issues/1",
                title="Issue", text="body",
                code_blocks=[], content_type="github_issue",
            )
            result = fetcher.fetch("https://github.com/o/r/issues/1")
            mock_gh.assert_called_once()
            assert result.content_type == "github_issue"
