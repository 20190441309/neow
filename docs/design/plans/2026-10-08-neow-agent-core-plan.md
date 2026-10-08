# Neow Agent 核心强化计划（v0.7 – v0.9）

> **面向 AI 代理的工作者：** 按阶段、按任务顺序实现。每个任务先写失败测试，再实现，再跑全量回归，最后单独提交。步骤用复选框（`- [ ]`）跟踪进度；完成后勾选并在任务末尾记录 commit 哈希。

**目标：** 把 neow 的 agent 核心从“功能齐全的原型”提升到主流 agent CLI（Claude Code / Codex CLI / Gemini CLI / OpenCode）的可靠性与扩展性水平：工具循环不会因单次异常整轮失败、上下文不会被大输出撑爆、模型能看到项目约定、能接入 MCP 生态、子 agent 与审批安全一致。

**来源：** 2026-10-08 对 `neow/core`、`neow/models`、`neow/tools` 的代码审读（见下文“现状证据”）。结论基于读代码，未用真实 API 验证；任务 1.1 的第一步就是补上不 mock SDK 的格式测试来坐实。

**工作目录与命令约定：**
- 仓库：`/srv/workspaces/user2/neow`；虚拟环境：`.venv`（用 `uv` 创建）。
- 全量测试：`PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m pytest tests -q -p no:cacheprovider --no-cov`
  （venv 必须在 PATH 上，否则 `test_tools.py::TestCommand::test_execute_command_with_output` 会因找不到 `python` 失败）。
- Lint：`.venv/bin/python -m flake8 <改动的 .py 文件>`（配置见 `.flake8`，行宽 88）。
- **基线：623 passed（2026-10-08，commit `2c337b5`）。** 每个任务结束时数量只增不减、全部通过。

---

## 全局约束

- **内部消息格式统一为 OpenAI Chat 格式**（`role: user|assistant|tool`、`tool_calls`、`tool_call_id`），会话持久化（JSONL / session tree）继续存这个格式；各 provider 客户端负责在边界上转换。不要把 provider 专有格式写进 `conversation.messages`。
- `neow --plain`（REPL）与 TUI 必须同时可用；core 改动通过事件/回调暴露，不在 core 里 import TUI。
- 新运行时依赖只允许：`mcp`（阶段 4，任务 4.5）。`ripgrep` 作为可选外部二进制，缺失时必须回退到纯 Python 实现。
- 不破坏既有配置文件：新增配置项都要有默认值，旧 `.neow.json` 原样可用。
- 公开行为变化（工具名、工具输出格式、命令）必须同步：`neow/core/prompts.py` 的工具 schema、`neow/tui/screens/help.py`、`README.md`。
- Conventional Commits；**一个任务一个 commit**；commit 末尾带 `Co-Authored-By` 行（如由 AI 代理提交）。
- 每个阶段结束后更新 `CLAUDE.md` 路线图对应条目的勾选状态。

## 审查重点（每个 PR 都要过）

1. **历史记录合法性**：任何路径（取消、异常、超时、截断）结束后，`conversation.messages` 中每个带 `tool_calls` 的 assistant 消息，其每个 `id` 都必须有对应的 `role: tool` 结果。否则下一次请求会被 API 拒绝。→ 统一由任务 0.2 的 `validate_history()` 断言，所有循环相关测试结束时调用。
2. **provider 等价**：同一段对话（含工具调用、并行工具调用、图片）经 OpenAI / DeepSeek / Anthropic 三个适配器转换后都必须是该 API 接受的形状。→ 任务 1.1 的契约测试。
3. **审批不可绕过**：新增的任何执行路径（子 agent、并行执行、MCP 工具、hooks）都必须经过 `ToolExecutor.execute()` 的安全检查与审批闸门。
4. **上下文预算**：任何单个工具结果写入历史前都经过统一截断（任务 2.1）。

---

