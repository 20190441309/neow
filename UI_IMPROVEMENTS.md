# Neow CLI UI 改进建议

> 基于对 `neow/utils/formatter.py` 与 `neow/cli/repl.py` 的分析
> 改动目标：让终端对话 UI 更现代、更清晰、更有层次感

---

## 总体状态

**全部 9 个改进点已落地** ✅

| # | 改进点 | 状态 |
|---|--------|------|
| 1 | 流式 Panel 包裹 | ✅ 已完成 |
| 2 | 色彩主题系统 | ✅ 已完成 |
| 3 | 时间戳/消息编号 | ✅ 已完成 |
| 4 | Tool Call 折叠 | ✅ 已完成 |
| 5 | 非交互模式 spinner | ✅ 已完成 |
| 6 | 欢迎页重设计 | ✅ 已完成 |
| 7 | 行内 Diff | ✅ 已完成 |
| 8 | Code Block 语言高亮 | ✅ 已完成 |
| 9 | 窄终端适配 | ✅ 已完成 |

**验证基线：** 全套 441 个测试通过，无回归。

**改动文件清单：**

| 文件 | 涉及改进点 |
|------|-----------|
| `neow/utils/formatter.py` | 点 1/2/3/4/6/7/8/9（几乎所有视觉层） |
| `neow/cli/repl.py` | 点 1/2/3/4/6/7（REPL 集成） |
| `neow/cli/main.py` | 点 5（非交互 spinner） |
| `neow/cli/commands.py` | 点 4（`/verbose` 命令注册） |
| `tests/test_formatter.py` | 点 2（测试 console 加 NEOW_THEME） |

---

## 改进点 1：流式输出的 Assistant 消息没有 Panel 包裹 ✅ 已完成

**痛点**: 流式模式 (`_process_input_stream`) 中，输出是裸 `sys.stdout.write`，完全没用 Rich 的 Panel 或 Markdown 渲染，看起来就是纯文本刷屏。

**方案**: 用 Rich 的 `Live` 上下文管理器做流式 Panel。每收到新内容就更新同一个 Panel，而不是裸写 stdout。

**涉及文件**: `neow/cli/repl.py`（`_process_input_stream` 方法），可能需要 `neow/utils/formatter.py` 添加辅助函数。

---

## 改进点 2：色彩方案太初级 — 缺乏主题系统 ✅ 已完成

**痛点**: 只有 `blue=user, green=assistant, yellow=tool, magenta=approval, dim=thinking` 这几种颜色，面板边框是纯色实线，视觉层级扁平。

**方案**: 引入调色板/主题系统。Rich 原生支持 themes。
- 用渐变色/双色边框区分角色
- code block 内部用实际语言高亮而非全 monokai
- 为不同严重级别使用不同色调（info=cyan, warn=gold/orange, error=red, success=green）

**涉及文件**: `neow/utils/formatter.py`。

---

## 改进点 3：对话消息没有时间戳和消息编号 ✅ 已完成

**痛点**: 长对话后在终端里很难快速定位某条消息。消息之间没有视觉分隔线。

**方案**:
- 每条消息前加 dim 色的时间戳或消息序号
- Assistant 消息之间用 `─` 或 `╌` 字符做轻量分隔线
- 可以用不同面板圆角/样式区分（user=左下圆角, assistant=右下圆角，类似聊天气泡）

**涉及文件**: `neow/utils/formatter.py`，`neow/cli/repl.py`。

---

## 改进点 4：Tool Call 展示太啰嗦 ✅ 已完成

**痛点**: 每个 tool call 展开显示所有参数，对 `search_code`、`execute_command` 这类参数长的工具，屏幕被占满。

**方案**:
- 默认折叠参数，只显示工具名 + emoji + 一行描述
- 提供 `--verbose` 或 `/detail` 展开完整参数
- tool call 组嵌套缩进，形成"树状"结构，清晰展示调用链

**涉及文件**: `neow/utils/formatter.py`（`format_tool_call_panel`），`neow/cli/repl.py`。

---

## 改进点 5：不在交互模式下没有 Progress/Status 反馈 ✅ 已完成

**痛点**: 非交互模式 `neow "prompt"` 没有 spinner，长时间等待时用户不知道是否在运行。

**方案**:
- 非交互模式也加一个简单的思考动画（spinning 点）
- 显示 `[dim]Thinking...[/dim]` + 实时 token 计数

**涉及文件**: `neow/cli/main.py`，`neow/cli/repl.py`。

---

## 改进点 6：欢迎页虽然做了 Table 但太生硬 ✅ 已完成

**痛点**: `print_welcome` 用 `box=None` 的无边框表格列出命令，信息量大但毫无设计感。

**方案**:
- 用 `rich.Columns` 或卡片布局分组命令（核心命令、文件操作、会话管理等）
- 用 dim 色减少视觉噪音，关键字用 bold/color 突出
- 启动时显示最近会话列表（快速 `/load`）

**涉及文件**: `neow/utils/formatter.py`（`print_welcome`）。

---

## 改进点 7：行内 Diff 展示不足 ✅ 已完成

**痛点**: `print_diff` 只用了 `Syntax(diff_text, "diff", theme="monokai")`，是全量 diff，没有 inline diff。

**方案**:
- 用 `rich.Syntax` 的 inline styles 功能标记增删行背景色
- 或者用 `rich.table.Table` 两列对比 before/after

**涉及文件**: `neow/utils/formatter.py`（`print_diff`, `format_diff`）。

---

## 改进点 8：Code Block 高亮语言总是 monokai ✅ 已完成

**痛点**: 代码片段高亮统一用 monokai，且没有自动检测语言。

**方案**: 检测 markdown 中代码块的语言标识（```python, ```bash 等），用对应语言高亮显示。

**涉及文件**: `neow/utils/formatter.py`。

---

## 改进点 9：移动端/窄终端体验差 ✅ 已完成

**痛点**: 很多 Panel 内容长，在 80 列终端下会 wrap 得很惨。

**方案**: 检测终端宽度，窄终端时自动降低信息密度（缩短参数预览、隐藏次要信息）。

**涉及文件**: `neow/utils/formatter.py`，`neow/cli/repl.py`。

---

## 实施顺序与完成状态

按视觉收益 / 改动成本比排序，全部 9 个改进点已按此顺序落地：

1. **点 1** — 流式 Panel 包裹（最高优先级，体验提升最大）✅ 已完成
2. **点 2** — 色彩主题系统 ✅ 已完成
3. **点 3** — 时间戳/消息编号 ✅ 已完成
4. **点 6** — 欢迎页重设计 ✅ 已完成
5. **点 4** — Tool Call 折叠 ✅ 已完成
6. **点 8** — Code Block 语言高亮 ✅ 已完成
7. **点 7** — 行内 Diff ✅ 已完成
8. **点 5** — 非交互模式 spinner ✅ 已完成
9. **点 9** — 窄终端适配 ✅ 已完成

---

## 后续可选扩展

以下未纳入本次 9 个改进点，作为未来可选方向记录：

- **Aider Repo Map** — 用 tree-sitter 生成项目结构摘要（Windows 兼容性问题，暂缓）
- **语音输入** — Aider 已有，Neow 未吸收
- **浏览器 GUI** — Aider 用 Streamlit，Neow 保持纯终端路线
- **多模型 metadata 管理** — OpenRouter 集成等
