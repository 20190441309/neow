# Neow TUI 设计规格（v1）

- 日期：2026-10-07
- 状态：对话内设计已获用户批准（"全部按照你推荐的来"）；本文件待用户书面审查
- 范围：Neow 全屏 TUI 的信息架构、卡片体系、动效、交互、视觉、技术与验收标准
- 关联材料：
  - 调研笔记：`docs/research/tui-references.md`
  - 可行性 demo：`docs/research/tui-feasibility/demo.py`（FEASIBILITY OK）
  - 设计稿：`docs/research/tui-feasibility/design_mockup.py` + `screenshots/01-main.png`、`02-sidebar.png`、`03-approval.png`、`04-splash.png`

---

## 1. 背景与目标

Neow 目前是 Rich + prompt-toolkit 的行式 REPL（`neow/cli/repl.py` 1278 行、`neow/utils/formatter.py` 988 行），核心层（conversation / executor / approval / session tree / token tracker / plugin / tools）已完整，443 个测试在保。

本设计将交互层升级为全屏 TUI：

- 默认入口 `neow` 进入全屏 TUI；`neow --plain` 保留现有 REPL；`neow "prompt"` 一次性模式与管道行为不变。
- 形态为 **Warp 式卡片时间线**（单列、可折叠卡片、垂直流式滚动）。
- 动效以 **crush 式「乱码闪动」thinking** 为核心记忆点，配渐变 ASCII 启动动画、流式光标、状态过渡。
- **core 业务语义零改动**，现有 443 个测试零回归。

## 2. 范围

**In scope（v1 交付）**

- `neow/tui/` 全屏界面包（App、Screens、Widgets、Effects、Bridge、TCSS 主题）。
- CLI 入口分流：`neow`（TUI）/ `neow --plain`（REPL）/ `neow --tui`（强制）。
- Thinking scramble、启动 logo、卡片入场、工具状态过渡、审批模态脉冲。
- 27 个 `/命令` 在 TUI 中的完整去路（内联执行或独立 Screen）。
- 审批流、任务取消、消息排队、会话持久化、token/成本/上下文展示的 TUI 呈现。
- `tests/tui/` 测试、README 文档更新。

**Out of scope（v1 不做）**

- 修改模型客户端、工具实现、权限语义、会话存储格式。
- 删除或重写现有 REPL / formatter（保留给 `--plain`）。
- Web GUI、多主题市场、亮色主题（主题 token 预留，v1 只出 `midnight`）。
- 会话树/分支的新算法（只做现有能力的界面化）。
- 远程推送、CI 配置。

## 3. 已确认的设计决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 布局形态 | **A. Neon Timeline**：单列卡片时间线 + 1 行顶栏 + 底部输入坞 + 状态栏；右侧栏（42 列）由 `Tab` 切换，默认隐藏。否决 B 常驻驾驶舱（挤压对话宽度）、C 无框极简流（工具卡状态可读性弱） |
| 2 | Thinking 展示 | **V2**：实时显示 reasoning 文本，最前沿 32 字符持续乱码翻滚，`reasoning_end` 时落定并自动折叠为 `✻ Thought Ns · M 字 [▸]`。否决 V1 纯乱码状态条（看不到思考过程） |
| 3 | Tool 卡完成态 | 运行中展开；**完成后自动折叠**为标题行；`error` / `denied` 保持展开；用户在同一卡上手动展开后，本卡不再自动折叠 |
| 4 | 生成中发消息 | **排队**：当前回合结束后自动发送；排队条显示 `⏳ 排队 N`；输入框为空时按 `↑` 取回最后一条排队消息编辑；`Esc` 取消当前生成，队列保留并继续 |

## 4. 信息架构与布局

### 4.1 主界面（ChatScreen）

