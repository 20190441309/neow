# Neow CLI 开发路线图

> 目标：对标 Aider，逐步构建专业的 AI 结对编程工具
> 当前覆盖率：以 CI（ubuntu + windows）上 `pytest` 的实际结果为准 | P0–P5 已完成（v0.9）

---

## P0 - 核心差距（最高优先级）

### 1. Git 集成 ✅
Aider 的灵魂功能，也是 Neow 最大的短板。

- [x] 新增 `neow/tools/git.py`，封装 git 操作
- [x] `/diff` — 显示当前会话中 AI 做出的所有改动
- [x] `/commit` — AI 生成 commit message 并提交
- [x] 自动 commit — 每次文件编辑后自动创建原子提交
- [x] `/undo` — 回退上一次 AI 的commit
- [x] 分支感知 — 了解当前分支，在 system prompt 中注入分支信息
- [ ] ~~Repo Map — 用 tree-sitter 生成项目结构摘要，注入上下文~~ **暂缓：tree-sitter 依赖在 Windows 兼容性差，当前 ContextManager + search/grep 工具已够用，等有大型 monorepo 需求再做**

### 2. Streaming 流式输出 ✅
当前响应是等全部生成完才显示，体验差。

- [x] DeepSeek client 改为 `stream=True`
- [x] OpenAI client 改为 `stream=True`
- [x] Anthropic client 改为 `stream=True`
- [x] REPL 中逐 token 打印，带打字机效果
- [x] 流式输出中正确处理 tool_calls 的增量拼接

### 3. 文件上下文管理 ✅
让 AI 精确知道哪些文件在上下文中。

- [x] `/add <file>` — 将文件加入会话上下文
- [x] `/drop <file>` — 将文件从上下文移除
- [x] `/ls` — 列出当前上下文中的所有文件
- [x] 上下文文件内容自动注入 system prompt
- [x] 文件变更后自动更新上下文中的内容

### 4. edit_file 精准化 ✅
当前 `str.replace()` 替换所有匹配，容易出错。

- [x] 支持基于行号范围的编辑（start_line, end_line）
- [x] 支持只替换第 N 次匹配（first_only 参数）
- [x] 编辑前自动备份原文件（配合 Git 集成）
- [x] 添加 `create_file` 工具（区分创建和覆盖）
- [x] 添加 `delete_file` 工具

---

## P1 - 专业能力

### 5. 项目理解（启用 ContextManager） ✅
`ContextManager` 已接入主流程。

- [x] 在 `main.py` 中初始化 ContextManager
- [x] 会话开始时自动注入项目结构摘要
- [x] 用户提问时自动匹配相关文件
- [ ] ~~引入 tree-sitter 做 AST 级别的代码理解~~ **暂缓**（同上）
- [ ] ~~生成 Repo Map（函数/类/方法索引）~~ **暂缓**（同上）

### 6. Architect 模式 ✅
规划与执行分离，复杂任务效果更好。

- [x] `/architect` 命令切换到架构师模式
- [x] 用强模型（如 Claude）做规划
- [x] 用快模型（如 DeepSeek）做代码编辑
- [x] 规划阶段只读不写，确认后再执行

### 7. 自动 Lint & Test ✅
编辑后自动验证代码质量。

- [x] `/lint` — 运行项目 linter，结果反馈给 AI 修复
- [x] `/test` — 运行测试套件，失败时自动让 AI 修复
- [x] `--auto-lint` 配置项 — 每次编辑后自动 lint
- [x] `--auto-test` 配置项 — 每次编辑后自动测试
- [x] 自动检测项目语言，选择对应 linter

### 8. 运行时模型切换 ✅
`/model` 命令已实现真实切换。

- [x] 实现 `/model <name>` 真正切换模型
- [x] 切换时保持会话历史（或提示是否保留）
- [x] `/model` 无参数时显示当前模型和可用模型列表
- [x] 支持快捷别名（`/model sonnet`, `/model deep`）

---

## P2 - 体验优化

### 9. 会话持久化
退出后对话丢失。

