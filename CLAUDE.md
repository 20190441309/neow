# Neow CLI 开发路线图

> 目标：对标 Aider，逐步构建专业的 AI 结对编程工具
> 当前覆盖率：~50% | P0 已完成

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
- [ ] Repo Map — 用 tree-sitter 生成项目结构摘要，注入上下文（P1）

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
- [ ] 引入 tree-sitter 做 AST 级别的代码理解
- [ ] 生成 Repo Map（函数/类/方法索引）

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

- [x] `allowed_commands` 白名单真正生效
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

---

## 里程碑规划

| 里程碑 | 包含 | 预计覆盖率 | 状态 |
|--------|------|-----------|------|
| v0.2 | P0 全部（Git + Streaming + 上下文 + 编辑精度） | ~50% | ✅ 已完成 |
| v0.3 | P1 全部（Context + Architect + Lint + 模型切换） | ~65% | ✅ 已完成 |
| v0.4 | P2 全部（持久化 + Token + 安全 + CLI 增强） | ~80% | ✅ 已完成 |
| v0.5 | P3 全部（Web + 插件） | ~90% | ✅ 已完成 |
