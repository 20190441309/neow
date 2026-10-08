"""Help screen: commands and keybindings."""

from __future__ import annotations

from textual.screen import Screen
from textual.containers import VerticalScroll
from textual.widgets import Static

HELP_TEXT = """\
NEOW · 斜杠命令
  /help              显示帮助
  /model             切换或查看模型
  /diff              查看未提交改动
  /commit [msg]      提交（无 msg 时由 AI 生成）
  /undo              回退上一次 AI 提交
  /add <file>        加入上下文
  /drop <file>       移出上下文
  /ls                列出上下文文件
  /lint · /test      运行 linter / 测试（支持 on/off）
  /architect · /code 架构师模式 / 编码模式
  /save · /load      保存 / 载入会话
  /history           历史会话
  /cost              token 与费用
  /web <url>         抓取网页加入上下文
  /think             查看最近一次推理内容
  /compact           压缩上下文（incremental / handoff）
  /export            导出 Markdown
  /image <file>      附加图片
  /approval          审批模式（always-ask / write / yolo）
  /tree · /branch    会话树导航 / 分叉
  /verbose           切换工具参数展开
  /clear             清空会话历史
  /exit              退出

键位
  Enter 发送 · Ctrl+J 换行 · Esc 中断
  ↑↓ 选择候选 · Tab/Enter 补全 · Esc 收起候选
  Ctrl+B 侧栏 · Ctrl+T 侧栏页 · Ctrl+O 折叠卡片
  PgUp/PgDn 滚动 · Ctrl+P 命令面板 · Ctrl+Q 退出
"""


class HelpScreen(Screen):
    """Static help overlay (F1 / /help)."""

    BINDINGS = [
        ("escape", "app.pop_screen", "返回"),
        ("q", "app.pop_screen", "返回"),
    ]

    def compose(self):
        with VerticalScroll():
            yield Static(HELP_TEXT, id="help-text")

    def on_mount(self) -> None:
        self.query_one(VerticalScroll).focus()


__all__ = ["HelpScreen", "HELP_TEXT"]