## 现状证据（问题清单）

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| E1 | Anthropic 客户端原样发送 OpenAI 格式的工具定义（`{"type":"function","function":{...}}`）和消息（`role:"tool"`、`tool_calls`） | `neow/models/anthropic.py:62-72, 133-140`；schema 来自 `neow/core/prompts.py:get_tool_definitions` | 带工具的请求预计直接 400；Architect 规划器默认就是 anthropic |
| E2 | Anthropic 流式解析把 `input_json_delta` 追加到**所有**工具缓冲区 | `neow/models/anthropic.py` 流式循环 `for tid in tool_inputs` | 一次返回多个工具调用时参数全部被拼坏 |
| E3 | `max_tokens` 写死 4096，且未处理 `max_tokens` / `length` 停止原因 | `anthropic.py:64,135` | 大文件 `write_file` 参数被截断成非法 JSON |
| E4 | 工具参数 `json.loads` 无保护 | `neow/core/conversation.py:184, 312` | 模型输出一次坏 JSON 就整轮失败 |
| E5 | 工具结果不限长；`read_file` 返回全文 | `conversation.py:add_tool_result`、`neow/tools/file_ops.py:16` | 上下文快速膨胀、费用飙升 |
| E6 | 无重试/退避 | `neow/models/*.py` | 429/5xx/网络抖动直接失败 |
| E7 | 取消只停止消费流；进行中的命令跑到超时；取消点可能留下无结果的 `tool_calls` | `neow/tui/bridge/controller.py:80-118`、`conversation.py:get_response_stream`、`neow/tools/command.py:273` | 卡住 / 历史不合法导致后续请求 400 |
| E8 | 系统提示每轮变化（按用户输入匹配相关文件拼进 system） | `conversation.py:_get_effective_system_prompt` | 前缀缓存失效 |
| E9 | 项目结构只在会话第一次请求的 system 里出现，之后消失 | `conversation.py:_build_project_context`（`_structure_injected`） | 模型中途“忘记”项目结构 |
| E10 | 插件 `register_tool` 只登记函数，不提供 schema | `neow/core/plugin.py:57`、`prompts.get_tool_definitions` 是静态列表 | 插件工具模型不可见，插件系统实际不可用 |
| E11 | 图片以 Anthropic 块格式排队，OpenAI/DeepSeek 客户端未转换 | `conversation.py:queue_image`、`models/openai.py` | `/image` 在非 Anthropic 模型上失败 |
| E12 | 子 agent 固定 yolo、并发写同一工作区 | `neow/core/sub_agent.py:35`、`neow/core/architect.py:116` | 绕过审批；并发编辑冲突 |
| E13 | TUI 按工具**名**追踪运行中的卡片 | `neow/tui/screens/chat.py`（`_running_tools[event.name]`） | 同一工具连续/并行调用时卡片状态串位 |
| E14 | `get_response` 与 `get_response_stream` 两套几乎相同的循环 | `conversation.py:131-236, 238-340` | 每个修复都要改两遍，已出现分叉 |
| E15 | 上下文占用只靠“4 字符≈1 token”估算；`StatusBar.set_context` 从未被调用 | `conversation.py:449`、`neow/tui/widgets/status_bar.py:128` | 自动压缩阈值不准；用户看不到占用 |
| E16 | 系统提示自相矛盾（“修改前必须展示改动” vs yolo）；工具说明在 prompt 与 schema 中重复 | `neow/core/prompts.py` | 模型行为摇摆、浪费 token |

---

## 阶段与里程碑

| 阶段 | 内容 | 里程碑 | 依赖 |
|------|------|--------|------|
| 0 | 基础重构：工具注册表、统一 agent 循环 | v0.7-alpha | — |
| 1 | 正确性：provider 适配、输出上限、参数容错、重试、取消 | v0.7 | 0 |
| 2 | 上下文效率：输出截断、稳定前缀与缓存、准确计数、提示词清理 | v0.7 | 0、1.1 |
| 3 | 项目记忆：AGENTS.md / NEOW.md、`/init` | v0.8 | 2.2 |
| 4 | 生态：搜索工具、todo、子 agent 工具化、并行调用、MCP | v0.8 – v0.9 | 0、1 |
| 5 | 安全：hooks、文件回退点、（实验）沙箱 | v0.9 | 0.2 |
| 6 | 自动化：无头模式结构化输出 | v0.9 | 0.2 |

建议顺序：0.1 → 0.2 → 1.1 → 1.2 → 1.3 → 1.5 → 1.4 → 2.1 → 2.2 → 2.3 → 2.4 → 3.1 → 4.1 → 4.4 → 4.2 → 4.3 → 4.5 → 5.1 → 5.2 → 6.1 → 5.3。

---

## 阶段 0 · 基础重构

### 任务 0.1 · 统一工具注册表 `ToolSpec`

**为什么：** 现在工具的函数（`cli/main.py:setup_tools`）、schema（`prompts.get_tool_definitions` 静态列表）、审批层级（`approval.TOOL_TIERS`）、是否改文件（`executor.FILE_MUTATING_TOOLS`）分散在四处。MCP、子 agent 工具、todo、插件都需要“一处注册、处处可见”。修复 E10。

**文件：**
- 新建 `neow/core/tools_registry.py`
- 修改 `neow/core/executor.py`、`neow/core/prompts.py`、`neow/core/approval.py`、`neow/core/plugin.py`、`neow/cli/main.py`
- 测试 `tests/test_tools_registry.py`

**设计：**
```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict            # JSON Schema (object)
    func: Callable[..., str]
    tier: ApprovalTier          # read / write / exec
    read_only: bool = False     # 可并行、可给 explore 子 agent
    mutates_files: bool = False # 触发 on_file_change / checkpoint
    source: str = "builtin"     # builtin | plugin:<name> | mcp:<server>

class ToolRegistry:
    def register(self, spec: ToolSpec) -> None
    def get(self, name) -> ToolSpec | None
    def definitions(self, *, names=None, read_only=None) -> list[dict]  # OpenAI 格式
    def subset(self, predicate) -> "ToolRegistry"                      # 子 agent 用
```
- `ToolExecutor` 持有 `registry`；保留 `register_tool(name, func)` 作为兼容层（schema 用函数签名 + docstring 自动推断，tier 默认 exec）。
- `prompts.get_tool_definitions()` 改为从内建 spec 生成，保持返回内容与现在逐字段一致（先写快照测试锁住）。
- `ApprovalPolicy.check_approval` 的 tier 优先取 `spec.tier`，`TOOL_TIERS` 只作为未注册工具的回退。
- `PluginAPI.register_tool(name, func, description="", parameters=None, tier="exec", read_only=False)`；`conversation.set_tools()` 改为每次请求从 registry 取（插件加载后自动可见）。