- [x] 会话自动保存到 `~/.neow/sessions/`
- [x] `/save [name]` — 命名保存当前会话
- [x] `/load <name>` — 恢复历史会话
- [x] `/history` — 列出历史会话

### 10. Token 用量与成本展示
usage 数据已解析但未展示。

- [x] 每次回复后显示 token 用量（input/output）
- [x] `/cost` — 显示本次会话累计消耗
- [x] 支持设置 token 上限告警
- [x] 不同模型的单价配置

### 11. 安全加固
安全规则目前仅靠 prompt 约束。

- [x] `allowed_commands` 白名单真正生效（`;`/`&&`/`||`/`|`/`&` 链式命令逐段校验白名单，`$(...)`/反引号命令替换直接拒绝；默认白名单含 `python`/`npm` 时两者本身仍能任意执行代码，白名单管不了解释器内部行为，见 `neow/core/security.py`）
- [x] 危险命令（`rm -rf`, `drop table` 等需二次确认）
- [x] 文件写入前确认（可配置）
- [x] 敏感文件保护（`.env`, `id_rsa` 等默认不可读写）

### 12. 命令行增强
补充常用 CLI 功能。

- [x] `neow <prompt>` — 非交互模式，直接执行一次对话
- [x] `neow --file <path>` — 指定文件自动加入上下文
- [x] `neow --message-file <path>` — 从文件读取 prompt
- [x] 支持 pipe 输入：`cat error.log | neow "分析这个错误"`

---

## P3 - 锦上添花



### 13. Web 上下文
- [x] `/web <url>` — 抓取网页内容加入上下文
- [x] 支持自动提取代码片段
- [x] 支持 GitHub issue/PR 链接自动解析


### 14. 插件系统
- [x] 自定义工具注册机制
- [x] 用户可编写插件扩展功能
- [x] 插件目录自动发现

---

## 已知问题（需修复）

