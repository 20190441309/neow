# Neow TUI 验收报告（t10）

- 日期：2026-10-07
- 分支：`feat/tui`（基线 `cbfe09d`，验收 head `57d7f77`）
- 规格：`docs/design/2026-10-07-neow-tui-design.md`
- 计划：`docs/design/plans/2026-10-07-neow-tui-implementation.md`
- 审查方式：**作者自审**（本环境无子智能体调度工具，按 `requesting-code-review` 的 code-reviewer.md 流程执行，非独立审查者）
- 审查包：`.superpowers/sdd/2026-10-07-neow-tui-implementation/review-cbfe09d..930d47f.diff`

## 1. 验收命令与结果

| 命令 | 结果 |
|------|------|
| `pytest -q`（全量） | **536 passed, 0 failed** |
| `flake8 neow/tui tests/tui`（仓库 `.flake8`：max-line-length 88 / extend-ignore E203） | clean |
| `black --check neow/tui tests/tui neow/cli/mode.py` | clean（48 files unchanged） |
| `python tests/tui/pty_smoke.py` | **PTY SMOKE OK**（TUI / `--plain` / one-shot 三入口） |
| `python tests/tui/pty_observe.py` | **PTY OBSERVE OK**（thinking 乱码 + 流式渲染） |
| `python tests/tui/pty_commands.py` | **PTY COMMANDS OK**（/help、/diff、/model） |
| `python tests/tui/pty_full_flow.py` | **PTY FULL FLOW OK**（启动→对话→工具调用→审批→回复→退出） |
| `git diff --stat e397f9d..HEAD -- neow/core neow/models neow/tools` | 仅 `neow/core/config.py` +25 行（tui 配置默认值与校验），无业务语义改动 |

证据原文：`docs/design/evidence/`（pty-observe / pty-commands / pty-full-flow 的终端输出）。

## 2. 规格 §4–§10 逐条核对

### §4 信息架构与布局

| 要求 | 状态 | 证据 |
|------|------|------|
| 单列卡片时间线 + 顶栏 + 输入坞 + 状态栏 | ✅ | `01-main.png` 设计稿；ChatScreen compose；`test_app_mounts` |
| Tab 切换侧栏（CONTEXT/SESSION TREE/GIT 三页签） | ✅ | `test_sidebar_tabs_cycle_and_refresh` |
| QueueStrip 排队提示 + `↑` 取回 | ✅ | `test_queue_fifo_and_pop`、`test_queue_drains_after_turn` |
| 吸附底部 + 「↓ 新消息」banner | ✅ | `test_stick_to_bottom_and_banner`（6/6 稳定） |
| 断点 110/88/72（侧栏宽度/禁用/紧凑） | ✅ | `ChatScreen.apply_width_classes` + `test_narrow_resize_no_crash` |
| `tui.sidebar_default` 启动展开侧栏 | ✅ | `test_sidebar_default_config_shows_sidebar` |

### §5 卡片体系

| 要求 | 状态 | 证据 |
|------|------|------|
| User/Thinking/Assistant/Tool/Error/System 卡片 | ✅ | `test_cards.py` 26 项 |
| 工具卡：运行展开 → 完成自动折叠；错误保持展开；拒绝 ⛔ | ✅ | `test_tool_running_expanded_then_done_collapses` 等 5 项 |
| 用户手动操作后不再自动折叠 | ✅ | `test_user_toggle_during_run_disables_auto_collapse` |
| 8 类工具正文渲染器 | ✅ | `render_tool_body` 单测 5 项 |
| Thinking：实时 reasoning + 乱码锋面 + 落定折叠 | ✅ | `test_thinking_frame_has_settled_prefix_and_frontier`、PTY 证据 |
| 流式 Markdown + 光标；挂载前内容缓冲 | ✅ | `test_streaming_appends_markdown_and_shows_cursor`、`test_assistant_buffers_content_before_mount` |
| 长内容截断提示（reasoning >4000 字 / assistant >300 行 / tool >30 行） | ✅ | 三个 truncation 测试 |
| 任意文本按字面渲染（防 markup 注入） | ✅ | `test_user_card_renders_brackets_as_text`、`test_diff_screen_renders_markup_like_text` |

### §6 动效与性能

