"""Clipboard helpers for the TUI (design spec §7.1)."""

from __future__ import annotations

import re
from typing import Optional

CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def extract_last_code_block(markdown: str) -> Optional[str]:
    """Return the content of the last fenced code block, if any."""

    matches = list(CODE_FENCE_RE.finditer(markdown or ""))
    if not matches:
        return None
    return matches[-1].group(1).strip("\n")


__all__ = ["extract_last_code_block"]
