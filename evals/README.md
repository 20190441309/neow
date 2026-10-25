# Eval 套件

对应路线图任务 19（质量与评测体系）。目的：用固定任务集 + 自动打分，在不调用真实模型
API 的前提下，保护端到端的工具执行链路（文件 I/O、read-before-edit 守卫、approval、
checkpoint）不被回归破坏。

## 设计取舍

- **默认 scripted，不是 live**：每个任务用 `ScriptedClient`（见
  `tests/test_agent_loop.py`）回放预先写好的模型回复，驱动真实的
  `neow -p ... --output-format json --approval yolo` headless 流程。免费、确定、可在
  CI 跑。代价是不评估模型本身的推理质量——它验证的是"工具链路是否按预期执行"，不是
  "模型能不能想出正确的修复方案"。
- **打分方式**：每个任务跑完后，在产出的临时工作目录里做两层检查——① 直接读文件断言
  内容；② 用子进程 `python -c "..."` 实际跑一下产出的代码，确认真的能工作（不是字符串
  碰巧匹配）。

## 运行方式

```bash
python -m evals.runner            # 人类可读的表格，任一失败则 exit 1
python -m evals.runner --json     # JSON 报告（给脚本/CI 用）
```

同一套任务也作为 `tests/test_evals.py` 的一部分跑在 `pytest` 里，所以 `pytest` 和
CI 会自动覆盖到。

## 加任务

在 `evals/tasks.py` 的 `TASKS` 里追加一个 `EvalTask`：

- `setup`：运行前要写到工作目录的文件（dict：相对路径 -> 内容）。
- `prompt`：发给模型的任务描述。
- `replies`：`ScriptedClient` 要回放的回复列表——**每一轮模型请求消耗一条**，包括
  工具调用轮和最后的纯文本收尾轮。`edit_file` / `write_file` / `hashline_edit`
  要求同一轮会话里先 `read_file` 过同一个文件（read-before-edit 守卫），脚本顺序要
  符合这个约束。
- `check`：`Callable[[Path], tuple[bool, str]]`，在跑完之后对工作目录做断言，返回
  `(是否通过, 说明文字)`。

## 失败案例库

`evals/failures/` 记录真实使用中发现、现有单测/eval 都没覆盖到的 bug，并转成
`EvalTask(..., category="regression")`。流程见 `evals/failures/README.md`。目前是
空的——没有编造案例填充，等真实发生再记。

## Live 模式（真实模型评测）

- **Live 模式（已支持）**：通过 `--live`（及可选 `--model <name>`）用真实配置好的模型 API 替换 `ScriptedClient`，跑同一套任务集评估真实代码推理与改写质量：
  ```bash
  python -m evals.runner --live
  python -m evals.runner --live --model claude
  ```
  由于调用真实 API 会产生费用且具有非确定性，默认不进 CI 门禁，供版本发布前的人工评测与质量基准抽查。

## 后续规划
- **tree-sitter repo map 的必要性评估**：等任务集和失败案例库积累到足够规模（尤其
  是大型 monorepo 场景）后，用真实数据判断是否值得引入。
- **失败案例库**：把实际使用中发现的 bug（prompt + 期望 + 实际）转成新的 `EvalTask`，
  防止同类回归。
