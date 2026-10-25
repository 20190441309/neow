"""Skills browser modal for /skills."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional

from rich.text import Text
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option

from neow.core.skills import Skill, discover_skills, load_skill_content
from neow.tui.theme import get_palette


class SkillsModalScreen(ModalScreen):
    """Browse and load workspace/user skills (.neow/skills/<name>/SKILL.md)."""

    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    SkillsModalScreen .dialog {
        width: 78;
        max-height: 28;
    }
    SkillsModalScreen #skills-list {
        max-height: 9;
        margin-bottom: 1;
    }
    SkillsModalScreen #skill-preview {
        max-height: 11;
    }
    """

    def __init__(
        self,
        *,
        workspace_root: Optional[Path | str] = None,
        on_load: Optional[Callable[[str, str], None]] = None,
    ):
        super().__init__()
        self.workspace_root = workspace_root
        self.on_load = on_load
        self.skills: List[Skill] = discover_skills(workspace_root)
        self._selected: Optional[Skill] = self.skills[0] if self.skills else None

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "◆ 技能库 (Skills)"
        box.border_subtitle = "↑↓ 预览 · enter 加载到上下文 · esc 返回"
        palette = get_palette(self.app)
        with box:
            opt_list = OptionList(id="skills-list")
            if not self.skills:
                opt_list.add_option(
                    Option(
                        Text(
                            " ◇ 未发现技能文件 (.neow/skills/<name>/SKILL.md)",
                            style=palette["muted"],
                        ),
                        id="none",
                    )
                )
            else:
                for idx, s in enumerate(self.skills):
                    row = Text()
                    row.append(" ◆ ", style=palette["accent1"])
                    row.append(f"{s.name:<20} ", style=f"bold {palette['text']}")
                    row.append(f"[{s.scope}] ", style=palette["accent2"])
                    row.append(s.description[:42], style=palette["muted"])
                    opt_list.add_option(Option(row, id=f"skill-{idx}"))
            yield opt_list

            with VerticalScroll(id="skill-preview", classes="dialog-block"):
                yield Static("", id="skill-preview-text")

            with Horizontal(classes="actions"):
                if self.skills:
                    yield Button("加载选中技能", variant="primary", id="load-skill-btn")
                yield Button("关闭", id="close-skills-btn")

    def on_mount(self) -> None:
        self._update_preview(self._selected)
        self.query_one("#skills-list", OptionList).focus()

    def _update_preview(self, skill: Optional[Skill]) -> None:
        palette = get_palette(self.app)
        preview = self.query_one("#skill-preview-text", Static)
        if skill is None:
            hint = Text()
            hint.append("◇ 如何添加自定义技能\n", style=f"bold {palette['accent2']}")
            hint.append(
                "在项目目录 `.neow/skills/<技能名>/SKILL.md` 或用户目录 "
                "`~/.neow/skills/<技能名>/SKILL.md` 下创建指南，"
                "Agent 即可按需调用 `load_skill` 加载。",
                style=palette["muted"],
            )
            preview.update(hint)
            return
        content = load_skill_content(skill.name, self.workspace_root)
        txt = Text()
        txt.append(f"▸ {skill.name} ", style=f"bold {palette['accent1']}")
        txt.append(f"({skill.path})\n", style=palette["muted"])
        txt.append(content[:1200], style=palette["text"])
        preview.update(txt)

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        opt_id = event.option.id or ""
        if opt_id.startswith("skill-"):
            idx = int(opt_id.split("-", 1)[1])
            if 0 <= idx < len(self.skills):
                self._selected = self.skills[idx]
                self._update_preview(self._selected)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_id = event.option.id or ""
        if opt_id.startswith("skill-"):
            idx = int(opt_id.split("-", 1)[1])
            if 0 <= idx < len(self.skills):
                self._selected = self.skills[idx]
                self._load_selected()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close-skills-btn":
            self.app.pop_screen()
        elif event.button.id == "load-skill-btn":
            self._load_selected()

    def _load_selected(self) -> None:
        if self._selected is None:
            return
        content = load_skill_content(self._selected.name, self.workspace_root)
        self.app.pop_screen()
        if self.on_load is not None:
            self.on_load(self._selected.name, content)


__all__ = ["SkillsModalScreen"]