```
┌ TopBar (1 行) ────────────────────────────────────────────────┐
│ ◆ NEOW · {model} · ⎇ {branch}{dirty} · ⛨ {approval_mode} · cwd │
├ Body (1fr) ────────────────────────────────────────────────────┤
│ ┌ TimelineScroll ─────────────────────┐ ┌ Sidebar (可选, 42列) ┐ │
│ │ [UserCard]                          │ │ CONTEXT · N files    │ │
│ │ [ThinkingCard]                      │ │ SESSION TREE         │ │
│ │ [AssistantCard + 流式光标]           │ │ GIT                  │ │
│ │ [ToolCard ×N]                       │ │                      │ │
│ │ …                                   │ │                      │ │
│ └─────────────────────────────────────┘ └──────────────────────┘ │
├ QueueStrip (仅排队时 1 行) ────────────────────────────────────┤
│ ⏳ 排队 1 · ↑ 取回                                              │
├ InputDock (1–6 行, 随内容增长) ────────────────────────────────┤
│ ❯ {多行输入}                                                     │
│ Enter 发送 · Ctrl+J 换行 · @ 文件 · / 命令 · Esc 中断            │
├ StatusBar (1 行) ──────────────────────────────────────────────┤
│ ▲in ▼out · $cost · ctx N% · ⏱elapsed    [✻ thinking|⟳ tool|idle]│
└────────────────────────────────────────────────────────────────┘
```

### 4.2 区域职责

- **TopBar**：logo 标记（生成中变为活动色）、模型名、git 分支（`*` 表示脏）、审批模式、会话名、缩写 cwd。不可折叠。
- **TimelineScroll**：卡片时间线，唯一滚动容器。吸附规则：用户停留在底部时自动跟随新内容；用户上滚后停止吸附，出现 `↓ 新消息 (N)` chip，点击或按 `End` 回到底部。
- **Sidebar**：三页签（`Ctrl+T` 循环）——CONTEXT（上下文文件列表，`/add`、`/drop` 提示）、SESSION TREE（当前会话树形，`/tree` 的全屏版之外的内联版）、GIT（`git status` 摘要 + 最近 3 条 auto-commit）。宽度 42；`Tab` 开合。
- **QueueStrip**：仅当队列非空显示；`↑` 取回最后一条。
- **InputDock**：多行输入（`TextArea`），高度 1–6 行内自适应，超出后内部滚动。提示行常驻。
- **StatusBar**：左半区 token/成本/上下文/计时；右半区当前状态（`✻ thinking` / `⟳ {tool}` / `⏸ approval` / `idle`）与快捷提示。

### 4.3 终端宽度断点

| 宽度 | 行为 |
|------|------|
| ≥ 110 列 | 全部功能；时间线内容最大宽度 140 居中；侧栏 42 列 |
| 88–109 列 | 侧栏 36 列；Tool 卡标题 meta 超长省略 |
| 72–87 列 | 侧栏禁用（`Tab` 弹 toast「终端宽度不足」）；卡片时间/编号保留，meta 省略；工具摘要截断 30 字符 |
| < 72 列 | 紧凑模式：隐藏输入提示行第二行、隐藏 StatusBar 右侧提示、卡片 padding 减半；功能不缺失 |

## 5. 卡片体系

### 5.1 通用规则

- 卡片 = `surface #0f1117` 背景 + 左侧 1 列 heavy 色条 + 上下间距 1 行；无圆角边框（只有模态有边框）。
- 标题行：`{图标} {名称}` + `#{n}`（回合/消息编号，沿用现有 formatter 的编号语义）+ `· {时间}`；右侧 meta（耗时、`+N -M`）在宽度允许时右对齐。
- 每张卡可折叠；折叠状态存于卡片实例（不持久化）；`Ctrl+O` 折叠/展开当前聚焦卡。
- 长正文截断：默认显示前 20 行，尾部提示 `… (+N 行，Ctrl+O 展开)`；展开后正文区最大高度 30 行，内部滚动；`/verbose` 全局展开所有卡。

### 5.2 卡片类型

