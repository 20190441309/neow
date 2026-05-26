"""Web content fetching and extraction for Neow CLI."""

import re
import subprocess
import json
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import requests
from readability import Document
from bs4 import BeautifulSoup

from neow.utils.logger import logger


@dataclass
class WebContent:
    """Structured web content extracted from a URL."""

    url: str
    title: str
    text: str
    code_blocks: List[Tuple[str, str]] = field(default_factory=list)
    content_type: str = "webpage"  # "webpage" | "github_issue" | "github_pr"


class WebFetcher:
    """Fetches web pages and extracts useful content."""

    GITHUB_URL_PATTERN = re.compile(
        r"https?://github\.com/([^/]+)/([^/]+)/(issues|pull)/(\d+)"
    )

    def __init__(self, config: dict):
        self.timeout = config.get("timeout", 10)
        self.max_length = config.get("max_content_length", 10000)

    def fetch(self, url: str) -> WebContent:
        """Fetch a URL and return structured content.

        Routes GitHub issue/PR URLs to extract_github().
        For other URLs, uses readability + BeautifulSoup.
        """
        if self._is_github_url(url):
            return self.extract_github(url)

        resp = requests.get(url, timeout=self.timeout, headers={
            "User-Agent": "Neow-CLI/1.0"
        })
        resp.raise_for_status()

        html = resp.text
        doc = Document(html)
        title = doc.title()
        summary_html = doc.summary()

        # Extract text from readability summary
        soup = BeautifulSoup(summary_html, "lxml")
        text = soup.get_text(separator="\n")

        # Extract code blocks from full HTML
        code_blocks = self._extract_code_blocks(html)

        return WebContent(
            url=url,
            title=title,
            text=self._clean_text(text),
            code_blocks=code_blocks,
            content_type="webpage",
        )

    def extract_github(self, url: str) -> WebContent:
        """Extract GitHub issue or PR content using gh CLI."""
        parsed = self._parse_github_url(url)
        if not parsed:
            raise ValueError(f"Not a valid GitHub issue/PR URL: {url}")

        owner, repo, kind, number = parsed
        cmd = ["gh", kind.rstrip("s"), "view", number, "--repo", f"{owner}/{repo}"]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
            if result.returncode != 0:
                raise RuntimeError(f"gh CLI failed: {result.stderr}")

            data = json.loads(result.stdout)
        except FileNotFoundError:
            raise RuntimeError("gh CLI not found. Install it to fetch GitHub content.")

        title = data.get("title", "")
        body = data.get("body", "")
        comments = data.get("comments", [])

        text_parts = [f"# {title}\n", body]
        for comment in comments:
            author = comment.get("author", {}).get("login", "unknown")
            text_parts.append(f"\n---\n**{author}:** {comment.get('body', '')}")

        content_type = "github_issue" if kind == "issues" else "github_pr"

        return WebContent(
            url=url,
            title=title,
            text=self._clean_text("\n".join(text_parts)),
            code_blocks=[],
            content_type=content_type,
        )

    def _is_github_url(self, url: str) -> bool:
        """Check if URL is a GitHub issue or PR."""
        return bool(self.GITHUB_URL_PATTERN.match(url))

    def _parse_github_url(self, url: str) -> Optional[Tuple[str, str, str, str]]:
        """Parse GitHub URL into (owner, repo, kind, number)."""
        match = self.GITHUB_URL_PATTERN.match(url)
        if match:
            return match.group(1), match.group(2), match.group(3), match.group(4)
        return None

    def _extract_code_blocks(self, html: str) -> List[Tuple[str, str]]:
        """Extract <pre><code> blocks from HTML, preserving language hints."""
        soup = BeautifulSoup(html, "lxml")
        blocks = []
        for pre in soup.find_all("pre"):
            code = pre.find("code")
            if not code:
                continue
            lang = ""
            classes = code.get("class", [])
            for cls in classes:
                if cls.startswith("language-"):
                    lang = cls[len("language-"):]
                    break
            blocks.append((lang, code.get_text()))
        return blocks

    def _clean_text(self, text: str) -> str:
        """Clean whitespace and truncate to max_length."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip()

        if len(text) > self.max_length:
            text = text[:self.max_length] + "..."

        return text