| 要求 | 状态 | 证据 |
|------|------|------|
| 启动渐变 logo，600ms 收起，任意键跳过 | ✅ | `test_effects_off_disables_logo_timer`、`test_logo_skips_on_any_key` |
| effects 三档 `full/subtle/off` + `TEXTUAL_ANIMATIONS=none` | ✅ | `test_effect_mode_from_config_and_env` |
| 卡片入场动画 | ✅ | `test_full_effects_play_card_entrance` |
| 流式光标脉冲 / 完成闪烁 / 审批边框脉冲 | ✅ | `AssistantCard._blink`、`ToolCard.finish`、`ApprovalModal._pulse` |
| 非 TTY 降级为纯文本 | ✅ | `select_run_mode`（`test_entry.py` 8 项） |
| 无可感知卡顿 | ✅ | PTY 观察整会话 9s（含 Python/Textual 启动），流回合 ~1s；`@` 补全扫描 5s 缓存 |
| Tool 运行 braille spinner | ⚠️ 延后 | 运行态图标为静态 `⟳`（状态语义完整；动画见延后清单） |

### §7 交互模型

| 要求 | 状态 | 证据 |
|------|------|------|
| Enter 发送 / Ctrl+J 换行 / Ctrl+O 折叠 / Tab 侧栏 / Ctrl+T 页签 | ✅ | `test_enter_submits_and_ctrl_j_newlines`、`test_queue_fifo_and_pop`、`test_sidebar_tabs_cycle_and_refresh` |
| Esc 中断生成；中断后续回合可用 | ✅ | `test_cancel_emits_cancelled_turn`、`test_cancel_then_new_turn`、`test_cancel_then_submit_again` |
| `/` 命令补全 + `@` 文件补全 + 历史 | ✅ | `test_slash_completion_filters_commands`、`test_at_file_completion`、`test_history_roundtrip` |
| 生成中排队（FIFO，结束后自动发送） | ✅ | `test_queue_drains_after_turn` |
| 27 个 `/命令` 全覆盖 | ✅ | `test_commands.py` 7 项 + `SLASH_COMMANDS` 27 项 + HelpScreen |
| 功能屏：help/model/session/tree/diff/cost/approval | ✅ | `test_screens.py` 8 项 |
| F1 帮助 | ✅ | `test_f1_opens_help` |
| Ctrl+P 命令面板含全部 slash 命令 | ✅ | `test_command_palette_lists_slash_commands` |
| 审批：y/a/n/Esc，a 写回 policy override | ✅ | `test_modal_keys_return_decision`、`test_always_sets_policy_override` |
| 审批全链路（worker→bridge→模态→Future） | ✅ | `test_approval_flow_end_to_end` + PTY FULL FLOW |
| Ctrl+Y 复制代码块 / 图片 chip / /clear 确认 | ⚠️ 延后 | 见延后清单 |

### §8 视觉系统

| 要求 | 状态 | 证据 |
|------|------|------|
| 调色板 token（§8.1）收在 theme.tcss | ✅ | `theme.tcss`；设计稿 4 张 PNG |
| 角色色条 / 语义色 | ✅ | 卡片 accent + 设计稿 |
| v1 单主题 `midnight`，非法值回退 | ✅ | `Config.tui` 校验 + `test_tui_config_unknown_effects_falls_back` |
| 安全字形集（无需 Nerd Font） | ✅ | 图形字符列表（◆●✻⟳✓✗⛔◈⎇❯⏳▊） |

### §9 技术架构

| 要求 | 状态 | 证据 |
|------|------|------|
| `neow/tui/` 模块结构（screens/widgets/effects/bridge） | ✅ | 文件树 + 计划任务 3–15 |
| worker 线程消费 stream，事件回 UI 线程 | ✅ | `ChatScreen._run_turn` + `TuiEventMessage`；`test_event_sequence_from_fake_stream` |
| 50ms delta 聚合 | ✅ | `test_delta_coalescing_with_fake_clock` |
| 审批 Future 桥 + 超时/取消拒绝兜底 | ✅ | `test_bridge_timeout_denies`、`test_bridge_cancel_denies` |
| 取消语义（关闭 generator，工具执行完停止） | ✅ | controller cancel 测试族 |
| 会话持久化（退出自动保存） | ✅ | `test_exit_saves_session`（复核阶段补齐） |
| core 零语义改动 | ✅ | 仅 config.py 增 tui 段（+25 行） |
| `textual>=8,<9` 依赖、pytest-asyncio | ✅ | `pyproject.toml` |

### §10 入口与兼容

| 场景 | 状态 | 证据 |
|------|------|------|
| `neow`（TTY）→ TUI | ✅ | PTY SMOKE 入口 1 |
| `neow --plain` → 旧 REPL | ✅ | PTY SMOKE 入口 2 |
| `neow --tui` 强制 / 非 TTY 退出码 2 | ✅ | `test_cli_tui_non_tty_exits_2` |
| `neow "prompt"` 一次性模式不变 | ✅ | PTY SMOKE 入口 3 |
| 管道/非 TTY → plain | ✅ | `test_no_tty_falls_back_plain`、`test_piped_stdin_falls_back_plain` |
| 冲突 flag → 退出码 2 | ✅ | `test_cli_flags_conflict_exits_2` |
| textual 导入失败 → 警告 + 回退 REPL | ✅ | `tui_available()` 探测 + main 回退分支；`test_tui_available_when_textual_installed`、`test_tui_unavailable_when_textual_missing` |