| 卡片 | 数据来源 | 色条 | 初始状态 | 说明 |
|------|---------|------|---------|------|
| **UserCard** | 用户提交 | 青 `#22d3ee` | 展开 | 保留换行；图片附件显示 `[img N]` chip |
| **ThinkingCard** | `reasoning_start/delta/end` | 锌灰 `#52525b` | 展开 | 详见 5.3；无 reasoning 的模型退化为状态行卡片 |
| **AssistantCard** | `content_delta` | 紫 `#a78bfa` | 展开 | Markdown 流式；代码块语法高亮；流式光标 `▊` |
| **ToolCard** | `progress.tool_start/tool_end` | 黄 `#facc15`（运行）→ 绿 `#34d399`（成功）/ 红 `#f87171`（失败）/ 红（拒绝） | 展开 | 详见 5.4 |
| **ErrorCard** | 工具异常、模型错误、安全拦截 | 红 `#f87171` | 展开 | 标题 `✗ {类型} · {摘要}`；正文错误详情 |
| **SystemCard** | lint/test 反馈、插件事件、审批拒绝信息 | 蓝 `#38bdf8`；warn 变体黄 | 展开 | 短消息直接标题行承载 |
| **CompactionCard** | auto-compact / `/compact` | 蓝 `#38bdf8` | 折叠 | 标题 `◈ Context Compacted · 18 messages → summary · -12.4k tokens` |

### 5.3 ThinkingCard 规格

- **进行中（scrambling）**：
  - 标题：`✻ Thinking · {elapsed:.1f}s · {chars} 字`，图标做 10fps 闪烁（`✻`/`✧` 交替）。
  - 正文：已到文本以 dim 灰 `#71717a` 正常显示；最前沿 32 字符（<110 列时 20 字符）每帧替换为随机字符，字符集 `0123456789abcdefABCDEF~!@#$%^&*()+=_`，随机字符按位置取渐变相位色（20fps）。
  - 每帧只重绘正文一行（Textual `Static.update`，只更新该卡）。
- **落定（settled）**：`reasoning_end` 后 300ms 内前沿乱码加速收敛为正文；卡片自动折叠为 `✻ Thought {duration:.1f}s · {chars} 字 [▸]`。
- **空 reasoning 模型**：显示状态行 `✻ Working · {当前活动}`（如 `⟳ execute_command`），附带 12 字符乱码条；不显示正文。
- **effects 降级**（见 §6.4）：`subtle` 时乱码条换成 10fps 旋转符 `⠋⠙⠹…`，正文仍实时 dim 显示；`off` 时无动画，纯 dim 文本。

### 5.4 ToolCard 规格

- **标题行**：`{状态图标} {tool_name} · {摘要} · {duration} · {+N -M}`。
  - 状态图标：`⟳`（运行，braille 动画）/ `✓`（成功）/ `✗`（失败）/ `⛔`（被拒绝）。
- **状态机**：`running` → `done` | `error` | `denied`。`running` 强制展开；`done` 自动折叠（决策 3）；`error`/`denied` 保持展开。
- **工具正文渲染器**：

| 工具 | 正文 |
|------|------|
| `read_file` | 路径 + 行数 + 前 5 行预览 |
| `write_file` / `create_file` / `delete_file` | 文件路径 + 行数变化 + 内容首 10 行（新建） |
| `edit_file` / `hashline_edit` | 行内 diff（`+` 绿底 / `-` 红底，复用 `formatter._colorize_diff_lines` 的着色逻辑）+ 锚点 hash 前缀 |
| `execute_command` | `$ {command}` + 输出尾部 20 行 + exit code；超时/失败红色 |
| `search_code` | pattern + 命中数 + 前 5 条 `path:line` |
| `lint` / `test` | 通过/失败统计 + 失败用例前 3 条 |
| `web` / GitHub | 标题 + URL + 摘要首 2 行 |
| `git_*` | 操作摘要（分支、commit hash、文件数） |

- 结果截断：进度事件里 `result[:500]` 保持现状；展开正文优先用完整结果（controller 可从工具层拿到完整返回值时缓存），取不到则显示 500 字上限并提示「完整输出见 --plain 或日志」。

### 5.5 回合组织

- 一个用户回合内，多个 assistant 内容段共享同一 `#{n}` 编号（沿用现有语义）；`ThinkingCard`、`ToolCard` 按事件顺序穿插在 assistant 段之间。
- 回合一结束（无 tool_call 且流结束）：最后一张 AssistantCard 追加 meta（耗时、tokens）。

## 6. 动效系统

### 6.1 参数表

