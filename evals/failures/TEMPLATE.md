<!-- 复制为 evals/failures/<yyyy-mm-dd>-<short-slug>.md，填完四项即可。 -->

# <一句话标题>

## Prompt

<触发问题的用户输入，或接近的复现版本>

## Expected

<当时期望的行为>

## Actual

<实际发生的：错误输出 / 异常 / 文件状态错误>

## Root cause

<定位到的根因：文件 + 函数/逻辑>

## 回归测试

- [ ] 已在 `evals/tasks.py` 加入 `EvalTask(id="...", category="regression", ...)`