**步骤：**
- [x] 快照测试：当前 `get_tool_definitions()` 输出写入 `tests/fixtures/tool_definitions.json`，断言重构后不变
- [x] 实现 `ToolSpec` / `ToolRegistry`，内建工具在 `neow/tools/builtin.py:builtin_specs()` 声明
- [x] `ToolExecutor` 改走 registry
- [x] 插件 API 支持 schema；测试：插件注册的工具出现在发给模型的 `tools` 里
- [x] 全量回归（630 passed）+ PTY 脚本

**测试：** `test_registry_definitions_match_snapshot`、`test_legacy_register_tool_infers_schema`、`test_register_tool_rebinds_known_tool_keeps_schema`、`test_plugin_tool_visible_to_model`、`test_tier_from_spec_overrides_table`、`test_search_code_directory_is_optional`、`test_registry_subset_and_copy_are_independent`（`tests/test_tools_registry.py`）

**实现记录（与设计的差异）：**
- 内建 spec 放在 `neow/tools/builtin.py` 而不是 `neow/tools/__init__.py`，避免导入任意 `neow.tools.*` 子模块时连带加载全部工具。
- `ToolExecutor()` 仍然注册**占位实现**（调用即 `NotImplementedError`），只有 `setup_tools()` 绑定真实实现。原因：大量测试用默认 executor 构造 `ConversationManager`，改成真实实现会让它们真的读写文件。
- 会话改为通过 `conversation.tool_provider = executor.get_tool_definitions` 每次请求取工具；`set_tools()` 仍可用（子 agent 继续用它）。
- 顺带修复：`search_code` 的 schema 标明 `directory` 可选，但函数要求必填，模型省略时必然失败；`builtin.py` 用适配函数默认 `"."`。
- `hashline_edit` 的 tier 由“未登记→exec”改为 `write`；三种审批模式下的行为不变。

**提交：** `8a8dec0`

### 任务 0.2 · 抽出统一的 agent 循环

**为什么：** 修复 E14；为取消、参数容错、截断、hooks、并行执行提供唯一挂载点。

**文件：** 新建 `neow/core/agent_loop.py`；修改 `neow/core/conversation.py`、`neow/tui/bridge/controller.py`、`neow/cli/repl.py`（只改调用方式）

**设计：**
```python
class CancelToken:           # threading.Event 包装
    def cancel(self); def cancelled(self) -> bool; def raise_if_cancelled(self)

class AgentLoop:
    def run(self, conversation, user_input, *, cancel: CancelToken,
            on_event: Callable[[LoopEvent], None]) -> Generator[StreamChunk]
```
- 单一实现：流式请求 → 收集 → 执行工具 → 追加结果 → 循环；`get_response()` 变成消费 `run()` 的薄包装。
- 进度事件带 **`call_id`**（`tool_start/tool_end` 增加 `id` 字段；修复 E13 的前提）。
- 所有退出路径（正常、异常、取消、`GeneratorExit`）在 `finally` 中调用 `repair_history()`：给缺失结果的 `tool_call` 补 `"Error: cancelled before execution"`。
- 提供 `validate_history(messages) -> list[str]`（返回问题列表），测试统一使用。
- 最大迭代数 `agent.max_turns`（默认 50）防止死循环，触发时以 SystemCard/警告结束。

**步骤：**
- [x] 先为现有两条路径写行为测试（工具往返、多工具、无工具、异常工具），确保迁移前后都绿
- [x] 实现 `AgentLoop`、`CancelToken`、`repair_history`、`validate_history`
- [x] `ConversationManager.get_response/get_response_stream` 委托给 `AgentLoop`
- [x] TUI controller 用 `CancelToken`；`ChatScreen` 按 `call_id` 追踪卡片
- [x] 全量回归（643 passed）+ 4 个 PTY 脚本

**测试：** `tests/test_agent_loop.py`（`test_loop_single_implementation_parity`、`test_tool_events_carry_call_ids`、`test_tool_exception_becomes_error_result`、`test_cancel_mid_tools_repairs_history`、`test_generator_close_repairs_history`、`test_cancel_during_content_keeps_partial_answer`、`test_max_turns_stops_loop`、`test_usage_recorded_for_every_request`、`test_validate_and_repair_history`、`test_validate_history_flags_orphan_results`、`test_agent_config_max_turns`）；`tests/tui/test_controller.py::test_controller_passes_cancel_token_and_ids`；`tests/tui/test_app.py::test_same_tool_twice_tracks_cards_by_call_id`