| 动效 | 参数 | 触发/结束 |
|------|------|----------|
| Thinking scramble | 20fps；前沿 32 字（窄屏 20）；字符集 `0-9a-fA-F~!@#$%^&*()+=_`；渐变相位 0.05/帧；落定 300ms | `reasoning_start` → `reasoning_end` |
| 启动 logo | 12fps；渐变相位 0.02/帧；连接成功后停留 600ms 收起为 TopBar 标记；任意按键跳过 | App 启动 |
| 流式光标 | `▊` 以 1.5s 周期做透明度/颜色脉冲（10fps） | `content_delta` 流期间 |
| 卡片入场 | opacity 0→1 + offset-x −1→0，120ms ease-out | 新卡挂载 |
| 工具 spinner | braille 帧 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`，10fps | ToolCard `running` |
| 完成闪烁 | 左色条颜色 150ms 过渡到语义色（绿/红） | ToolCard 状态落定 |
| 审批脉冲 | 模态边框黄↔暗黄，800ms 循环 | ApprovalModal 打开期间 |

### 6.2 性能预算

- 全屏动效合计 ≤ 20fps；每张活动卡各自最多 1 个 `set_interval`。
- 非活动卡不挂定时器；离开视口或回合结束后立即停止（可恢复）。
- `content_delta` 合并刷新：controller 以 50ms 窗口聚合，UI 侧批量 `Markdown.append`。
- 内存：reasoning/工具输出全量保留在当前会话内；CompactionCard 后随会话压缩自然释放。

### 6.3 渲染纪律（实现注意）

- 禁止定义 `Widget._render()`（Textual 内部方法，覆盖会导致布局崩溃）；自定义渲染函数命名 `_frame()` 等。
- 渐变取色用 `Gradient.get_color(t).hex` 传给 Rich Text；`Color.rich_color` 是 Rich 对象，会导致 `AttributeError`。

### 6.4 降级模式

配置 `tui.effects`（默认 `full`）：

- `full`：全部动效。
- `subtle`：无启动 logo（直接进主界面）、无卡片入场、无渐变散射；scramble 换 spinner 条；其余保留。
- `off`：静态界面，保留颜色与折叠等无动画交互。

环境变量 `TEXTUAL_ANIMATIONS=none` 或非 TTY 输出时强制 `off`。`--plain` 不加载 TUI。

## 7. 交互模型

### 7.1 键位表

| 按键 | 行为 |
|------|------|
| `Enter` | 发送；生成中则加入队列 |
| `Ctrl+J` / `Shift+Enter` | 输入框内换行 |
| `Esc` | 关闭浮层；无浮层时中断当前生成（见 7.4） |
| `Ctrl+C` | 生成中=中断；空闲时双击（1.5s 内两次）退出 |
| `Ctrl+Q` | 退出（生成中先弹确认） |
| `Ctrl+P` | 命令面板 |
| `/` | 行首触发命令内联菜单（过滤 + Enter 执行） |
| `@` | 触发文件补全（插入相对路径） |
| `↑` / `↓` | 光标在首/末行时切换历史；输入为空时 `↑` 取回最后一条排队消息 |
| `PgUp` / `PgDn` / `Home` / `End` | 时间线滚动；`End` 恢复吸附底部 |
| `Ctrl+↑` / `Ctrl+↓` | 移动卡片焦点（最近活动卡为默认焦点） |
| `Ctrl+O` | 折叠/展开焦点卡 |
| `Tab` | 开合侧栏 |
| `Ctrl+T` | 侧栏页签循环（CONTEXT → SESSION TREE → GIT） |
| `F1` | 帮助屏（同 `/help`） |
| `Ctrl+Y` | 复制最后一个代码块（OSC52；不支持时 toast 提示） |
| 鼠标 | 点击折叠/聚焦、文本选择、滚动 |

### 7.2 输入与补全

- 输入框跟随内容增长（1–6 行），超出内部滚动。
- 历史复用现有 `.neow_history`（`FileHistory` 同路径），写入行为与 REPL 一致。
- `/` 菜单展示全部 27 个命令及描述，支持前缀/模糊过滤；`Tab` 补全不执行，`Enter` 执行。
- `@` 补全扫描 cwd 文件（复用 `neow/tools/search.py` 的 `SKIP_DIRS`，排除 `.git`、`__pycache__`、`node_modules`），支持前缀过滤，最多显示 20 条。
- 排队：`QueueStrip` 显示条数；排队消息按 FIFO 顺序在回合结束后自动发送；图片 chip 通过 `/image <path>` 添加，附加到下一条待发消息。

### 7.3 命令与 Screen 映射

| 命令 | TUI 去路 |
|------|---------|
| `/help` | HelpScreen（命令表 + 键位表） |
| `/model` | ModelPicker Screen（配置内模型列表，Enter 切换；复用现有切换逻辑与历史保留策略） |
| `/history` `/load` | SessionPicker Screen（日期/消息数/大小；Enter 载入） |
| `/tree` `/branch` | SessionTreeScreen（现有 `SessionManager.session_tree/load_tree` 数据；Enter 导航，`b` 分叉） |
| `/diff` `/commit` `/undo` | DiffScreen（`git_diff/commit/undo`；`c` 提交需输入 message，`u` 回退需确认） |
| `/cost` | CostScreen（按模型列出输入/输出与费用） |
| `/approval` | ApprovalPicker（模式三选 + 工具覆盖列表） |
| `/clear` | 确认模态后清空会话历史（保留上下文文件） |
| `/save` | 输入框前缀交互：`/save [name]` 直接执行，无 name 时生成默认名 |
| `/add` `/drop` `/ls` `/web` `/compact` `/export` `/image` `/lint` `/test` `/think` `/code` `/architect` `/verbose` `/exit` | 时间线内联执行，结果以 SystemCard/ToolCard/CompactionCard 呈现 |

命令面板（`Ctrl+P`）同时提供全部命令与 UI 动作者（切换侧栏、effects 模式）。

### 7.4 生成控制

- 发送后进入 `busy` 状态；StatusBar 显示当前活动。
- `Esc`：置 cancel flag → controller 停止消费 stream 并 `close()`；正在执行的本地工具等待其结束后停止（写操作不半途中断），SystemCard 提示「已中断（当前工具执行完成后停止）」。
- 中断后队列中的消息继续按序发送。
- 审批模态打开时，生成线程阻塞等待，StatusBar 显示 `⏸ approval`。

### 7.5 审批流

- 模态展示：工具名、tier、参数摘要（截断 200 字，可展开）、原因、危险标记。
- 按键：`y` 允许一次；`a` 本会话总是允许（调用现有 `ApprovalPolicy.set_tool_override(tool, "allow")`）；`n` / `Esc` 拒绝。
- 拒绝：抛回 `ToolError("User denied: …")`，工具结果走 error 路径，ToolCard 显示 `⛔`。
- 退出应用或超时（应用退出路径）时按拒绝处理，绝不阻塞进程退出。
- 审批桥在 worker 线程阻塞、UI 线程弹窗；`Future` + `call_from_thread` 实现，禁止在 worker 线程直接操作 UI。

## 8. 视觉系统

### 8.1 调色板（token）

| token | 值 | 用途 |
|-------|-----|------|
| `bg` | `#0b0d12` | 屏幕背景 |
| `surface` | `#0f1117` | 卡片/顶栏/状态栏背景 |
| `elevated` | `#151a23` | hover/选中 |
| `border` | `#1e293b` / `#334155` | 分隔线/卡片未激活色条 |
| `text` | `#e5e7eb` | 正文 |
| `dim` | `#94a3b8` | 次要文字 |
| `muted` | `#64748b` | meta/提示 |
| `accent-1..4` | `#22d3ee` `#a78bfa` `#f472b6` `#facc15` | 渐变、角色色、强调 |
| `success` | `#34d399` | 成功/新增 |
| `error` | `#f87171` | 失败/删除 |
| `warn` | `#facc15` | 警告/审批 |
| `info` | `#38bdf8` | 系统信息 |