- [x] `ContextManager` 代码已写好但从未接入主流程（已修复：已接入主流程）
- [x] `grep_code()` 已定义但未注册为工具（已修复：已注册）
- [x] `allowed_commands` 配置已定义但未执行检查（已修复：SecurityGuard 已执行检查）
- [x] `edit_file` 替换所有匹配而非第一个（已修复：新增 first_only 参数）
- [x] `/model` 命令仅打印消息，未真正切换（已修复：实现真实切换）
- [x] `event_bus`/`conversation` 在闭包中引用但创建在回调之后（已修复：重排 main.py 初始化顺序）
- [x] 非交互模式跳过 plugin/event_bus 初始化（已修复：plugin 系统移至统一初始化区）
- [x] `pending_lint_feedback` 重复赋值 + auto_lint/auto_test 反馈互相覆盖（已修复：累加合并）
- [x] `ToolExecutor.get_tool_definitions()` 永远返回空列表（已修复：委托给 prompts.get_tool_definitions）
- [x] DeepSeek `_last_reasoning_content` 泄漏到消息历史（已修复：不再注入 reasoning_content 到 API 消息）
- [x] Session restore 不恢复 `web_cache`（已修复：保存/恢复 web_cache + 重置 _structure_injected）
- [x] `compact()` 未防止 summarizer 返回 tool_calls（已修复：添加 guard + warning）
- [x] `search_code` 未排除 `.git`/`__pycache__`/`node_modules`（已修复：SKIP_DIRS 过滤）
- [x] `_sanitize_text` 在 4 个文件中重复定义（已修复：提取到 `neow.utils.sanitize_text`）
- [x] **Windows：headless 模式（`neow -p` / `--output-format`）关闭真实 `sys.stdout`**（已修复：`neow/utils/formatter.py` 不再把 `sys.stdout.buffer` 包进额外的 `TextIOWrapper`，改用 `sys.stdout.reconfigure(encoding="utf-8")`。旧写法下 `console.file = sys.stderr` 会丢掉 wrapper 的最后一个引用，`TextIOWrapper.__del__` 随即关掉真实 stdout——`sys.stdout.isatty()` 当场抛 `ValueError`，headless 直接崩；测试侧表现为 `tests/test_evals.py` 后 1173 个 error 级联。回归测试：`tests/test_headless.py::test_headless_keeps_stdout_open`）
- [x] **Windows：`read_piped_stdin` 在"管道开着但没人写"时永久挂死**（已修复：`neow/cli/main.py` 不再假定"select 失败 = 就绪"，改用 `PeekNamedPipe` 轮询管道、`stat.S_ISREG` 识别重定向文件，超时返回空串。旧代码在 Windows 上 `select()` 必抛 `OSError`，随后 `stream.read()` 死等——正是该函数声称要防的场景。回归测试：`tests/test_headless.py::test_piped_stdin_never_hangs`（此前是挂死而非失败，导致 Windows 上 `pytest` 永远跑不完））
- [x] **Windows：`tools.command.sandbox` 被完全跳过**（已修复：`neow/tools/command.py` 之前 `sys.platform == "win32"` 时直接不调 `sandbox.plan()`，于是 `strict` 模式照跑命令、`auto` 模式不给提示。现在所有平台都问 `plan()`，Windows 上只丢弃它返回的 POSIX argv）
- [x] **PowerShell 翻译器吃掉带连字符的文件名**（已修复：`neow/tools/command.py` 的 `_strip_flags`/`_extract_flags` 原来用 `\s*-[a-zA-Z]+\b`，把 `made-by-shell.txt` 拆成 `-by`/`-shell` 当 flag 删掉，`touch made-by-shell.txt` 变成 `New-Item -ItemType File made.txt`。现在 flag 必须是独立 token。回归测试：`tests/test_tools.py::TestPowerShellTranslation`）
- [x] **hooks 超时在 Windows 上不生效**（已修复：`neow/core/hooks.py` 原来用 `subprocess.run(timeout=)`，它只杀直接子进程，而 shell 的孙进程持有 stdout/stderr 管道，清理阶段照样阻塞到孙进程结束（0.5s 超时实测等了 10.7s）。改为 `Popen` + `communicate(timeout=)`，超时后 `taskkill /T /F`（POSIX 用 `killpg`）杀掉整棵树）
- [x] `neow/tui/commands.py` 重复定义 `_cmd_image`（已修复：删掉被覆盖的死代码）
- [x] MCP 启动失败的错误信息不含目标（已修复：`_describe_error` 现在带上 `config.describe()`；顺带让 `tests/test_mcp.py` 不再断言本地化的 OS 文案）
- [x] 一批只在 Windows 上失败的测试（已修复：`USERPROFILE`/`HOME` 双设、hook 命令按平台加引号、`os.sep` 断言、CRLF 文件用 `newline=""` 写入、chmod 断言限定 POSIX）
- [x] **eval harness 泄漏 `console._file`，污染后续所有测试**（已修复：`evals/runner.py::_sandbox` 直接 `CliRunner().invoke()`，而 headless 模式会把模块级 console 指向 stderr 且不会指回来；`test_evals.py` 之后的用例里 `capsys` 再也抓不到 console 输出，`test_hooks.py::test_repository_config_cannot_define_hooks` 因此随机失败。现在 `_sandbox` 一并 patch/恢复 `formatter.console._file`）
- [x] **两个时序测试在 Windows 上随机失败**（已修复：`tests/test_parallel_tools.py` 用 `elapsed >= DELAY * 2/3` 判断"串行执行"，但 Windows 计时器粒度会让 0.6s 实测成 0.594s；改成断言真实性质——调用区间不重叠 / 顺序固定。`tests/tui/test_cards.py::test_tool_finished_before_mount_still_renders_body` 随机失败是因为 `ToolCard.on_mount` 用 `call_after_refresh(_render_body)` 补渲染，而 `_render_body` 又被 `is_mounted` 挡住（`Static.update()` 需要 `widget.app.console`，`on_mount` 里 `is_mounted` 仍为 False）——于是卡片要等下一次 refresh 才有内容。现在 `_render_body(force=True)` 在 `on_mount` 同步渲染）
- [x] **代码风格与 lint 清零**（已修复：此前 `flake8` 有 164 项、`black --check` 有 52 个文件不合规。先跑一次 `black .`（55 个文件重排，纯机械），再手工折行 `black` 拆不开的 36 条长行——其中 114→36 是 `black` 的功劳，剩下 36 条是长字符串/长注释。现在 `flake8 neow` 为 0 项、`black --check .` 全绿，两个 gate 都进了 CI。**注意**：`neow/core/architect.py` 的 `PLANNER_SYSTEM_PROMPT` 里那段 JSON 示例被改成多行缩进格式（原来两行各 89 字符），指令和示例取值都没变；`SYSTEM_PROMPT` 已用脚本比对确认逐字节相同（1694 字符））

