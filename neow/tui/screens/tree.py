"""Session tree screen."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from rich.text import Text
from textual.screen import Screen
from textual.widgets import Tree


class SessionTreeScreen(Screen):
    """Interactive session tree: Enter navigates, ``b`` branches."""

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

    def compose(self):
        widget: Tree = Tree("Session")
        nodes: Dict[str, Any] = {}
        for node_id, node in self.tree_data.items():
            marker = " *" if node_id == self.leaf_id else ""
            preview = str(node.get("content_preview", ""))[:60]
            label = f"[{node_id[:8]}] {node.get('role', '?')}: {preview}{marker}"
            nodes[node_id] = {"label": label, "children": node.get("children", [])}

        def add(parent, node_id: str) -> None:
            info = nodes.get(node_id)
            if info is None:
                return
            child = parent.add(Text(info["label"]), data=node_id, expand=True)
            for next_id in info["children"]:
                add(child, next_id)

        for node_id, node in self.tree_data.items():
            if node.get("parentId") is None:
                add(widget.root, node_id)
        widget.root.expand()
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