### 8.2 字形与排版

- 默认字形集（无需 Nerd Font）：`◆ ● ✻ ✧ ⟳ ✓ ✗ ⛔ ◈ ⎇ ❯ ⏳ ▊ ↑↓⠋⠙` 等；对可能缺字形的 `⛨` 提供回退 `🛡`/`!`。
- emoji 不作为唯一语义载体（对齐问题），配置项 `tui.emoji` 预留，v1 默认关闭。
- 卡片内 padding：`0 2`（窄屏 `0 1`）；卡片间距 1 行；标题 bold，正文常规。
- 代码高亮沿用 Rich 语法主题，映射到上述调色板。

### 8.3 主题

- v1 只提供 `midnight`；所有颜色收敛在 `neow/tui/theme.tcss` 的 CSS 变量中。
- 配置 `tui.theme` 预留，未知值回退 `midnight` 并警告。

## 9. 技术架构

### 9.1 模块结构

```
neow/tui/
  __init__.py
  app.py                  # NeowApp：Screen 栈、主题、全局键位、命令面板接入
  theme.tcss
  screens/
    chat.py               # ChatScreen：TopBar + Timeline + Sidebar + Queue + Input + Status
    help.py               # HelpScreen
    model_picker.py       # ModelPicker
    session_picker.py     # SessionPicker
    tree.py               # SessionTreeScreen
    diff_view.py          # DiffScreen（diff/commit/undo）
    cost.py               # CostScreen
    approval.py           # ApprovalModal（ModalScreen）
  widgets/
    timeline.py           # TimelineScroll：卡片追加、吸附、焦点卡
    input_dock.py         # TextArea + 补全菜单 + 历史 + 排队条
    status_bar.py
    logo.py
    cards/
      base.py             # CardBase：标题行/折叠/状态色条/入场动画
      user.py assistant.py thinking.py tool.py system.py error.py compaction.py
  effects/
    scramble.py           # 乱码引擎（可测、可 seed）
    gradient.py           # 渐变 Rich Text 构建
  bridge/
    events.py             # TurnStarted/ReasoningDelta/ContentDelta/ToolStart/ToolEnd/TurnEnd/…
    controller.py         # ChatController：跑 stream、事件投递、取消、审批桥
```