---

## 里程碑规划

| 里程碑 | 包含 | 预计覆盖率 | 状态 |
|--------|------|-----------|------|
| v0.2 | P0 全部（Git + Streaming + 上下文 + 编辑精度） | ~50% | ✅ 已完成 |
| v0.3 | P1 全部（Context + Architect + Lint + 模型切换） | ~65% | ✅ 已完成 |
| v0.4 | P2 全部（持久化 + Token + 安全 + CLI 增强） | ~80% | ✅ 已完成 |
| v0.5 | P3 全部（Web + 插件） | ~90% | ✅ 已完成 |
| v0.6 | P4 全部（Approval Mode + Compaction v2 + Session Tree + Hashline Edit） | ~95% | ✅ 已完成 |
| v0.7 – v0.9 | P5 全部（Agent 核心强化，见下） | — | ✅ 已完成 |
| v1.0 | P6 全部（质量评测 + 多模态 + IDE 集成 + 性能成本优化） | ~95% | ✅ 已完成 |

---

## P4 - 借鉴 OhMyPi 的核心能力（v0.6）

### 15. Approval Mode ✅
对标 OhMyPi 的工具审批系统，让用户精确控制 AI 的自动执行边界。

- [x] 三级模式：`always-ask`（每次确认）、`write`（写入需确认）、`yolo`（全自动）
- [x] 工具声明 approval tier（read/write/exec）
- [x] 用户按工具名覆盖策略（`tools.approval.<tool>: allow|deny|prompt`）
- [x] 危险操作强制 prompt（`rm -rf`、`git push --force` 等）
- [x] `/approval` REPL 命令：查看/切换模式
- [x] SubAgent 独立 executor；默认 `agent.subagent_approval: inherit`，继承并转发父会话审批（弹窗路由回父线程），显式设为 `yolo` 才跳过审批

### 16. Compaction v2 ✅
升级 `/compact` 为增量式、自动触发的上下文管理。

- [x] 保留最近 N tokens 消息，只总结旧消息（`compact_incremental`）
- [x] 自动触发：80% token 阈值触发 auto-compact
- [x] `/compact --keep-tokens N` 命令
- [x] `/compact incremental` 命令
- [x] idle 维护：空闲 >30s 且 token >50% 时自动 compact
- [x] split-turn 处理：不完整 tool-call turn 的上下文保留
- [x] Handoff 策略：`/compact handoff` 生成交接摘要并重置会话

### 17. Session Tree ✅
从线性 session 升级为树形，支持分支/导航/回退。

- [x] JSONL append-only 格式（替代 JSON 全量写入）
- [x] `id`/`parentId` 树结构 + `leafId` 指针
- [x] `/tree` 命令：可视化导航到任意历史节点
- [x] `/branch` 命令：从任意用户消息分叉新 session
- [x] Branch summary：放弃分支时自动生成摘要

### 18. Hashline Edit ✅
基于文件哈希锚定的精确编辑，防止过时编辑。

- [x] `¶PATH#HASH` 格式的编辑指令
- [x] 行号锚定编辑（insert before/after, replace, delete）
- [x] Stale-anchor recovery：文件变更后自动恢复
- [x] 多文件批量编辑
- [x] BOM 和行尾风格保留