**实现记录（与设计的差异）：**
- 非流式 `get_response()` 不是“消费流式 run()”，而是同一个循环换一个请求适配器：`chat()` 的结果被包装成单个 chunk。原因：大量测试只 mock 了 `client.chat`，`MagicMock().chat_stream()` 迭代为空。
- `run()` 是生成器，最终回复放在 `loop.result`（不用 `StopIteration.value`）。
- `CancelToken` 通过 `get_response_stream(..., cancel=token)` 传入；TUI 的 Esc 同时设置令牌并关闭生成器。正在执行的命令本身仍要等它结束（真正终止进程是任务 1.5）。
- 新增 `agent.max_turns` 配置（默认 50）；达到上限时发出 `progress.type == "notice"`，TUI 显示为 SystemCard，REPL 用 `print_warning`。
- 行为修正（有测试锁住）：
  - **token 用量按每次请求累计**。旧代码只记录工具循环中最后一次请求的用量，带工具的回合费用被低估。
  - 流式输出中途取消时，已收到的部分回复作为 assistant 消息保留，避免连续两条 user 消息。
  - 推理在一次请求结束时若仍未闭合，补发 `reasoning_end`（之前推理后直接调用工具时，TUI 的思考卡片会一直挂着）。
  - `reasoning_content` 只在客户端提供字符串时回传（旧代码对 MagicMock 等对象也会写入）。
- 工具参数 `json.loads` 仍未加保护（任务 1.3）；但现在解析失败时历史会被修复为合法状态。

**提交：** `0d6fe51`

---

## 阶段 1 · 正确性

### 任务 1.1 · Provider 适配层（Anthropic 格式转换 + 图片）

**修复：** E1、E2、E11。

**文件：** 新建 `neow/models/adapters.py`；修改 `neow/models/anthropic.py`、`openai.py`、`deepseek.py`；测试 `tests/test_adapters.py`、`tests/test_provider_contract.py`

**设计：**
- `to_anthropic(messages, tools) -> (messages, tools)`：
  - 工具：`{"name", "description", "input_schema"}`。
  - assistant 的 `tool_calls` → `content` 中的 `tool_use` 块（`input` 为解析后的 dict；解析失败时用 `{}` 并记录 warning）。
  - 连续的 `role:"tool"` 消息合并成**一条** `role:"user"` 消息，内容为多个 `tool_result` 块（Anthropic 要求结果紧跟在 tool_use 之后的同一条 user 消息里）。
  - 相邻同角色消息合并；去掉 `reasoning_content`、`type` 等非标准字段。
- `to_openai(messages)`：Anthropic 风格图片块 → `{"type":"image_url","image_url":{"url":"data:<mime>;base64,..."}}`。
- Anthropic 流式：按 `event.index` 维护 `index -> tool buffer`，修复 E2。
- 契约测试**不 mock 转换逻辑**：构造包含文本、单工具、并行双工具、工具错误、图片的标准对话，断言转换结果满足各 API 的结构约束（用手写的最小 schema 校验器；可选：设置 `NEOW_LIVE_TESTS=1` 时对真实 API 跑一次冒烟）。

**步骤：**
- [x] 先写失败测试：旧代码发给 Anthropic 的请求有 34 处结构问题（OpenAI 格式工具、`role:"tool"`、空文本块、角色重复）；OpenAI/DeepSeek 收到 Anthropic 格式图片
- [x] 实现 `adapters.py` 与三个客户端接入
- [x] 修复流式多工具缓冲；测试并发 `tool_use` 的参数各自正确（旧代码抛 `JSONDecodeError`）
- [x] `/image` 在 OpenAI 路径上的转换测试
- [ ] 可选 live 冒烟测试（默认跳过）——未做：本环境没有 API key，留到有 key 时补

**测试：** `tests/test_provider_contract.py`（参考对话 × Anthropic/OpenAI/DeepSeek × chat/chat_stream，共 7 个）；`tests/test_adapters.py`（`test_anthropic_tools_have_input_schema`、`test_tool_results_merged_into_single_user_message`、`test_empty_assistant_text_and_empty_results_are_normalised`、`test_malformed_arguments_become_empty_input`、`test_openai_image_block_converted_and_extra_keys_dropped`、`test_anthropic_stream_parallel_tool_inputs`）

**实现记录：**
- 契约校验器是手写的结构规则（角色、交替、tool_use/tool_result 配对与顺序、空文本块、多余字段），不是官方 schema；它能抓住本次发现的全部问题，但不能替代真实 API 冒烟。
- OpenAI 客户端现在会去掉非标准字段（`reasoning_content`、工具消息上的 `type`）；DeepSeek 保留这两个（思考模式需要回传 `reasoning_content`）。
- 发给 Anthropic 的工具结果以 `Error:` 开头时带 `is_error: true`；空结果填 `(no output)`；内容为空的 assistant 消息被丢弃，相邻同角色消息合并。
- 顺带修复：Anthropic 流式下无参数工具（如 `git_status`）没有参数增量，旧代码产出空字符串参数，后续 `json.loads("")` 失败；现在默认 `"{}"`。
- `max_tokens` 仍为 4096（任务 1.2）。

**提交：** `7c13a7b`

### 任务 1.2 · 输出上限可配置 + 截断处理

**修复：** E3。

**文件：** `neow/core/config.py`、`neow/models/*.py`、`neow/core/agent_loop.py`

**设计：**
- 配置 `models.<name>.max_output_tokens`，默认：anthropic 16000，openai 16000，deepseek 8192（可被覆盖）。
- 客户端在最后一个 `StreamChunk` 上透出 `finish_reason`（统一为 `stop | tool_calls | length`）。
- 循环处理 `length`：
  - 若有未完成的工具调用 → 不执行，写入工具结果 `"Error: output was truncated (max_output_tokens). Split the change into smaller edits."`，继续循环让模型重试；
  - 若是纯文本 → 发出警告事件（TUI 显示 SystemCard），不自动续写。