## 3. 审查发现与处置

审查中确认并修复（每个都有 RED→GREEN 测试）：

| 级别 | 发现 | 处置 |
|------|------|------|
| Critical | 任意文本（用户输入、diff、system/error 详情、会话名）被当 Rich markup 渲染；PTY `/diff` 实测 `MarkupError` 崩溃 | 统一包 `Text()`；`test_user_card_renders_brackets_as_text` 等 |
| Important | TUI 退出不自动保存会话（REPL 会保存） | `ChatScreen.on_unmount` 保存；`test_exit_saves_session` |
| Important | `@` 补全每次按键同步扫描最多 5000 个路径 | 5s 缓存 + `_scan_files`；`test_file_options_are_cached` |
| Important | 卡片在挂载完成前追加的内容被丢弃（PTY 观察到空 Assistant 卡） | `AssistantCard` pending 缓冲 + `on_mount` flush |
| Minor | 时间线 burst 加卡后 follow 欠底（测试抖动） | 有界二次 follow |
| Minor | 死代码 / 未用导入 / 超长行 | flake8 clean |
| Minor | 规格缺口：`tui.sidebar_default`、F1、Ctrl+P 面板 | 复核轮补齐（3 测试） |

任务执行期间已修复的真实缺陷还包括：`Widget._render` 命名冲突（两次）、Textual 8 `SelectionList` 无 `Selected` 消息、`Static.update` 需 active app、AssistantCard 缓冲等，均记录在 SDD 账本。

**审计补记（goal 完成后）**：审计指出 lint 证据表述不准确——flake8 不读 `pyproject.toml` 的 `[tool.flake8]`，默认命令会报 60+ 条 E501；已新增仓库级 `.flake8`（max-line-length 88 / E203），默认命令现为 clean，本报告 lint 行改为精确命令。同时补齐规格 §10 最后一行：`textual` 缺失时的警告 + 回退 REPL（`tui_available()` + 两个单测）。

将 `neow/cli` 纳入 lint 范围后还发现两处 `print_warning` 未导入的潜在 `NameError`：`main.py`（本次回退分支引入）与 `repl.py` 的既有路径（token 告警/空闲压缩时触发）；均已修复，F821 现为 0。`neow/cli` 仍存在既有的 E402/E501/E303 等风格债务（不改变旧代码风格，未处理）。

## 4. 延后的 Minor

1. 工具正文受 `progress.result[:500]` 限制（完整输出需改 core 边界）。
2. 侧栏 GIT 刷新在侧栏隐藏时仍执行（每回合同步 git 调用）。
3. Tool 运行态为静态 `⟳`，braille spinner 动画未做。
4. 压缩事件用 SystemCard 呈现，未单独建 CompactionCard。
5. Ctrl+Y 剪贴板复制未实现。
6. 图片附件可排队但无视觉 chip。
7. `/clear` 无确认弹窗。
8. `/load <name>`、`/model <name>` 带参数时仍打开选择器（规格将它们映射为屏幕）。
9. 亮色主题/`tui.theme` 变体（v1 范围外）。
10. `tui.emoji` 图标开关预留未实现。

## 5. 裁决清单（复审用）

- 布局取 A（单列 + Tab 侧栏）；Thinking 取 V2（实时 + 乱码锋面）；工具卡完成自动折叠；生成中排队（用户已批准）。
- `docs/superpowers/` 被仓库 .gitignore 忽略 → 正本放 `docs/design/`，契约路径留副本。
- 旧 `NeowLogo`（status_bar.py）与新的统一到 `widgets/logo.py`。
- 非 TTY 降级由 `select_run_mode` 承担（effects 层不重复判断）。
- black 门禁只覆盖新增 TUI 文件；两个既有文件在基线即非 black-clean，保持不动。
- 工作保留在 `feat/tui` 分支，集成方式由用户决定（finishing-a-development-branch 菜单）。

## 6. 结论

规格 §4–§10 的全部功能项均已实现并通过测试；§6 的 braille spinner 与 §7 的 3 项增强、§5 的 CompactionCard 独立化列入延后清单。全量测试、lint、black（新增文件）、四类 PTY 冒烟全部通过，core 无业务语义改动。**作者自审弱于独立审查者**，合并前是否接受由你决定。