---

## P5 - Agent 核心强化（v0.7 – v0.9）

> 详细设计、问题证据（E1–E16）与逐任务测试清单见 `docs/design/plans/2026-10-08-neow-agent-core-plan.md`。

- [x] **阶段 0 基础重构**：统一工具注册表 `ToolSpec`（插件工具对模型可见）、抽出唯一的 `AgentLoop`（取消令牌、历史修复）
- [x] **阶段 1 正确性**：Anthropic 格式适配与流式多工具修复、可配置输出上限、工具参数容错、可配置重试次数（SDK 已内置重试）、可真正取消的命令执行
- [x] **阶段 2 上下文效率**：工具输出统一截断与 `read_file` 分页、稳定系统提示与提示缓存、准确的上下文用量、提示词清理与“先读后改”
- [x] **阶段 3 项目记忆**：加载 `AGENTS.md` / `NEOW.md`、`/init`、`/memory`
- [x] **阶段 4 生态**：`grep`/`glob`/`list_dir`、`todo_write`、子 agent 工具化（`task`，不再 yolo）、只读工具并行、MCP 客户端
- [x] **阶段 5 安全**：可配置 hooks、文件回退点 `/rewind`、（实验）命令沙箱
- [x] **阶段 6 自动化**：无头模式 `--output-format json|stream-json`

---

## P6 - 规模化与打磨（v1.0）

> 核心能力已齐备（~95%），P6 聚焦让 Neow 经得住真实、长期、多人使用的考验，而非再堆新功能。

### 19. 质量与评测体系（优先级最高）
目前主要靠手动验证，规模变大后容易退化且难发现回归。

- [x] 搭建 eval 套件：固定任务集（多文件编辑、bug 修复、重构）+ 自动打分（`evals/`，见 `evals/README.md`；默认 scripted client，零成本、CI 友好，不评估真实模型质量）
- [x] CI 中跑核心单测 + 关键 eval 子集，防止回归（`.github/workflows/ci.yml`；eval 子集即 `tests/test_evals.py`，随 `pytest` 一起跑）
- [x] 重新评估 tree-sitter repo map 的必要性 — **结论：继续暂缓，但理由变了**。`tree-sitter` / `tree-sitter-languages` 现在都有 Windows 预编译 wheel，当初的 Windows 兼容性理由已过时；但目前没有真实 monorepo 痛点证据，`grep`/`glob`/`list_dir` + `AGENTS.md` 项目记忆已覆盖日常场景，而引入 tree-sitter 要为每种语言维护 grammar 依赖和 symbol 提取查询，维护成本不低。**重新开工触发条件**：用户反复反馈 grep 找不到定义/引用关系，或者在 >5 万行、命名约定不统一的 monorepo 里验证 grep 噪音过大。
- [x] 记录失败案例库（prompt + 预期 + 实际），作为回归测试种子 — 基础设施已搭好：`evals/failures/`（流程 + 模板）+ `EvalTask.category`（区分 smoke / regression）。库目前是空的，没有编造案例填充——等真实使用中出现 eval/单测都没覆盖到的 bug 时，按模板记录并转成 `category="regression"` 的 `EvalTask`

### 20. 多模态能力
目前仅支持文本，无法处理截图/图片类输入，限制了 UI 调试、报错截图分析等场景。

