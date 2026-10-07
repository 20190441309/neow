# Neow TUI 参考调研与技术可行性（t2）

> 目的：为 neow 全屏 TUI 设计提供参考依据，并验证 Textual 8.x 上炫酷效果的可行性。
> 环境：Python 3.12 + textual 8.2.8（/home/neow/.venv）
> 状态：可行性已验证，见 `tui-feasibility/demo.py`（一次性实验，不是产品代码）

---

## 1. 参考项目拆解

### 1.1 crush（charmbracelet/crush，Go + Bubble Tea）——「乱码闪动」的原始参考

用户点名的效果来自 crush 的 `internal/ui/anim/anim.go`（已读源码）：

| 机制 | 实现要点 |
|------|---------|
| 乱码字符集 | `availableRunes = "0123456789abcdefABCDEF~!@#$£€%^&*()+=_"` |
| 帧率 | `fps = 20`（50ms/帧），帧预渲染（`prerenderedFrames = 10`）后循环 |
| 渐变 | 在 `defaultGradColorA`→`B` 之间生成 ramp，色彩沿字符区域流动 |
| 逐字定型（birth） | 每个字符有随机出生步数（`maxBirthSteps = 20`），约 1s 内逐个从乱码「落定」为真实文本 |
| 省略号 | `ellipsisFrames = [".", "..", "...", ""]`，每 8 帧变一次 |
| 可关闭 | `NoScramble` 开关：非 LLM 语境只显示省略号，避免误导 |

**关键结论**：crush 的 scramble 不是「纯随机噪音」，而是 **随机字形 + 色彩流动 + 左→右逐字定型**，且带开关。我们的 thinking 卡应复刻这个语义：思考中=乱码闪动，内容落定后=正常 Markdown。

### 1.2 opencode（sst/opencode）——TUI 产品形态参考

- TS 核心 + Go（Bubble Tea）全屏 TUI，默认进入全屏界面，支持会话切换、模型选择、工具流。
- 交互模式：底部输入、消息时间线、工具调用以内联块展示。
- 对 neow 的启示：**原生命令入口（TUI 默认 + 子命令）** 是主流做法，与已确认的「TUI 转正为默认入口」一致。

### 1.3 Codex CLI（openai/codex，Rust + ratatui）

- 全屏 alternate-buffer TUI；聊天 transcript 视口 + 底部状态/输入区；审批以模态弹窗出现。
- 对 neow 的启示：审批弹窗（approval modal）用独立焦点层，不打断主时间线；底部常驻状态栏承载 model/token/审批模式。

### 1.4 Claude Code（行式 REPL 的克制路线）

- 并非全屏 TUI：行内输出 + `✻ Thinking…` 状态行（spinner + 闪烁）。
- 对 neow 的启示：**思考态是需要单独设计的「状态」**，无论行式还是全屏。我们把它升级成卡片 + scramble，是差异化亮点。

### 1.5 Warp（卡片时间线，用户选定形态）

- Agent 的每个动作（命令、计划、编辑）是时间线上的一个 block，可折叠查看输出。
- 对 neow 的启示：卡片 = 时间线的原子单位；标题行承载 `状态图标 + 工具名/角色 + 摘要`；正文可折叠。

---

## 2. Textual 8.2.8 能力矩阵（已在本机验证）

| 能力 | API | 验证结果 |
|------|-----|---------|
| 渐变取色 | `textual.color.Gradient.from_colors(...).get_color(t)` → `.hex` | ✅ |
| 可折叠卡片 | `Collapsible(title=..., collapsed=...)`，动态改 `collapsed` | ✅ |
| 流式 Markdown | `Markdown.append(chunk)`（awaitable）；内部 `MarkdownStream` 可用但未顶层导出 | ✅ |
| 逐帧动画 | `Static.update(Rich Text)` + `set_interval(1/20)`；`Widget.animate`/`styles.animate` 可用 | ✅ |
| 截图（证据留存） | `App.save_screenshot(path)` → SVG，`export_screenshot()` | ✅ |
| 无头测试 | `App.run_test(size=(110,36))` + `Pilot.pause()`，可断言组件状态 | ✅ |
| 命令面板 | Textual 内置 Command Palette（Ctrl+P） | 待 t3 设计确认是否启用 |
| 鼠标 | Textual 原生支持 | 待定 |

### 2.1 两个必须记住的坑（已在 demo 中踩过并修复）

1. **不要定义 `Widget._render()`**：它是 Textual 内部「取 Visual」的方法，覆盖后布局会拿到 Rich Text 并崩溃（`'Text' object has no attribute 'get_height'`）。自定义渲染函数要另起名（demo 用 `_frame()`）。
2. **Rich Text 样式要传字符串**：`textual.Color.rich_color` 返回的是 Rich Color 对象，传给 `Text.append(style=...)` 会崩；用 `Color.hex`（`"#rrggbb"`）。

---

## 3. 可行性 Demo 结论

`docs/research/tui-feasibility/demo.py --headless` → **FEASIBILITY OK**，产出 3 张 SVG 截图（/tmp/neow-tui-feasibility/）：

1. `AnimatedLogo`：逐字符渐变 + phase 流动 — ✅
2. `ScrambleText`：20FPS 随机字形 + 渐变 + 左→右定型 — ✅
3. `ToolCard`：Collapsible 折叠/展开 + diff 内容 — ✅
4. `StreamCard`：Markdown 分块流式追加 — ✅

断言：scramble 进度推进、折叠状态可切换、markdown 内容完整、logo 存在。

---

## 4. 对 neow TUI 设计的直接输入（供 t3 使用）

- **卡片时间线**：`VerticalScroll` 容器 + 卡片组件族（user / assistant / thinking / tool / diff / error）；工具卡默认折叠标题行，正文可展开。
- **Thinking 卡**：crush 式 scramble（随机 rune + 渐变 + 逐字定型），落定后切换为正常文本或折叠为「已思考 Ns」。
- **启动动画**：渐变 ASCII logo，phase 流动；首轮输入后收起为 header 小 logo。
- **性能**：动效只在卡片处于可见/进行中时运行（`set_interval` 可暂停）；静态卡片不挂定时器。
- **降级**：非 TTY / `--plain` 走现有 Rich 行式路径，动效不启动。
- **审批**：`ModalScreen` 弹窗，键盘 y/n/a；与现有 `ApprovalPolicy` 对接。
- **测试**：Textual `run_test`/`Pilot` 做组件级测试，动效类用「进度推进 + 内容非空」类断言而非逐帧快照。