**测试：** `tests/test_output_limits.py`（`test_anthropic_default_output_limit` ×3、`test_max_output_tokens_from_config`、`test_invalid_max_output_tokens_is_rejected`、`test_openai_style_output_limit_parameters` ×4、`test_anthropic_reports_normalised_finish_reasons`、`test_length_finish_with_tool_call_returns_error_result` ×2（流式/非流式）、`test_length_finish_text_emits_warning`、`test_normal_tool_turn_has_no_truncation_notice`）

- [x] 已完成（670 passed）

**实现记录（与设计的差异）：**
- 默认值不按 provider 一刀切：
  - Anthropic 必须传 `max_tokens`：Claude 4 及以后 16000；`claude-3-5/3-7` 8192；其余 `claude-3` 4096（这些型号的硬上限，超出会 400）。
  - DeepSeek 8192（API 不传时默认只有 4096）。
  - OpenAI 与兼容端点**默认不传**：API 默认就是模型自身上限，硬塞 16000 会让输出上限更小的模型报错。配置后 OpenAI 用 `max_completion_tokens`（推理模型只认这个），设置了 `base_url` 的兼容端点用 `max_tokens`。
- 只有配置了 `max_output_tokens` 时工厂才向客户端传这个参数，旧配置的构造调用与改动前完全一致（`test_legacy_config_behavior_unchanged` 不需要修改）。
- Anthropic 流式改为从最终消息读取真实的 `stop_reason`（旧代码根据“有没有工具调用”自己拼 `tool_use/end_turn`，看不到 `max_tokens`）。各客户端统一用 `normalize_finish_reason()` 输出 `stop | tool_calls | length`。
- 截断且带工具调用时，这一批调用**全部**不执行（最后一个必然残缺，不去猜其余是否完整），写入 `TRUNCATED_RESULT` 后继续循环，计入 `agent.max_turns`。
- 面向用户的提示改为中文（包括任务 0.2 的轮数上限提示）；给模型看的工具结果保持英文。
- README 补充 `max_output_tokens` 与 `agent.max_turns`。

**提交：** `ed7508a`

### 任务 1.3 · 工具调用容错

**修复：** E4。

**设计（在 `AgentLoop._execute_one`）：**
- 参数 JSON 解析失败 → 工具结果 `Error: invalid JSON arguments (<msg>). Re-issue the call with valid JSON.`
- 未知工具 → `Error: unknown tool '<name>'. Available: ...`（列出前 20 个）
- 参数不匹配（`TypeError`）→ 用 schema 的 `required` 字段生成提示
- 统一使用 `ToolError` 子类区分 `denied / invalid / failed`，TUI 用它决定图标（denied 走 ⊘）

**测试：** `tests/test_tool_errors.py`（`test_bad_json_arguments_become_tool_error`、`test_empty_arguments_mean_no_arguments`、`test_non_object_arguments_are_rejected`、`test_unknown_tool_lists_available`、`test_missing_required_param_message`、`test_unexpected_param_message`、`test_valid_call_still_runs`、`test_denied_call_is_reported_as_denied`、`test_tool_end_reports_status` ×2）；`tests/tui/test_controller.py::test_tool_status_drives_error_and_denied_flags`；`tests/tui/test_cards.py::test_tool_denied_flag_overrides_result_text`

- [x] 已完成（682 passed）

**实现记录（与设计的差异）：**
- 参数校验放在 `ToolExecutor.execute()` 而不是循环里（`check_arguments()`），所有调用方都受益；用 schema 的 `required` 加 `inspect.signature` 判断缺失/多余参数，**在安全检查和审批之前**完成，不会为必然失败的调用弹审批窗。函数接受 `**kwargs` 时不报“多余参数”。
- 新增 `ToolNotFound` / `ToolInvalidArguments` / `ToolDenied`（都继承 `ToolError`，原有 `pytest.raises(ToolError, match=...)` 不受影响）。安全拦截、用户拒绝、无审批回调都归为 `ToolDenied`。
- 循环解析参数：空字符串视为无参数；非法 JSON、非对象 JSON 都变成给模型的错误结果，回合继续。
- `tool_end` 进度事件新增 `status: ok | error | denied`；TUI 控制器优先用它（缺省时回退到旧的字符串判断），安全拦截现在也显示 ⊘。
- 只有 `status == ok` 时才刷新上下文文件。

### 任务 1.4 · 重试与退避

**修复：** E6。

**文件：** 新建 `neow/models/retry.py`；三个客户端接入。

**设计：**
- 可重试：HTTP 408/409/429/5xx、连接错误、超时（按各 SDK 的异常类型判断，`anthropic.APIStatusError` / `openai.APIStatusError` 的 `status_code`）。
- 指数退避 + 抖动：1s、2s、4s，最多 3 次；遵守 `retry-after` 头。
- **流式只在首个 chunk 产出前重试**；已开始输出后的失败直接上抛（避免重复内容）。
- 重试时发事件 `retrying(attempt, delay, reason)`，TUI 状态栏显示“重试中 2/3”。
- 配置 `models.retry: {max_attempts: 3, base_delay: 1.0}`。

