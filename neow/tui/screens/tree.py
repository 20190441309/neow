"""Session tree screen."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from rich.text import Text
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Tree

from neow.tui.theme import get_palette

_ROLE_KEYS = {"user": "role_user", "assistant": "role_assistant", "tool": "tool_done"}


class SessionTreeScreen(ModalScreen):
    """Interactive session tree: Enter navigates, ``b`` branches."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("b", "branch", "分叉"),
    ]

    def __init__(
        self,
        *,
        tree: Dict[str, Any],
        leaf_id: Optional[str] = None,
        on_goto: Optional[Callable[[str], None]] = None,
        on_branch: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.tree_data = tree or {}
        self.leaf_id = leaf_id
        self.on_goto = on_goto
        self.on_branch = on_branch

    def _label(self, node_id: str, node: Dict[str, Any]) -> Text:
        palette = get_palette(self.app)
        role = str(node.get("role", "?"))
        preview = " ".join(str(node.get("content_preview", "")).split())[:60]
        out = Text(no_wrap=True, overflow="ellipsis")
        out.append(f"{node_id[:8]} ", palette["muted"])
        out.append(role, f"bold {palette[_ROLE_KEYS.get(role, 'dim')]}")
        out.append(f"  {preview}", palette["dim"])
        if node_id == self.leaf_id:
            out.append("  ● 当前", palette["success"])
        return out

    def compose(self):
        widget: Tree = Tree(Text("Session"))
        widget.show_root = False
        nodes: Dict[str, Any] = {}
        for node_id, node in self.tree_data.items():
            nodes[node_id] = {
                "label": self._label(node_id, node),
                "children": node.get("children", []),
            }

        def add(parent, node_id: str) -> None:
            info = nodes.get(node_id)
            if info is None:
                return
            child = parent.add(info["label"], data=node_id, expand=True)
            for next_id in info["children"]:
                add(child, next_id)

        for node_id, node in self.tree_data.items():
            if node.get("parentId") is None:
                add(widget.root, node_id)
        widget.root.expand()
        box = Vertical(classes="dialog tall wide")
        box.border_title = "会话树"
        box.border_subtitle = "enter 跳转 · b 分叉 · esc 返回"
        with box:
            if not self.tree_data:
                yield Static("当前会话还没有可导航的节点", classes="dialog-empty")
            yield widget

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node_id = event.node.data
        if node_id and self.on_goto is not None:
            self.on_goto(node_id)

    def action_branch(self) -> None:
        node = self.query_one(Tree).cursor_node
        if self.on_branch is not None and node is not None and node.data:
            self.on_branch(node.data)


__all__ = ["SessionTreeScreen"]
