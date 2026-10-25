# 技术评估与设计方案：写操作安全并发调度

## 1. 背景与现状

在 Neow v0.9 之前，只有标记为 `read_only=True` 的工具（如 `read_file`、`list_dir`、`grep`、`glob`、`search_code`）以及只读子代理（`agent_type="explore"`）可以在同一轮会话中并行执行。任何涉及写操作的工具调用（如 `write_file`、`edit_file`、`create_file`、`delete_file`）均强制串行执行。

随着多文件操作场景（如跨文件批量重构、脚手架项目生成、多测试文件更新）的增多，串行执行会导致显著的 I/O 延迟。因此，需要评估将并发执行范围安全扩大到写操作的可行性与安全边界。

---

## 2. 安全边界与风险分析

将并发扩大到写操作必须严格满足以下四个安全边界：

### 2.1 审批策略边界（Approval Boundary）
- **原则**：需要人工交互审批的工具调用绝对不能在后台 Worker 线程中并发执行。
- **原因**：并发触发弹窗会导致多重审批冲突、阻塞其他线程或界面死锁。
- **规则**：仅当调用处于免审批状态（`ApprovalMode.YOLO`，或用户在配置中显式指定 `tools.approval.<tool>: allow`）且 `check_approval().needs_approval is False` 时，才可考虑并发。

### 2.2 目标文件互斥（Disjoint Target Files）
- **原则**：若同一轮中存在多个写操作作用于**相同文件路径**（如连续两次 `edit_file` 或 `hashline_edit`），必须保持严格的时序因果关系，严禁并发。
- **原因**：并发修改同一文件会引发写写竞态（Write-Write Race Condition）、内容覆盖或 Hashline 锚点失效。
- **规则**：并发执行的一批写操作，其规范化后的绝对路径集合必须互不相交（`len(targets) == len(set(targets))`）。

### 2.3 检查点隔离（Checkpoint Isolation）
- **原则**：每个文件的写操作在落盘前均需执行 `checkpoints.before_mutation(file_path)`。
- **保障**：Neow 的 `CheckpointsManager` 基于文件相对/绝对路径组织备份。不同文件的快照目录各自独立，因此只要目标文件不重叠，快照备份过程天然线程安全。

### 2.4 副作用不可预测工具屏障（Side-Effect Barrier）
- **原则**：`execute_command` 等任意 shell 指令可能对文件系统、进程、网络产生任意不可预知的副作用。
- **规则**：`execute_command` 必须作为 Barrier（串行屏障），禁止与任何写操作并发。

---

## 3. 架构设计与实现

### 3.1 目标文件提取器 (`extract_target_file`)
从工具参数中提取规范化的目标文件路径（`resolve()`），支持 `write_file`、`create_file`、`edit_file`、`delete_file` 及未来文件类工具。

### 3.2 批次并发调度器 (`can_batch_run_concurrently`)
在 `ToolExecutor` 中增加批次级调度判定逻辑：
1. 校验批次内所有工具规格，确认非只读工具均为声明 `mutates_files=True` 的受控工具；
2. 逐一校验审批策略，若存在任一需要交互审批的调用，整批拒绝并发；
3. 提取所有写操作的目标文件，检测重叠。若存在路径重叠，整批退回串行保证时序；
4. 若全部通过，允许在 `ThreadPoolExecutor` 中并发安全执行。

---

## 4. 评估结论

将只读工具并行范围扩大到互不相交、免审批的受控文件写操作，在保持系统数据一致性与安全门禁的同时，大幅提升了批量文件写入和多模块生成场景的吞吐性能。