**测试：** 用假客户端注入异常：`test_retry_on_429_then_success`、`test_no_retry_on_400`、`test_stream_no_retry_after_first_chunk`、`test_retry_after_header_respected`

### 任务 1.5 · 真正的取消 + 命令执行改造

**修复：** E7。

**文件：** `neow/tools/command.py`、`neow/core/agent_loop.py`、`neow/tui/bridge/controller.py`

**设计：**
- `execute_command` 改为 `Popen`（新进程组，`start_new_session=True`），轮询 `CancelToken`；取消时先 SIGTERM 进程组，1 秒后 SIGKILL（Windows 用 `CTRL_BREAK_EVENT` / `taskkill /T`）。
- 默认超时 120s，参数 `timeout` 上限 600s（配置 `tools.command.max_timeout`）。
- 输出边读边收集，超长按任务 2.1 截断。
- Esc 时：流式阶段立即关闭流；工具阶段终止当前进程；`repair_history` 保证历史合法。

**测试：** `test_cancel_kills_running_command`（`sleep 30` 在 1 秒内被终止）、`test_cancel_then_new_turn_history_valid`、`test_default_timeout_120`

---

## 阶段 2 · 上下文效率

### 任务 2.1 · 工具输出统一截断 + `read_file` 分页

**修复：** E5。

**设计：**
- `AgentLoop` 写入历史前统一调用 `truncate_tool_output(text, limit)`：默认 30,000 字符；超出时保留前 60% 与后 40%，中间插入 `\n… [truncated N chars; re-run with narrower scope] …\n`。UI 收到的事件仍可拿到完整输出（用于展开查看）。
- `read_file(file_path, offset=1, limit=2000)`：输出带行号（`{n:>6}\t{line}`），单行超过 2,000 字符时截断；文件超过 limit 时末尾提示总行数与下一个 offset。哈希行（hashline）仍基于**全文件**计算。
- 系统提示说明：行号前缀不是文件内容，编辑时不要带上。
- 二进制文件检测（含 NUL 字节）→ 返回提示而不是乱码。

**测试：** `test_tool_output_truncated_head_tail`、`test_read_file_offset_limit_numbered`、`test_read_file_binary_detected`、`test_edit_after_numbered_read_still_matches`

### 任务 2.2 · 稳定系统提示 + 提示缓存

**修复：** E8、E9。

**设计：**
- **system = 静态部分**：角色与原则、工具使用指南、平台信息、项目记忆（阶段 3）、项目结构摘要（会话开始时生成一次，长期保留——修复 E9）。会话内不变；`/model` 切换或 `/clear` 时才重建。
- **动态上下文移出 system**：`/add` 的文件、web 内容、按输入匹配的相关文件、git 状态变化，作为 `<context>…</context>` 块**附加在当次 user 消息开头**；同一份内容已发送过且未变化则不重复发送（按内容哈希去重）。
- Anthropic：在 tools 末尾、system 末尾、倒数第二条 user 消息上设置 `cache_control: {"type": "ephemeral"}`（最多 4 个断点）。
- `TokenTracker` 记录 `cache_read_input_tokens` / `cache_creation_input_tokens`（Anthropic）与 `prompt_cache_hit_tokens`（DeepSeek），计价分开；`/cost` 显示缓存命中率。

**测试：** `test_system_prompt_stable_across_turns`、`test_context_files_attached_to_user_turn_once`、`test_project_structure_persists_after_first_turn`、`test_anthropic_cache_control_breakpoints`、`test_tracker_counts_cached_tokens`

### 任务 2.3 · 准确的上下文用量

**修复：** E15。

**设计：**
- 当前上下文大小 = 最近一次请求返回的 `prompt_tokens + completion_tokens`（provider 真实值）；无值时才回退到估算。
- 配置 `models.<name>.context_window`（内置常见模型默认值表：Claude 200k、GPT-4o 128k、DeepSeek 128k；未知模型 128k）。
- `ChatScreen.refresh_status()` 调用 `status_bar.set_context(pct)`；REPL 在用量行显示百分比。
- 自动压缩阈值（80%）改用这个真实值。

**测试：** `test_context_pct_from_usage`、`test_status_bar_shows_ctx`、`test_auto_compact_uses_real_usage`

### 任务 2.4 · 提示词与工具集清理

**修复：** E16。

**设计：**
- 删除 `TOOL_USAGE_PROMPT` 中与 schema 重复的参数说明，只保留“何时用哪个工具”的策略性指导。
- 安全段落改为与审批模式一致的表述：“需要确认的操作由系统审批机制处理；不要在回复里要求用户手动确认”。
- **先读后改**：executor 记录本会话 `read_file` 过的路径与哈希；`edit_file` / `hashline_edit` 对未读或已变更的文件返回错误，提示先读取（与 Claude Code 行为一致）。`write_file` 覆盖已存在文件同样要求先读。
- 工具描述统一为英文、动词开头、说明返回格式。

**测试：** `test_edit_requires_prior_read`、`test_edit_rejects_stale_file`、`test_prompt_has_no_duplicate_param_docs`

---

## 阶段 3 · 项目记忆

### 任务 3.1 · 加载 `AGENTS.md` / `NEOW.md` + `/init`