### 9.2 线程模型

- UI 主线程：Textual App；只有 UI 线程操作 widget。
- 生成线程：`ChatScreen` 用 `@work(thread=True)` 调 `ChatController.run_stream(user_input)`；controller 逐 chunk 生成事件，经 `call_from_thread` / 消息队列投递到对应卡片方法。
- 刷新合并：controller 侧 50ms 聚合 delta；UI 侧只更新受影响卡片，禁止整树重排。
- 关闭顺序：先停生成线程（cancel + join 超时 3s），再关 App，避免僵尸线程。

### 9.3 审批桥

```
worker 线程                                UI 线程
prompt_user_approval(tool, params, reason)
  future = Future()
  app.call_from_thread(show_modal, future) ──► push ApprovalModal
  return future.result()   ◄────────────────── modal 按键 set_result(bool)
```

- `future.result(timeout=600)`；超时按拒绝并提示。
- App 退出时 `future.cancel()`；worker 捕获 `CancelledError` 走拒绝分支。
- 该桥与现有 `executor.approval_callback` 签名 `(str, dict, str) -> bool` 完全兼容，core 零改动。

### 9.4 取消

- `ChatController.cancel()` 置 `threading.Event`；`run_stream` 在 chunk 边界检查并 `stream.close()`。
- 工具执行不可中断（原子性保证）；前端提示「当前工具结束后停止」。
- 取消后 `TurnEnd(cancelled=True)`，卡片补 meta。

### 9.5 错误处理

- 模型/网络错误：ErrorCard + StatusBar 红色状态；会话保持可继续（沿用现有异常语义）。
- 工具错误：ToolCard `✗` + 错误正文（现有 `ToolError` 文案不变）。
- 组件级异常：Textual 错误边界捕获后 toast + 日志 `~/.neow/neow.log`；主流程不崩溃。
- 致命错误（配置缺失、连接失败）：TUI 内 ErrorCard + 退出码 1；`--plain` 保持现有 stderr 行为。

### 9.6 配置新增

```json
{
  "tui": {
    "effects": "full",
    "sidebar_default": false,
    "theme": "midnight"
  }
}
```

- 未知/非法值回退默认并 warning；`--plain` 忽略 `tui` 段。
- 非 TTY 或管道输入强制 `--plain` 路径，不实例化 App。

### 9.7 依赖

- `pyproject.toml` 新增 `textual>=8.0,<9`（当前验证版本 8.2.8）。
- 不新增其他运行时依赖；测试沿用 pytest + pytest-asyncio（Textual `run_test` 自带 async 支持）。

## 10. 入口与兼容

