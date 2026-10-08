"""Neow TUI palettes and theme helpers (design spec §8.3)."""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_THEME = "midnight"

MIDNIGHT: Dict[str, Any] = {
    "bg": "#0b0d12",
    "surface": "#0f1117",
    "elevated": "#151a23",
    "panel": "#0f1117",
    "border": "#1e293b",
    "border_strong": "#334155",
    "text": "#e5e7eb",
    "dim": "#94a3b8",
    "muted": "#64748b",
    "accent1": "#22d3ee",
    "accent2": "#a78bfa",
    "accent3": "#f472b6",
    "accent4": "#facc15",
    "success": "#34d399",
    "error": "#f87171",
    "warn": "#facc15",
    "info": "#38bdf8",
    "role_user": "#22d3ee",
    "role_assistant": "#a78bfa",
    "role_thinking": "#52525b",
    "tool_running": "#facc15",
    "tool_done": "#34d399",
    "tool_error": "#f87171",
    "compaction": "#38bdf8",
    "settled": "#71717a",
    "user_bg": "#111a24",
    "code_bg": "#10141c",
    "error_bg": "#1c1216",
    "selection": "#1e293b",
    "gradient": ["#22d3ee", "#a78bfa", "#f472b6", "#facc15"],
}

LIGHT: Dict[str, Any] = {
    "bg": "#f8fafc",
    "surface": "#ffffff",
    "elevated": "#f1f5f9",
    "panel": "#eef2f7",
    "border": "#cbd5e1",
    "border_strong": "#94a3b8",
    "text": "#0f172a",
    "dim": "#475569",
    "muted": "#64748b",
    "accent1": "#0891b2",
    "accent2": "#7c3aed",
    "accent3": "#db2777",
    "accent4": "#b45309",
    "success": "#059669",
    "error": "#dc2626",
    "warn": "#b45309",
    "info": "#0284c7",
    "role_user": "#0891b2",
    "role_assistant": "#7c3aed",
    "role_thinking": "#6b7280",
    "tool_running": "#b45309",
    "tool_done": "#059669",
    "tool_error": "#dc2626",
    "compaction": "#0284c7",
    "settled": "#64748b",
    "user_bg": "#ecf8fb",
    "code_bg": "#f1f5f9",
    "error_bg": "#fdf0f0",
    "selection": "#e2e8f0",
    "gradient": ["#0891b2", "#7c3aed", "#db2777", "#b45309"],
}

PALETTES: Dict[str, Dict[str, Any]] = {"midnight": MIDNIGHT, "light": LIGHT}


def get_palette(app: Any = None) -> Dict[str, Any]:
    """Active palette, falling back to midnight when no app is available."""

    palette = getattr(app, "palette", None) if app is not None else None
    return palette or PALETTES[DEFAULT_THEME]


def widget_palette(widget: Any) -> Dict[str, Any]:
    """Palette for a widget, safe to call before mount."""

    try:
        return get_palette(widget.app)
    except Exception:
        return get_palette(None)


def theme_variables(palette: Dict[str, Any]) -> Dict[str, str]:
    """CSS variables (``$neow-*``) for a registered Textual theme.

    Also maps markdown headings onto the palette so assistant replies use
    bold role colours instead of Textual's underlined ANSI defaults.
    """

    variables = {
        f"neow-{key}": value for key, value in palette.items() if isinstance(value, str)
    }
    headings = [
        palette["accent2"],
        palette["accent1"],
        palette["text"],
        palette["dim"],
        palette["dim"],
        palette["muted"],
    ]
    for level, color in enumerate(headings, start=1):
        variables[f"markdown-h{level}-color"] = color
        variables[f"markdown-h{level}-background"] = "transparent"
        variables[f"markdown-h{level}-text-style"] = "bold"
    return variables


__all__ = [
    "DEFAULT_THEME",
    "MIDNIGHT",
    "LIGHT",
    "PALETTES",
    "get_palette",
    "widget_palette",
    "theme_variables",
]