**设计：**
- 查找顺序（全部加载、按顺序拼接，越具体越靠后）：
  1. 用户级：`~/.neow/NEOW.md`
  2. 从 git 根目录到当前目录的每一级：`AGENTS.md`、`NEOW.md`（同目录两者都有则都加载）
- 支持 `@path/to/file.md` 导入（最多 5 层，防循环）。
- 总量上限 40k 字符，超出时警告并截断最上层的内容。
- 内容放入静态 system 段（与任务 2.2 配合，可被缓存）。
- `/init`：扫描仓库（README、包管理文件、测试命令、lint 配置、目录结构），让模型生成 `AGENTS.md` 草稿，写入前走审批与 diff 预览。
- `/memory`：显示已加载的文件列表与大小；`/memory add <text>` 追加到项目 `NEOW.md`。
- TUI：侧栏 Context 页显示“已加载的记忆文件”。

**测试：** `test_memory_files_discovered_in_order`、`test_memory_import_depth_limit`、`test_memory_in_system_prompt`、`test_init_generates_agents_md_via_approval`

---

## 阶段 4 · 生态

### 任务 4.1 · 搜索工具：`grep` / `glob` / `list_dir`

**设计：**
- `grep(pattern, path=".", glob=None, output_mode="files_with_matches|content|count", context=0, case_insensitive=False, head_limit=100)`：优先调用 `rg --json`；无 `rg` 时回退到 Python 实现。两者都遵守 `.gitignore`（回退实现用 `git ls-files --cached --others --exclude-standard`，非 git 目录用现有 `SKIP_DIRS`）。
- `glob(pattern, path=".")`：按修改时间倒序，最多 200 条。
- `list_dir(path=".", depth=1)`：树形输出，忽略规则同上。
- `search_code` 保留为 `grep` 的别名一个版本，并在 schema 描述中标注 deprecated。
- 三者都是 `read_only=True`、tier read。

**测试：** `test_grep_uses_ripgrep_when_available`、`test_grep_python_fallback_respects_gitignore`、`test_glob_sorted_by_mtime`、`test_list_dir_depth`

### 任务 4.2 · 任务清单工具 `todo_write`

**设计：**
- 工具 `todo_write(todos: [{id, content, status: pending|in_progress|completed}])`，全量覆盖式更新；同一时刻最多一个 `in_progress`。
- 状态存在 `conversation.todos`，随会话保存/恢复。
- 系统提示指导：3 步以上的任务先建清单，完成一项立即标记。
- TUI：时间线中渲染 `TodoCard`（原地更新，不重复插入）；侧栏新增 Todo 页。REPL：打印紧凑清单。

**测试：** `test_todo_write_validates_single_in_progress`、`test_todos_persist_in_session`、`test_tui_todo_card_updates_in_place`

### 任务 4.3 · 子 agent 工具化（`task`）

**修复：** E12。

**设计：**
- 工具 `task(description, prompt, agent_type="explore"|"general")`：
  - `explore`：只能用 `read_only` 工具（registry.subset），适合并行调研，结果只返回最终总结文本。
  - `general`：使用与主 agent **相同的审批策略与回调**（不是 yolo），审批弹窗标注“来自子 agent: <description>”。
- 子 agent 有独立上下文、独立 `max_turns`（默认 25）、可被父级 `CancelToken` 取消；禁止嵌套 `task`（深度 1）。
- 子 agent 的 token 计入会话总成本，`/cost` 分项显示。
- `ArchitectOrchestrator` 改为：规划器输出计划 → 生成 todo（任务 4.2）→ 主 agent 按序执行，调研类子任务并行派给 `explore`。删除并发写文件的路径。配置 `architect.subagent_approval` 仅允许 `inherit`（默认）或显式 `yolo`。
- TUI：`task` 工具卡片内显示子 agent 的工具调用计数与当前步骤。

**测试：** `test_explore_subagent_has_only_read_only_tools`、`test_general_subagent_uses_parent_approval`、`test_subagent_cancelled_with_parent`、`test_no_nested_task`、`test_architect_no_parallel_writes`

### 任务 4.4 · 并行执行只读工具

**设计：**
- 同一轮的多个工具调用全部为 `read_only` 时，用线程池并行执行（上限 8）；否则按顺序执行。结果按原始顺序写回历史。
- 审批仍逐个经过 `execute()`（只读工具一般无需审批）。
- 事件按 `call_id` 发出（依赖 0.2），TUI 同时显示多张运行中卡片。
- 系统提示：鼓励在一次回复中并行发起互不依赖的读取/搜索。

**测试：** `test_parallel_read_only_calls_run_concurrently`（用 `sleep` 计时）、`test_mixed_calls_run_sequentially`、`test_results_preserve_call_order`

### 任务 4.5 · MCP 客户端

**新依赖：** `mcp`（官方 Python SDK）。