| 场景 | 行为 |
|------|------|
| `neow`（TTY，无 prompt） | 启动 TUI（默认） |
| `neow --plain` | 现有 REPL |
| `neow --tui` | 强制 TUI；非 TTY 时 stderr 报错退出码 2 |
| `neow "prompt"` | 一次性非交互（不变） |
| `neow --file f`（TTY） | TUI，文件加入上下文 |
| stdin 管道 | 非交互（不变），强制 plain 渲染 |
| stdout 非 TTY | 强制 plain 路径 |
| `--message-file` | 不变（非交互） |
| textual 导入失败 | 警告 + 自动回退 REPL（`--plain` 语义） |

- REPL、formatter、现有命令行为全部保留，作为兼容路径。
- core（models/tools/core）不做语义修改；仅 `neow/cli/main.py` 增加分流与审批接线。

## 11. 测试与验收

### 11.1 测试层级

| 层级 | 文件 | 覆盖 |
|------|------|------|
| 效果引擎 | `tests/tui/test_effects.py` | scramble 确定性（seed）、落定、渐变端点色；禁用模式不启动定时器 |
| 卡片 widget | `tests/tui/test_cards.py` | Pilot：折叠/展开、状态色、截断、排队/追加内容 |
| 审批模态 | `tests/tui/test_approval_modal.py` | `y/a/n/Esc` 返回值；`a` 更新 ApprovalPolicy override；超时/退出按拒绝 |
| 输入坞 | `tests/tui/test_input_dock.py` | `/` 与 `@` 补全、历史、排队发送与取回 |
| Controller | `tests/tui/test_controller.py` | fake stream 事件序列（reasoning→assistant→tool→assistant）、cancel、50ms 聚合 |
| 入口决策 | `tests/tui/test_entry.py` | 纯函数：给定 TTY/prompt/管道/flags 返回 TUI/PLAIN/ONESHOT |
| 回归 | 现有套件 | 443 个测试全绿 |
| PTY 冒烟 | `tests/tui/pty_smoke.py`（非默认标记） | 于真实 pty 依次启动/退出 `neow`、`neow --plain`、`neow "hi"`（stub 模型客户端） |

### 11.2 验收门（全部满足才可标记完成）

1. `pytest`：现有 443 + 新增 TUI 测试 0 失败。
2. `black --check .` 通过。
3. PTY 冒烟：三入口启动/退出正常，TUI 默认生效、`--plain` 行为与改动前一致。
4. 对照本规格 §4–§10 逐条核对并留证（截图/命令输出）。
5. 真实会话手工验证：thinking 乱码动效、流式渲染、工具折叠、审批弹窗、`/diff`、中断、排队。
6. 非 TTY/管道路径不加载 TUI。

## 12. 里程碑映射

| 任务 | 内容 | 对应规格 |
|------|------|---------|
| t5 | TUI 骨架与入口改造 | §4.2、§9.1–9.2、§9.6–9.7、§10 |
| t6 | 卡片时间线核心 | §5、§6.1–6.3、§7.4 |
| t7 | 外围交互 | §4.2 Sidebar、§7.1–7.3、§7.5 |
| t8 | 主题、启动动画与性能打磨 | §6、§8 |
| t9 | 测试补齐、全量回归与 README | §11、§10 |
| t10 | 验收与代码审查 | §11.2 |

## 13. 风险与缓解

| 风险 | 缓解 |
|------|------|
| Markdown 流式重排造成卡顿 | 50ms 聚合 + 只更新可见卡 + 20fps 上限（§6.2） |
| 审批桥死锁/阻塞退出 | Future 超时 + 退出 cancel + 拒绝兜底（§9.3） |
| Textual 8.x API 变动 | 版本钉 `>=8,<9`；渲染纪律单测覆盖（§6.3、§9.7） |
| Windows/非 UTF-8 终端字形 | 安全字形集 + 回退映射（§8.2），Textual 跨平台 |
| 现有测试被入口改造破坏 | 分流逻辑纯函数化 + 回归套件门禁（§11.1–11.2） |
| 剪贴板/OSC52 不被支持 | 支持性检测 + toast 降级，不阻断（§7.1） |

## 14. 未决问题

无。本规格所有行为均已定值；实现中发现的新歧义需回到本文件更新并经用户确认。