- [x] `/add <image>` 或粘贴截图加入上下文（复用 Claude vision）— `/image <path>` 这条路径其实早就有了（`queue_image`/`_build_vision_content`/adapters 都已实现，只是没出现在路线图里）；这次补的是：`/add <image>` 原来会因为 `read_text` 读二进制文件直接崩溃，现在会按 mimetype 自动转给 `queue_image`；新增 `BaseModelClient.supports_vision`（Anthropic/OpenAI=True，DeepSeek=False），队列图片时如果当前模型不支持会给出警告；补了 `tests/test_core.py::TestQueueImage` 等直接单测
- [x] 终端内图片预览（支持的终端：iTerm2/kitty 协议）— `neow/utils/formatter.py` 的 `print_inline_image`（iTerm2 OSC 1337 / kitty 图形协议，非 tty 或不认识的终端直接返回 False 走文字兜底），`/image` 命令队列成功后调用
- [x] 截图 diff（UI 改动前后对比，辅助视觉回归判断）— 新增 Pillow 依赖，`neow/tools/imgdiff.py` 的 `diff_images`（不同尺寸自动左上对齐 padding，不报错；差异像素红色高亮）+ `/imgdiff <before> <after>` 命令：生成 diff 图、终端内预览、并 `queue_image` 进对话让模型也能看到。顺带把 `/image`/`/imgdiff` 补进了 TUI 的 `CommandDispatcher`（之前只有 REPL 有，TUI 侧会落到"not available yet"）；TUI 没有内联图片预览（Textual 接管了屏幕，直接写转义序列会破坏渲染），只排队给模型看

### 21. 编辑器 / IDE 集成
当前只能在终端 REPL 里用，离"结对编程"的无缝体验还有距离。

- [x] 评估 LSP server 模式 vs VSCode 插件桥接，二选一先落地最小可用版本 — **结论：桥接 CLI，不做 LSP server**。LSP 是给补全/诊断设计的协议，"聊天 + diff + 批准/拒绝"不是它的原生语义，硬塞进去（自定义 notification/code action）得到的工具支持跟直接做扩展差不多，却要多维护一个协议层；而 Neow 已经有 `--output-format stream-json` 的事件流，桥接成本低很多。代价：Neovim/Emacs 用户目前只能在终端里用 REPL/TUI，没有编辑器内插件——可接受，等真有人要求再加。
- [x] 编辑器内发起对话、接收 diff、一键应用/拒绝 — **应用层已落地**。建立 `editors/vscode/` 插件体系，基于 `--output-format stream-json --approval-interactive` 双向事件协议驱动，在侧边栏 Webview 提供流式思考与聊天卡片、交互式工具审批弹窗通知、右键选区代码解释/修复，以及工作区文件编辑应用；单测：`tests/test_vscode_extension.py`。
- [x] 复用现有 approval mode / hashline edit 作为底层能力，不重复造轮子 — 没有新造一套审批/编辑逻辑：`--approval-interactive` 只是给已有的 `ApprovalPolicy`/`executor.approval_callback` 接了个新的 I/O 通道，扩展侧的 diff/apply 走的还是模型原本会调的 `edit_file`/`hashline_edit`/`write_file` 等工具，扩展只是把批准动作从"终端打字"换成"点按钮"。

### 22. 性能与成本自动优化
模型选择、并发策略目前靠用户手动配置，缺少自适应能力。

- [x] 简单任务自动路由到低成本模型（基于任务复杂度粗分类），复杂任务才上强模型 — 新增 `neow/core/router.py`，实现 `TaskComplexityClassifier`（分析长短指令、多步指令、文件数量、中英文架构/重构关键词）与 `ModelRouter`；支持在配置中启用或通过 `/model auto` 实时自适应路由；单测：`tests/test_router.py`。
- [x] prompt cache 命中率监控与展示（`/cost` 扩展） — 增强 `neow/core/token_tracker.py`，实现 `get_cache_savings()` 与 `get_cache_stats()`，在 `/cost`（REPL / TUI / Headless）中展示缓存命中量、命中率与节省费用；流式结束实时显示单次缓存命中；模型基类增强对 dict 格式 usage 适配；单测：`tests/test_prompt_cache.py`。
- [x] 评估将只读工具并行范围扩大到部分写操作（需配合 approval mode 的安全边界） — 输出详细技术评估报告 `docs/design/2026-10-25-parallel-write-evaluation.md`；在 `neow/core/executor.py` 与 `neow/core/agent_loop.py` 中实现目标文件互斥与免审批安全检测（`can_batch_run_concurrently`），安全并发无冲突受控文件写操作，同一文件强制串行保证因果一致；单测：`tests/test_parallel_tools.py`。