**设计：**
- 配置来源（合并，后者覆盖前者）：`~/.neow/config.json` 的 `mcp.servers`、项目根 `.mcp.json`（格式兼容 Claude Code：`{"mcpServers": {"name": {"command", "args", "env"} | {"type": "http", "url", "headers"}}}`）。
- 传输：stdio、streamable HTTP。SDK 是 async 的：在专用后台线程运行一个事件循环，对外提供同步调用接口（带超时）。
- 工具名 `mcp__<server>__<tool>` 注册进 `ToolRegistry`（`source="mcp:<server>"`）；默认 tier exec（需要审批），服务器配置 `trusted: true` 或工具注解 `readOnlyHint` 时可降级。
- 项目级 `.mcp.json` 中的服务器首次启动前需用户确认（防止仓库投毒）。
- 启动失败不影响主程序：标记为 failed，`/mcp` 显示状态、错误与工具列表，支持 `/mcp reconnect <name>`。
- MCP 资源与 prompts 先不做（后续任务）。

**测试：** 用一个测试内的最小 stdio MCP 服务器（`tests/fixtures/mcp_echo_server.py`）：`test_mcp_tools_registered_with_prefix`、`test_mcp_call_roundtrip`、`test_mcp_server_failure_is_isolated`、`test_project_mcp_requires_confirmation`、`test_mcp_tools_require_approval_by_default`

---

## 阶段 5 · 安全

### 任务 5.1 · 可配置 hooks

**设计（语义对齐 Claude Code，降低用户迁移成本）：**
- 事件：`user_prompt_submit`、`pre_tool_use`、`post_tool_use`、`stop`、`session_start`。
- 配置：`hooks.<event>: [{"matcher": "<正则，匹配工具名>", "command": "<shell>", "timeout": 30}]`。
- 输入：JSON 经 stdin 传给命令（`session_id`、`cwd`、`tool_name`、`tool_input`、`tool_output`）。
- 退出码：`0` 继续（stdout 可选 JSON：`{"decision": "block", "reason": ...}` / 修改后的 `tool_input`）；`2` 阻止，stderr 作为工具结果回给模型；其他非零只记录警告。
- 在 `AgentLoop` 中调用；`pre_tool_use` 在审批**之前**运行（hook 可以直接拒绝）。
- 现有 `EventBus` 保留给 Python 插件，并让它也能收到这些事件。

**测试：** `test_pre_tool_hook_blocks_with_exit_2`、`test_hook_can_rewrite_input`、`test_hook_timeout_does_not_block_loop`、`test_post_tool_hook_receives_output`

### 任务 5.2 · 文件回退点 `/rewind`

**设计：**
- 每个回合开始时创建检查点；每次改文件的工具执行**前**，若该文件在本回合尚未备份，就把原内容（或“不存在”标记）存到 `~/.neow/checkpoints/<session>/<turn>/`。
- `/rewind`：列出回合（用户输入摘要 + 改动文件数），选择后可选“只恢复文件 / 只回退对话 / 两者都回退”；对话回退复用 session tree 的分支机制。
- 与 git 自动提交并存：rewind 不改 git 历史，只改工作区文件。
- 只跟踪通过工具修改的文件；`execute_command` 造成的改动明确提示“无法回退”。
- 按会话保留最近 50 个检查点，超出自动清理。

**测试：** `test_checkpoint_before_first_mutation_in_turn`、`test_rewind_restores_and_deletes_created_files`、`test_rewind_conversation_branches_session_tree`

### 任务 5.3 · 命令沙箱（实验，可选）

**设计：**
- `tools.command.sandbox: off | auto | strict`（默认 off）。
- Linux：`bwrap` 只读挂载根目录、可写挂载工作区与临时目录、`--unshare-net`（可配置是否放行网络）；macOS：`sandbox-exec` profile；不可用时 `auto` 回退并提示，`strict` 拒绝执行。
- 审批弹窗显示命令是否在沙箱中运行。

**测试：** 在有 `bwrap` 的环境运行（否则 skip）：`test_sandbox_blocks_write_outside_cwd`、`test_sandbox_blocks_network`

---

## 阶段 6 · 自动化

### 任务 6.1 · 无头模式结构化输出

**设计：**
- `neow -p "<prompt>" --output-format text|json|stream-json`：
  - `json`：结束时输出 `{result, session_id, usage, cost, num_turns, is_error}`
  - `stream-json`：每行一个事件（与 `AgentLoop` 事件一一对应）
- `--allowed-tools "read_file,grep,..."`、`--disallowed-tools`、`--max-turns N`；无头模式下需要审批的工具默认拒绝，除非 `--approval yolo`。
- 退出码：0 成功；1 模型/工具错误；2 参数错误；130 被中断。
- 文档：`README.md` 增加 CI 用法示例（GitHub Actions）。

**测试：** `test_headless_json_schema`、`test_stream_json_events_order`、`test_allowed_tools_filter`、`test_headless_denies_approval_tools_by_default`

---

## 不在本计划内（记录以免遗漏）

- Repo Map / tree-sitter（`CLAUDE.md` 已暂缓，原因不变）。
- IDE 集成、Web UI。
- MCP 资源 / prompts / sampling（4.5 之后再评估）。
- 多会话并行 / git worktree 隔离。

## 完成定义（每个任务）

- [ ] 新增测试先失败后通过；全量测试通过且数量不少于基线
- [ ] `flake8` 对改动文件无报错
- [ ] 涉及 TUI 的任务：`tests/tui/pty_*.py` 四个脚本通过
- [ ] 文档同步（prompts schema、`help.py`、`README.md`、`CLAUDE.md` 勾选）
- [ ] 单独 commit，信息说明“修复了哪个 E 编号 / 新增了什么能力”
