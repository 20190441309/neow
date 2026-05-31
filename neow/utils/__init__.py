"""Utility functions for Neow CLI."""

def sanitize_text(text: str) -> str:
    """Remove surrogate characters that cause encoding errors."""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
