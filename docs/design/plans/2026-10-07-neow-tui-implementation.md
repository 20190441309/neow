# Neow TUI 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 `/home/neow` 用 Textual 实现 neow 全屏 TUI（Warp 式卡片时间线 + crush 式乱码 thinking 动效），使其成为默认入口 `neow`，现有 REPL 保留为 `neow --plain`，core 语义与 443 个现有测试零回归。

**架构：** `neow/tui/` 新增 UI 包：ChatScreen 持有 TimelineScroll / InputDock / StatusBar；ChatController 在 worker 线程消费 `ConversationManager.get_response_stream()` 并用事件驱动卡片；ApprovalBridge 用 Future + `call_from_thread` 把同步审批回调桥接到 ApprovalModal；效果引擎（渐变/乱码）与卡片渲染解耦、可单测。入口用纯函数 `select_run_mode()` 分流 TUI/PLAIN/ONESHOT。

**技术栈：** Python 3.10+、Textual 8.x、Rich（既有）、pytest + pytest-asyncio + Textual Pilot。

**规格：** `docs/design/2026-10-07-neow-tui-design.md`（契约副本 `docs/superpowers/specs/2026-10-07-neow-tui-design.md`）。执行者必须两份材料都读；本计划的取值全部来自规格，冲突时以规格为准并回报。

**工作目录与命令约定：** 仓库 `/home/neow`；虚拟环境 `/home/neow/.venv`；所有 pytest 命令统一用 `PATH="/home/neow/.venv/bin:$PATH" .venv/bin/python -m pytest ...`（venv bin 必须在 PATH 上，否则 `test_tools.py::TestCommand` 会因找不到 `python` 失败）。

## 全局约束

- 运行时新依赖仅 `textual>=8.0,<9`；dev 依赖新增 `pytest-asyncio`；不引入其他新依赖。
- core（`neow/core/`、`neow/models/`、`neow/tools/`）不做语义修改；`neow/cli/repl.py`、`neow/utils/formatter.py` 不为 TUI 重构。
- 现有 443 个测试必须保持全绿；每个任务结束跑一次全量回归。
- 非 TTY（stdout 或 stdin 非 TTY）绝不实例化 Textual App；`neow --plain` 行为与改动前逐字节一致。
- 渲染纪律：禁止覆盖 `Widget._render()`（自定义渲染函数命名 `_frame()`）；渐变取色用 `Gradient.get_color(t).hex`，不得用 `.rich_color`。
- `tui.effects` 取值 `full|subtle|off`，默认 `full`；`TEXTUAL_ANIMATIONS=none` 或非 TTY → 强制 `off`；未知值回退默认并 warning。
- UI 文案中文、命令英文；代码风格 black（line-length 88）；Conventional Commits。
- 每个任务独立 commit；禁止把多个任务压进一个 commit。

## 审查重点（Review Focus）

1. **Esc 取消后的续用**：取消后线程/生成器不得残留，紧接着的新回合必须正常；期望无僵尸线程、无串话。→ 测试钉在任务 9（`test_cancel_then_new_turn`）与任务 11（`test_cancel_then_submit_again`）。
2. **极小终端与 resize**：宽 < 72 列或运行中 resize 不得崩溃、输入与滚动仍可用。→ 测试钉在任务 2（`test_narrow_resize_no_crash`）。
3. **超长推理/输出**：≥10k 字符 reasoning 或 ≥30 行工具输出必须截断展示并给出展开提示，不阻塞 UI。→ 测试钉在任务 5（`test_huge_reasoning_truncates`）与任务 7（`test_long_output_truncates_with_hint`）。
4. **审批期间的退出/取消**：审批 Future 悬挂不得阻塞进程退出或下一个回合。→ 测试钉在任务 10（`test_bridge_timeout_denies`、`test_bridge_cancel_denies`）与任务 11（`test_exit_with_pending_approval`）。
5. **忙碌时连续 Enter**：排队必须 FIFO、状态一致、可回取。→ 测试钉在任务 12（`test_queue_fifo_and_pop`）与任务 11（`test_queue_drains_after_turn`）。

---

## 文件结构

**创建：**

| 文件 | 职责 |
|------|------|
| `neow/cli/mode.py` | 纯函数入口分流 `RunMode` / `select_run_mode` |
| `neow/tui/__init__.py` | 包标记、`run_tui()` 导出 |
| `neow/tui/app.py` | `NeowApp`：Screen 栈、主题、全局键位、`run_tui()` |
| `neow/tui/theme.tcss` | 全部颜色 token 与布局样式 |
| `neow/tui/commands.py` | `CommandDispatcher`：27 个 `/命令` 的 TUI 去路 |
| `neow/tui/screens/chat.py` | `ChatScreen`：回合生命周期、队列、卡片编排 |
| `neow/tui/screens/approval.py` | `ApprovalModal`（ModalScreen） |
| `neow/tui/screens/help.py` | `HelpScreen` |
| `neow/tui/screens/model_picker.py` | `ModelPickerScreen` |
| `neow/tui/screens/session_picker.py` | `SessionPickerScreen` |
| `neow/tui/screens/tree.py` | `SessionTreeScreen` |
| `neow/tui/screens/diff_view.py` | `DiffScreen`（diff/commit/undo） |
| `neow/tui/screens/cost.py` | `CostScreen` |
| `neow/tui/widgets/timeline.py` | `TimelineScroll` + `NewMessagesBanner` |
| `neow/tui/widgets/input_dock.py` | `InputDock`：输入/补全/历史/排队 |
| `neow/tui/widgets/status_bar.py` | `StatusBar` + `TopBar` |
| `neow/tui/widgets/logo.py` | `NeowLogo`（渐变标记/启动动画） |
| `neow/tui/widgets/cards/base.py` | `CardBase` |
| `neow/tui/widgets/cards/user.py` | `UserCard` |
| `neow/tui/widgets/cards/assistant.py` | `AssistantCard` |
| `neow/tui/widgets/cards/thinking.py` | `ThinkingCard` |
| `neow/tui/widgets/cards/tool.py` | `ToolCard` + `render_tool_body()` |
| `neow/tui/widgets/cards/system.py` | `SystemCard` + `ErrorCard` |
| `neow/tui/effects/gradient.py` | 渐变工具（`gradient_text` / `gradient_hex`） |
| `neow/tui/effects/scramble.py` | `ScrambleEngine` |
| `neow/tui/bridge/events.py` | TUI 事件 dataclass |
| `neow/tui/bridge/controller.py` | `ChatController` + `ApprovalBridge` |
| `tests/tui/__init__.py` | 包标记 |
| `tests/tui/conftest.py` | `FakeConversation`、`FakeStream`、Pilot 辅助 |
| `tests/tui/test_entry.py` | 入口分流 |
| `tests/tui/test_config.py` | `tui` 配置段 |
| `tests/tui/test_app.py` | App 骨架/状态栏/窄屏 |
| `tests/tui/test_effects.py` | 渐变与乱码引擎 |
| `tests/tui/test_cards.py` | 卡片族 |
| `tests/tui/test_controller.py` | 事件序列/聚合/取消 |
| `tests/tui/test_approval.py` | 审批桥与模态 |
| `tests/tui/test_input_dock.py` | 输入坞 |
| `tests/tui/test_commands.py` | 命令分发 |
| `tests/tui/test_screens.py` | 功能屏与侧栏 |
| `tests/tui/pty_smoke.py` | PTY 三入口冒烟脚本（手动/CI 可选） |
| `tests/tui/_fake_launcher.py` | PTY 冒烟用的 fake 客户端启动器 |

**修改：**

| 文件 | 改动 |
|------|------|
| `pyproject.toml` | +`textual>=8.0,<9`；dev +`pytest-asyncio`；pytest `asyncio_mode = "auto"` |
| `neow/core/config.py` | +`tui` property（默认 `{"effects": "full", "sidebar_default": False, "theme": "midnight"}`） |
| `neow/cli/main.py` | +`--plain/--tui` 选项；`select_run_mode()` 分流；TUI 分支接审批桥与 `run_tui()` |
| `README.md` | TUI 用法、`--plain`、配置、动效开关 |

---

### 任务 1：入口模式选择与 CLI flags

**文件：**
- 创建：`neow/cli/mode.py`
- 创建：`tests/tui/__init__.py`、`tests/tui/test_entry.py`
- 修改：`neow/cli/main.py`（click 选项与分流）

- [ ] **步骤 1：编写失败的测试 `tests/tui/test_entry.py`**

```python
from neow.cli.mode import ModeError, RunMode, select_run_mode
import pytest

def _m(**kw):
    base = dict(prompt=None, plain=False, tui=False, stdin_tty=True, stdout_tty=True)
    base.update(kw)
    return select_run_mode(**base)

def test_default_tty_is_tui(): assert _m() is RunMode.TUI
def test_prompt_is_oneshot_even_non_tty(): assert _m(prompt="hi", stdin_tty=False, stdout_tty=False) is RunMode.ONESHOT
def test_plain_flag(): assert _m(plain=True) is RunMode.PLAIN
def test_tui_flag_non_tty_raises():
    with pytest.raises(ModeError): _m(tui=True, stdout_tty=False)
def test_plain_and_tui_conflict():
    with pytest.raises(ModeError): _m(plain=True, tui=True)
def test_no_tty_falls_back_plain(): assert _m(stdout_tty=False) is RunMode.PLAIN
def test_piped_stdin_falls_back_plain(): assert _m(stdin_tty=False) is RunMode.PLAIN
def test_tui_flag_tty(): assert _m(tui=True) is RunMode.TUI
```

- [ ] **步骤 2：运行确认失败**

运行：`... -m pytest tests/tui/test_entry.py -v`
预期：FAIL（`ModuleNotFoundError: neow.cli.mode`）

- [ ] **步骤 3：实现 `neow/cli/mode.py`**

接口（数值规则出自规格 §10，顺序即优先级）：

```python
class RunMode(str, Enum):
    TUI = "tui"; PLAIN = "plain"; ONESHOT = "oneshot"

class ModeError(Exception): ...

def select_run_mode(*, prompt: str | None, plain: bool, tui: bool,
                    stdin_tty: bool, stdout_tty: bool) -> RunMode:
    # 1) plain and tui -> ModeError("--plain 与 --tui 互斥")
    # 2) prompt -> ONESHOT
    # 3) tui and not stdout_tty -> ModeError("--tui 需要 TTY")
    # 4) tui -> TUI
    # 5) plain -> PLAIN
    # 6) stdout_tty and stdin_tty -> TUI
    # 7) 其余 -> PLAIN
```

- [ ] **步骤 4：运行确认通过**

运行：`... -m pytest tests/tui/test_entry.py -v` → PASS

- [ ] **步骤 5：在 `neow/cli/main.py` 加选项与分流**

- click 选项：`--plain`（"Use the classic line REPL"）、`--tui`（"Force the full-screen TUI"），两者互斥时 `raise click.UsageError(...)`（click 退出码 2）。
- `main(...)` 内：读 pipe 输入合并 prompt 后调用 `select_run_mode`；`ONESHOT` 与 `PLAIN` 走现有路径（原样保留）；`TUI` 暂时 `raise click.ClickException("TUI mode lands in task 2")`，任务 2 替换为 `run_tui()`。
- 现有参数 `--file/--message-file/--config/--model/--verbose` 不变。

- [ ] **步骤 6：回归 + Commit**

运行：`... -m pytest -q` → 443 + 8 passed
```bash
git add neow/cli/mode.py neow/cli/main.py tests/tui/__init__.py tests/tui/test_entry.py
git commit -m "feat(cli): add TUI/plain/oneshot entry mode selection"
```

---

### 任务 2：配置 tui 段、依赖、App 骨架与主题、状态栏、PTY 冒烟

**文件：**
- 修改：`pyproject.toml`、`neow/core/config.py`、`neow/cli/main.py`（TUI 分支接真）
- 创建：`neow/tui/__init__.py`、`app.py`、`theme.tcss`、`screens/__init__.py`、`screens/chat.py`、`widgets/__init__.py`、`widgets/status_bar.py`、`widgets/logo.py`
- 创建：`tests/tui/test_config.py`、`tests/tui/test_app.py`、`tests/tui/_fake_launcher.py`、`tests/tui/pty_smoke.py`

- [ ] **步骤 1：安装依赖并写失败测试**

`pyproject.toml`：dependencies + `"textual>=8.0,<9"`；dev + `"pytest-asyncio>=0.23"`；`[tool.pytest.ini_options]` 增 `asyncio_mode = "auto"`。
运行：`.venv/bin/pip install -q -e ".[dev]" textual pytest-asyncio`

`tests/tui/test_config.py`：

```python
def test_tui_config_defaults(tmp_path):
    from neow.core.config import Config
    cfg = Config(tmp_path / "missing.json")
    assert cfg.tui == {"effects": "full", "sidebar_default": False, "theme": "midnight"}

def test_tui_config_unknown_effects_falls_back(tmp_path):
    p = tmp_path / ".neow.json"; p.write_text('{"tui": {"effects": "warp9"}}')
    from neow.core.config import Config
    assert Config(p).tui["effects"] == "full"
```

`tests/tui/test_app.py`（Pilot；`FakeConversation` 在任务 9 的 conftest 中完整化，此任务先放最小 stub）：

```python
async def test_app_mounts():
    app = _chat_app(FakeConversation(script=[]))   # _chat_app 定义于 conftest
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.query_one("#topbar"); assert app.query_one("#statusbar")
        assert app.query_one(ChatScreen)

async def test_narrow_resize_no_crash():
    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.resize_terminal(58, 18); await pilot.pause()
        assert app.query_one("#inputdock")
```

- [ ] **步骤 2：运行确认失败** → `ModuleNotFoundError: neow.tui`

- [ ] **步骤 3：实现骨架**

- `Config.tui`：读取 `self._config.get("tui", {})`，与默认值 merge（`effects` 不在 `{"full","subtle","off"}` 时回退 `full` 并 `logger.warning`；`theme` 非 `midnight` 时回退；`sidebar_default` 强制 bool）。
- `theme.tcss`：写入规格 §8.1 全部 token（CSS 变量）+ 布局（TopBar 1 行 / Body 1fr / QueueStrip auto / InputDock 1–6 / StatusBar 1 行）；宽 <72 的紧凑规则。
- `NeowApp(App)`: `CSS_PATH = "theme.tcss"`；`BINDINGS` 含 `ctrl+q` 退出；构造参数 `conversation, config, token_tracker=None, session_manager=None, approval_policy=None, event_bus=None, plugin_api=None`；`on_mount` push `ChatScreen`。
- `ChatScreen.compose()`：TopBar、TimelineScroll、Sidebar（任务 14 前先占位空容器）、InputDock（占位）、StatusBar。
- `TopBar`：`◆ NEOW · {model} · ⎇ {branch} · ⛨ {mode} · {cwd}`（branch/mode 缺失时省略段）。
- `StatusBar`：`set_tokens(inp, out, cost)`, `set_context(pct)`, `set_activity(text)`；方法用 `Static.update`。
- `NeowLogo`：静态渐变 `NEOW` 标记（`gradient_text` 任务 3 前先用纯色 bold，任务 15 接动画）。
- `neow/tui/__init__.py` 导出 `run_tui(**kwargs) -> None`（在 `app.py` 实现：构造 `NeowApp(...).run()`）。
- `main.py` TUI 分支：构造与现有 `main()` 完全相同的对象图（model client、executor、conversation、token_tracker、session_manager、event_bus、plugin_api、approval_policy），把 `executor.approval_callback` 接到占位拒绝函数（任务 10 换真桥），然后 `run_tui(...)`。

- [ ] **步骤 4：运行测试** → `... -m pytest tests/tui -v` PASS；`... -m pytest -q` 全绿

- [ ] **步骤 5：PTY 冒烟脚本**

`tests/tui/_fake_launcher.py`：用 `unittest.mock.patch` 把 `neow.cli.main.create_model_client` 换成 `FakeClient`（`model="fake"`、`validate_connection()->True`、`chat_stream()` 产出固定 deltas、支持 `set_tools` 等调用），再 `main_mod.main.main(sys.argv[1:], standalone_mode=False)`。
`tests/tui/pty_smoke.py`：用 `pty.spawn` 依次运行
1. `... _fake_launcher.py`（TUI，进入后发 Ctrl+Q）→ 退出码 0
2. `... _fake_launcher.py --plain`（Ctrl-D）→ 退出码 0
3. `... _fake_launcher.py "hi"` → 输出含 fake 回答且退出码 0
运行：`.venv/bin/python tests/tui/pty_smoke.py` → `PTY SMOKE OK`

- [ ] **步骤 6：Commit**

```bash
git add pyproject.toml neow/core/config.py neow/cli/main.py neow/tui tests/tui
git commit -m "feat(tui): app shell, theme, config and entry wiring"
```

---

### 任务 3：效果引擎（渐变 + 乱码）

**文件：**
- 创建：`neow/tui/effects/__init__.py`、`gradient.py`、`scramble.py`
- 创建：`tests/tui/test_effects.py`

- [ ] **步骤 1：编写失败的测试**

```python
import random
from textual.color import Gradient
from neow.tui.effects.gradient import GRADIENT, gradient_hex, gradient_text
from neow.tui.effects.scramble import SCRAMBLE_RUNES, ScrambleEngine

def test_gradient_endpoints():
    assert gradient_hex(0.0) == "#22d3ee"
    assert gradient_hex(1.0) == "#facc15"

def test_gradient_text_styles_every_char():
    t = gradient_text("abc", phase=0.2)
    assert len(t) == 3 and all(s.style for s in t._spans)

def test_scramble_deterministic_with_seed():
    a = ScrambleEngine(rng=random.Random(42))
    b = ScrambleEngine(rng=random.Random(42))
    assert a.frame("settled ", "frontier", phase=0.1).plain == b.frame("settled ", "frontier", phase=0.1).plain

def test_scramble_frontier_chars_from_runeset():
    e = ScrambleEngine(rng=random.Random(1))
    txt = e.frame("ok ", "XXXXXXXX", phase=0.0).plain
    assert txt.startswith("ok ") and len(txt) == 11
    assert set(txt[3:]) <= set(SCRAMBLE_RUNES)

def test_settle_has_no_random_chars():
    e = ScrambleEngine(rng=random.Random(7))
    assert e.settle("final answer", phase=0.3).plain == "final answer"

def test_scramble_disabled_returns_plain():
    e = ScrambleEngine(enabled=False)
    assert e.frame("a", "b", phase=0.0).plain == "a b"
```

- [ ] **步骤 2：运行确认失败** → `ModuleNotFoundError`

- [ ] **步骤 3：实现**

`gradient.py`：
```python
GRADIENT = Gradient.from_colors("#22d3ee", "#a78bfa", "#f472b6", "#facc15")
def gradient_hex(position: float, phase: float = 0.0) -> str   # position/phase 取模 1.0
def gradient_text(text: str, phase: float = 0.0) -> Text        # 忽略换行，逐字符上色
```
`scramble.py`：
```python
SCRAMBLE_RUNES = "0123456789abcdefABCDEF~!@#$%^&*()+=_"
class ScrambleEngine:
    def __init__(self, *, enabled: bool = True, rng: random.Random | None = None,
                 frontier: int = 32, phase_step: float = 0.05)
    def frame(self, settled: str, frontier: str, phase: float) -> Text
        # settled 常规 dim，frontier 逐字符替换为随机 rune + gradient_hex 上色
    def settle(self, text: str, phase: float) -> Text
    def advance(self, phase: float) -> float   # +phase_step 取模 1.0
```
`enabled=False` 时 `frame` 返回 `settled + " " + frontier` 纯文本。

- [ ] **步骤 4：运行确认通过** → `... -m pytest tests/tui/test_effects.py -v` PASS

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/effects tests/tui/test_effects.py
git commit -m "feat(tui): gradient and scramble effect engines"
```

---

### 任务 4：CardBase + User/System/Error 卡片

**文件：**
- 创建：`neow/tui/widgets/cards/__init__.py`、`base.py`、`user.py`、`system.py`
- 创建：`tests/tui/test_cards.py`（先覆盖这三类）

- [ ] **步骤 1：编写失败的测试**

```python
async def test_card_toggle_collapses_body():
    card = UserCard("hello", number=1, timestamp="12:04")
    async with _host(card) as pilot:      # conftest 提供 _host：挂到测试 App
        assert not card.collapsed
        card.toggle(); await pilot.pause()
        assert card.collapsed and not card.body.display

async def test_user_card_preserves_multiline():
    card = UserCard("a\nb", number=1, timestamp="12:04")
    assert "a\nb" in card.body_text()

def test_system_card_levels():
    assert SystemCard("ok").accent == "#38bdf8"
    assert SystemCard("careful", level="warn").accent == "#facc15"

def test_error_card_accent_and_title():
    c = ErrorCard("Test Failure", "2 failed")
    assert c.accent == "#f87171" and "Test Failure" in c.title_text()
```

- [ ] **步骤 2：运行确认失败** → `ImportError`

- [ ] **步骤 3：实现**

```python
class CardBase(Vertical):
    def __init__(self, title: str, *, icon: str = "", meta: str = "",
                 accent: str = "#334155", body=None)
    @property
    def collapsed(self) -> bool
    def toggle(self) -> None
    def set_accent(self, color: str) -> None     # self.styles.border_left = ("heavy", color)
    def set_title(self, *, title=None, icon=None, meta=None) -> None
    def add_body(self, widget) -> None
    def body_text(self) -> str
    def title_text(self) -> str
```
- 结构：标题行 `Static`（icon/title/meta）+ `Vertical.card-body`；`.collapsed .card-body { display: none; }`。
- `UserCard(text, *, number, timestamp)`：accent `#22d3ee`，标题 `❯ You #n · 时间`，正文保留换行。
- `SystemCard(message, *, level="info")`：info `#38bdf8` / warn `#facc15`；正文即可见文本。
- `ErrorCard(title, detail)`：accent `#f87171`，标题 `✗ {title}`。

- [ ] **步骤 4：运行确认通过** → PASS

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/widgets/cards tests/tui/test_cards.py
git commit -m "feat(tui): card base with user/system/error cards"
```

---

### 任务 5：ThinkingCard（乱码动效 + effects 三档）

**文件：**
- 创建：`neow/tui/widgets/cards/thinking.py`
- 修改：`tests/tui/test_cards.py`

- [ ] **步骤 1：编写失败的测试**

```python
def test_thinking_frame_has_settled_prefix_and_frontier(monkeypatch):
    card = ThinkingCard(effects="full", rng=random.Random(3), frontier=8)
    card.append_reasoning("让我确认 tool definitions 的流向 ")
    frame = card._frame().plain
    assert frame.startswith("让我确认 tool definitions 的流向 ")
    assert len(frame) > len("让我确认 tool definitions 的流向 ")

def test_finish_collapses_and_titles_duration():
    card = ThinkingCard(effects="full")
    card.append_reasoning("abc"); card.finish_reasoning(duration=4.2)
    assert card.collapsed and "Thought" in card.title_text() and "4.2s" in card.title_text()

async def test_full_mode_runs_timer_then_stops():
    card = ThinkingCard(effects="full")
    async with _host(card) as pilot:
        assert card._timer is not None
        card.finish_reasoning(duration=1.0); await pilot.pause()
        assert card._timer is None

async def test_off_mode_has_no_timer():
    card = ThinkingCard(effects="off")
    async with _host(card):
        assert card._timer is None and "abc" in card._frame().plain

def test_subtle_mode_uses_spinner_not_runes():
    card = ThinkingCard(effects="subtle")
    card.append_reasoning("text")
    assert not (set(card._frame().plain[4:]) & set(SCRAMBLE_RUNES))

def test_huge_reasoning_truncates():
    card = ThinkingCard(effects="full")
    card.append_reasoning("x" * 10_000)
    assert len(card.body_text()) <= 10_000
    assert card.truncation_hint()      # 返回 "… (+N 字)" 形式字符串
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class ThinkingCard(CardBase):
    def __init__(self, *, effects: str = "full", frontier: int = 32,
                 fps: int = 20, rng: random.Random | None = None)
    def append_reasoning(self, delta: str) -> None
    def finish_reasoning(self, duration: float) -> None
    def _frame(self) -> Text         # settled 前缀 + 乱码/或 spinner 条
    def truncation_hint(self) -> str # > 4000 字正文时返回 "… (+N 字)"
```
- `full`：`set_interval(1/20)` 调 `self.update(self._frame())`；`finish_reasoning` 取消定时器、`self.update(settled)`、`toggle()` 折叠、标题改 `✻ Thought {duration:.1f}s · {chars} 字`。
- `subtle`：乱码条替换为 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` 10fps，正文 dim 正常显示。
- `off`：无定时器，正文静态 dim。
- 空 reasoning 模型（`append_reasoning` 从未调用）：`finish_reasoning` 后标题为 `✻ Working · {duration:.1f}s`。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/widgets/cards/thinking.py tests/tui/test_cards.py
git commit -m "feat(tui): thinking card with scramble animation"
```

---

### 任务 6：AssistantCard（流式 Markdown + 光标）

**文件：**
- 创建：`neow/tui/widgets/cards/assistant.py`
- 修改：`tests/tui/test_cards.py`

- [ ] **步骤 1：编写失败的测试**

```python
async def test_streaming_appends_markdown_and_shows_cursor():
    card = AssistantCard(number=2, timestamp="12:04")
    async with _host(card) as pilot:
        await card.append_content("找到问题了：`get_tool_definitions()`")
        await card.append_content("\n```python\nreturn prompts.get_tool_definitions()\n```")
        await pilot.pause()
        assert "get_tool_definitions" in card.rendered_markdown()
        assert card.cursor_visible

async def test_finish_removes_cursor_and_sets_meta():
    card = AssistantCard(number=2, timestamp="12:04")
    async with _host(card) as pilot:
        await card.append_content("done")
        card.finish(duration=3.1)
        await pilot.pause()
        assert not card.cursor_visible and "3.1s" in card.meta_text()
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class AssistantCard(CardBase):
    def __init__(self, *, number: int, timestamp: str)
    async def append_content(self, text: str) -> None   # await md.append(text) 批量调用
    def finish(self, duration: float) -> None
    @property
    def cursor_visible(self) -> bool
    def rendered_markdown(self) -> str
    def meta_text(self) -> str
```
- Markdown 由 `Markdown` widget 承载；光标为标题行尾/正文尾的独立 `Static("▊")`，`finish()` 时 `remove()`。
- 代码块语言高亮交由 Markdown 原生能力；正文超 300 行时只 append 前 300 行并 `truncation_hint()` 提示。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/widgets/cards/assistant.py tests/tui/test_cards.py
git commit -m "feat(tui): streaming assistant card"
```

---

### 任务 7：ToolCard + 渲染器 + 状态机

**文件：**
- 创建：`neow/tui/widgets/cards/tool.py`
- 修改：`tests/tui/test_cards.py`（新增 tool 部分）

- [ ] **步骤 1：编写渲染器单测（纯函数，无需 Pilot）**

```python
from neow.tui.widgets.cards.tool import render_tool_body, tool_is_error, tool_is_denied

def test_edit_file_body_has_inline_diff():
    body = render_tool_body("edit_file", {"file_path": "a.py", "old_text": "x", "new_text": "y"}, "ok")
    assert "- x" in body and "+ y" in body

def test_execute_command_body_has_cmd_and_exit():
    body = render_tool_body("execute_command", {"command": "npm test"}, "Exit code: 1\n2 failed")
    assert "$ npm test" in body and "Exit code: 1" in body

def test_search_body_has_hit_count():
    body = render_tool_body("search_code", {"pattern": "foo"}, "a.py:1: foo\nb.py:2: foo")
    assert "2" in body and "foo" in body

def test_read_file_body_has_line_count():
    body = render_tool_body("read_file", {"path": "a.py"}, "line1\nline2\nline3")
    assert "3" in body

def test_error_and_denied_detection():
    assert tool_is_error("Error: boom") and not tool_is_error("ok")
    assert tool_is_denied("Error: User denied: execute_command")
```

- [ ] **步骤 2：编写卡片生命周期 Pilot 测试**

```python
async def test_tool_running_expanded_then_done_collapses():
    card = ToolCard(effects="off")
    async with _host(card) as pilot:
        card.start("edit_file", {"file_path": "a.py"})
        await pilot.pause()
        assert not card.collapsed and card.status_icon == "⟳"
        card.finish(result="ok", is_error=False)
        await pilot.pause()
        assert card.collapsed and card.status_icon == "✓"

async def test_tool_error_stays_open():
    card = ToolCard(effects="off")
    async with _host(card) as pilot:
        card.start("execute_command", {"command": "false"})
        card.finish(result="Error: exit 1", is_error=True); await pilot.pause()
        assert not card.collapsed and card.status_icon == "✗" and card.accent == "#f87171"

async def test_tool_denied_icon():
    card = ToolCard(effects="off")
    card.start("write_file", {"file_path": "a.py"})
    card.finish(result="Error: User denied: write_file", is_error=True)
    assert card.status_icon == "⛔"

async def test_user_toggle_during_run_disables_auto_collapse():
    card = ToolCard(effects="off")
    async with _host(card) as pilot:
        card.start("edit_file", {"file_path": "a.py"}); card.toggle(); await pilot.pause()
        assert card.collapsed
        card.finish(result="ok", is_error=False); await pilot.pause()
        assert card.collapsed    # 用户操作被尊重（保持其选择）

def test_long_output_truncates_with_hint():
    card = ToolCard(effects="off")
    card.finish(result="\n".join(f"line{i}" for i in range(200)), is_error=False)
    assert card.truncation_hint().startswith("… (+")
```

- [ ] **步骤 3：运行确认失败**

- [ ] **步骤 4：实现**

```python
def render_tool_body(name: str, args: dict, result: str) -> Text
def tool_is_error(result: str) -> bool      # startswith("Error:")
def tool_is_denied(result: str) -> bool     # "User denied" in result

class ToolCard(CardBase):
    def start(self, name: str, args: dict) -> None
    def finish(self, result: str, is_error: bool) -> None
    @property
    def status_icon(self) -> str
    def truncation_hint(self) -> str
    def set_duration(self, seconds: float) -> None
```
- 渲染器按规格 §5.4 的表实现 8 类；diff 用 `+`/`-` 前缀 + 绿/红前景（不复用 formatter 的 Console 对象）。
- 状态机：`running` 展开（用户未手动操作时）；`done` 自动折叠（`_user_touched=True` 时跳过）；`error`/`denied` 保持展开；`denied` 图标 `⛔`。
- 标题 meta：`{name} · {summary} · {duration}`，`+N -M` 由 `edit_file` 参数按行计算。
- 输出截断：>30 行只显示前 30 行 + `truncation_hint()`。

- [ ] **步骤 5：运行确认通过**

- [ ] **步骤 6：Commit**

```bash
git add neow/tui/widgets/cards/tool.py tests/tui/test_cards.py
git commit -m "feat(tui): tool card with per-tool renderers and states"
```

---

### 任务 8：TimelineScroll（排序 + 吸附 + 新消息 banner）

**文件：**
- 创建：`neow/tui/widgets/timeline.py`
- 修改：`tests/tui/test_cards.py`（或新建 `tests/tui/test_timeline.py`）

- [ ] **步骤 1：编写失败的测试**

```python
async def test_cards_keep_insertion_order():
    tl = TimelineScroll()
    async with _host(tl) as pilot:
        for n in range(3): tl.add_card(UserCard(f"m{n}", number=n, timestamp="t")); await pilot.pause()
        ids = [w.card_id for w in tl.query(CardBase)]
        assert ids == sorted(ids)

async def test_stick_to_bottom_and_banner():
    tl = TimelineScroll()
    async with _host(tl) as pilot:
        for n in range(30): tl.add_card(UserCard(f"m{n}", number=n, timestamp="t"))
        await pilot.pause(); assert tl.stuck_to_bottom
        tl.scroll_up(); await pilot.pause(); assert not tl.stuck_to_bottom
        tl.add_card(UserCard("new", number=99, timestamp="t")); await pilot.pause()
        assert tl.query_one(NewMessagesBanner).display
        tl.jump_to_bottom(); await pilot.pause()
        assert tl.stuck_to_bottom and not tl.query_one(NewMessagesBanner).display
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class NewMessagesBanner(Static): ...  # "↓ 新消息"
class TimelineScroll(VerticalScroll):
    def add_card(self, card: CardBase) -> None
    def cards(self) -> list[CardBase]
    @property
    def stuck_to_bottom(self) -> bool
    def jump_to_bottom(self) -> None
```
- `add_card` 追加并保持插入顺序；`stuck_to_bottom` 用当前滚动位置与 `max_scroll_y` 比较（阈值 1 行）。
- 非吸附状态下新增卡片时显示 banner；`jump_to_bottom` 隐藏并恢复吸附。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/widgets/timeline.py tests/tui
git commit -m "feat(tui): timeline scroll with stick-to-bottom"
```

---

### 任务 9：事件模型 + ChatController

**文件：**
- 创建：`neow/tui/bridge/__init__.py`、`events.py`、`controller.py`
- 创建：`tests/tui/conftest.py`（FakeConversation / FakeStream / `_host`）
- 创建：`tests/tui/test_controller.py`

- [ ] **步骤 1：编写失败的测试**

```python
def test_event_sequence_from_fake_stream():
    conv = FakeConversation(script=[
        Chunk(progress={"type": "reasoning_start"}),
        Chunk(reasoning_delta="think"), Chunk(progress={"type": "reasoning_end"}),
        Chunk(content_delta="hello"),
        Chunk(progress={"type": "tool_start", "name": "read_file", "args": {"path": "a.py"}}),
        Chunk(progress={"type": "tool_end", "name": "read_file", "result": "ok"}),
        Chunk(content_delta=" world"), Chunk(finish_reason="stop"),
    ])
    events = []; ctrl = ChatController(conv, event_callback=events.append)
    ctrl.run_turn("hi")
    assert [type(e).__name__ for e in events] == [
        "ReasoningStarted", "ReasoningDelta", "ReasoningEnd", "ContentDelta",
        "ToolStarted", "ToolFinished", "ContentDelta", "TurnCompleted"]

def test_delta_coalescing_with_fake_clock():
    now = [0.0]
    conv = FakeConversation(script=[Chunk(content_delta="a"), Chunk(content_delta="b"), Chunk(content_delta="c")])
    events = []
    ctrl = ChatController(conv, event_callback=events.append, flush_interval=0.05,
                          time_fn=lambda: now[0])
    now[0] = 0.01; ctrl.run_turn("hi")
    assert [e.text for e in events if isinstance(e, ContentDelta)] == ["abc"]

def test_cancel_emits_cancelled_turn():
    conv = FakeConversation(script=[Chunk(content_delta="a"), "CANCEL", Chunk(content_delta="b")])
    events = []; ctrl = ChatController(conv, event_callback=events.append)
    ctrl.run_turn("hi")   # FakeConversation 在 "CANCEL" 处调用 ctrl.cancel()
    assert isinstance(events[-1], TurnCompleted) and events[-1].cancelled

def test_cancel_then_new_turn():
    conv = FakeConversation(script=[Chunk(content_delta="a"), "CANCEL"])
    ctrl = ChatController(conv, event_callback=lambda e: None)
    ctrl.run_turn("hi"); ctrl.run_turn("again")
    assert not ctrl.busy

def test_turn_failure_emits_turn_failed():
    conv = FakeConversation(script=RuntimeError("boom"))
    events = []; ctrl = ChatController(conv, event_callback=events.append)
    ctrl.run_turn("hi")
    assert isinstance(events[-1], TurnFailed) and "boom" in events[-1].message

def test_url_autofetch_and_token_limit_parity():
    # FakeConversation 记录 add_web_content 调用；token_tracker.check_max_tokens()=True 时发 TurnFailed 且不消费 stream
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

`events.py`（全部 `@dataclass(frozen=True)`）：`ReasoningStarted`、`ReasoningDelta(text)`、`ReasoningEnd(reasoning, duration)`、`ContentDelta(text)`、`ToolStarted(name, args)`、`ToolFinished(name, result, is_error, denied)`、`TurnCompleted(content, usage, cancelled)`、`TurnFailed(message)`。

`controller.py`：
```python
class ChatController:
    def __init__(self, conversation, *, event_callback, approval_bridge=None,
                 token_tracker=None, event_bus=None, web_fetcher=None,
                 flush_interval: float = 0.05, time_fn=time.monotonic)
    @property
    def busy(self) -> bool
    def run_turn(self, user_input: str) -> None   # 阻塞；由 worker 线程调用
    def cancel(self) -> None
```
- 回合前置（镜像 `repl.py:1049-1060` 的 `_process_input` 前半）：URL 正则自动抓取 → `event_bus.emit("pre_prompt")` → `token_tracker.check_max_tokens()` 超限则 `TurnFailed("Token limit reached...")` 并返回。
- 消费 `conversation.get_response_stream()`；`progress.type` → 对应事件；`content_delta`/`reasoning_delta` 按 `flush_interval` 聚合后发事件；流结束后若 `conversation.pending_lint_feedback` 存在，发 `TurnCompleted` 后自动再跑一个反馈回合（`SystemCard` 由 ChatScreen 呈现）。
- `cancel()`：置 `threading.Event`；循环内检查，命中后 `stream.close()` 并发 `TurnCompleted(cancelled=True)`；异常 → `TurnFailed`。
- `busy` 属性基于内部状态，worker 运行期间为 True。

`tests/tui/conftest.py`：`Chunk` dataclass（同 `StreamChunk` 字段）、`FakeConversation(script)`（`get_response_stream` 逐项 yield；`"CANCEL"` 项触发 `self.on_cancel()`；`RuntimeError` 项直接 raise；记录 `messages/add_web_content/web_cache/pending_lint_feedback`）、`_host(widget)` 异步上下文（临时 App 挂载 widget，供卡片测试）。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/bridge tests/tui/conftest.py tests/tui/test_controller.py
git commit -m "feat(tui): chat controller with event model and cancellation"
```

---

### 任务 10：ApprovalBridge + ApprovalModal

**文件：**
- 创建：`neow/tui/screens/approval.py`
- 修改：`neow/tui/bridge/controller.py`（+`ApprovalBridge`）
- 创建：`tests/tui/test_approval.py`

- [ ] **步骤 1：编写失败的测试**

```python
def test_bridge_allow_and_deny():
    b = ApprovalBridge(request=lambda tool, params, reason, fut: fut.set_result(True))
    assert b("edit_file", {}, "write") is True
    b2 = ApprovalBridge(request=lambda tool, params, reason, fut: fut.set_result(False))
    assert b2("edit_file", {}, "write") is False

def test_bridge_timeout_denies():
    b = ApprovalBridge(request=lambda *a: None, timeout=0.01)
    assert b("edit_file", {}, "write") is False

def test_bridge_cancel_denies():
    def req(tool, params, reason, fut): fut.cancel()
    assert ApprovalBridge(request=req)("edit_file", {}, "write") is False

async def test_modal_keys_return_decision():
    for key, expected in [("y", ApprovalDecision.ALLOW_ONCE), ("a", ApprovalDecision.ALLOW_ALWAYS), ("n", ApprovalDecision.DENY), ("escape", ApprovalDecision.DENY)]:
        results = []
        app = _modal_host(lambda r: results.append(r), tool="execute_command", params={"command": "npm test"}, reason="exec")
        async with app.run_test() as pilot:
            await pilot.press(key); await pilot.pause()
        assert results == [expected]

async def test_always_sets_policy_override():
    policy = ApprovalPolicy(mode=ApprovalMode.WRITE)
    ...
    assert policy.tool_overrides["execute_command"] == "allow"
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class ApprovalDecision(Enum): ALLOW_ONCE = auto(); ALLOW_ALWAYS = auto(); DENY = auto()

class ApprovalModal(ModalScreen[ApprovalDecision]):
    BINDINGS = [("y","allow_once",""), ("a","allow_always",""), ("n","deny",""), ("escape","deny","")]
    def __init__(self, *, tool: str, params: dict, reason: str, tier: str = "")

class ApprovalBridge:
    def __init__(self, *, request: Callable[[str, dict, str, Future], None],
                 timeout: float = 600.0)
    def __call__(self, tool: str, params: dict, reason: str) -> bool
        # Future + request(); result(timeout) → True；TimeoutError/CancelledError/异常 → False
```
- 模态展示规格 §7.5 的元素（工具/tier/参数摘要 200 字/原因）；背景 `#05060a 65%`；边框 `#facc15`。
- ChatScreen 侧（任务 11 接线）：`_request_approval(fut, tool, params, reason)` 用 `self.app.call_from_thread(self._show_approval, ...)`；模态返回 `ALLOW_ALWAYS` 时调 `policy.set_tool_override(tool, "allow")` 再 `fut.set_result(True)`。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/screens/approval.py neow/tui/bridge tests/tui/test_approval.py
git commit -m "feat(tui): approval modal and thread-safe approval bridge"
```

---

### 任务 11：ChatScreen 全接线（回合生命周期 + 队列 + Esc + 状态栏）

**文件：**
- 修改：`neow/tui/screens/chat.py`、`app.py`、`neow/cli/main.py`（接审批桥）
- 修改：`tests/tui/test_app.py`（新增集成测试）

- [ ] **步骤 1：编写失败的测试**

```python
async def test_submit_creates_cards_in_order():
    app = _chat_app(FakeConversation(script=[...reasoning/content/tool/finish...]))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press(*"hi", "enter"); await pilot.pause(); await pilot.pause()
        cards = app.query(CardBase)
        assert [type(c).__name__ for c in cards] == ["UserCard", "ThinkingCard", "AssistantCard", "ToolCard", "AssistantCard"]

async def test_queue_drains_after_turn():
    app = _chat_app(FakeConversation(script=[...]))
    async with app.run_test() as pilot:
        screen = app.query_one(ChatScreen)
        screen.submit_prompt("first"); screen.submit_prompt("second"); screen.submit_prompt("third")
        assert screen.queued == ["second", "third"]
        await pilot.pause(); await pilot.pause()
        assert screen.queued == []
        assert [c.body_text() for c in app.query(UserCard)] == ["first", "second", "third"]

async def test_cancel_then_submit_again():
    app = _chat_app(FakeConversation(script=[...slow..., "CANCEL"...]))
    async with app.run_test() as pilot:
        screen = app.query_one(ChatScreen)
        screen.submit_prompt("a"); await pilot.pause()
        screen.cancel_turn(); await pilot.pause()
        screen.submit_prompt("b"); await pilot.pause(); await pilot.pause()
        assert not screen.busy

async def test_exit_with_pending_approval():
    # 打开真实 ApprovalModal 后直接 app.exit()；断言无异常、退出返回
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class ChatScreen(Screen):
    BINDINGS = [("escape", "cancel_or_close", ""), ("ctrl+o", "toggle_card", ""), ("ctrl+t", "cycle_sidebar", ""), ("tab", "toggle_sidebar", "")]
    def submit_prompt(self, text: str) -> None
    def cancel_turn(self) -> None
    @property
    def busy(self) -> bool
    @property
    def queued(self) -> list[str]
    def handle_event(self, event) -> None       # 事件→卡片（UI 线程）
```
- 提交：`busy` 时入队（`QueueStrip` 更新）；否则建 UserCard → `@work(thread=True, exclusive=True)` 跑 `controller.run_turn` → 事件经 `self.post_message(TuiEventMessage(event))` 回 UI 线程 → `handle_event`。
- `handle_event` 分发：`ReasoningStarted/Delta/End` → ThinkingCard（无卡则建）；`ContentDelta` → 当前 AssistantCard（无则建，编号沿用当回合最后编号+1）；`ToolStarted/Finished` → ToolCard（用 `ToolStarted` 时刻计时）；`TurnCompleted` → 收尾（assistant.finish、thinking.finish、状态栏 idle、发下一条队列、处理 `pending_lint_feedback` 自动回合）；`TurnFailed` → ErrorCard。
- `escape`：busy → `controller.cancel()`；否则关闭浮层/聚焦输入。
- 审批接线：`approval_bridge = ApprovalBridge(request=self._request_approval)`；`_show_approval` push 模态，`ALLOW_ALWAYS` 更新 policy；模态结束 `fut.set_result`。
- `main.py`：`executor.approval_callback = approval_bridge`（TUI 分支）。
- 状态栏：`busy` 时 `set_activity("✻ thinking")`/`"⟳ {tool}"`，回合结束 `"idle"` 并更新 token/成本。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/screens/chat.py neow/tui/app.py neow/cli/main.py tests/tui/test_app.py
git commit -m "feat(tui): chat screen turn lifecycle, queueing and cancellation"
```

---

### 任务 12：InputDock（补全/历史/排队交互）

**文件：**
- 创建：`neow/tui/widgets/input_dock.py`
- 修改：`neow/tui/screens/chat.py`（替换占位输入）
- 创建：`tests/tui/test_input_dock.py`

- [ ] **步骤 1：编写失败的测试**

```python
async def test_slash_completion_filters_commands():
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press(*"/mo")
        await pilot.pause()
        opts = [o.prompt for o in dock.completion_options()]
        assert any("model" in o for o in opts) and not any("help" in o for o in opts)

async def test_enter_submits_and_ctrl_j_newlines():
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press("a", "ctrl+j", "b")
        assert "\n" in dock.text()
        await pilot.press("enter")
        assert dock.posted_submissions == ["a\nb"]

async def test_history_roundtrip(tmp_path):
    dock = InputDock(history_path=tmp_path / ".neow_history")
    dock._remember("hello"); dock._remember("world")
    assert dock._history == ["hello", "world"]

async def test_queue_fifo_and_pop():
    dock = InputDock()
    async with _host(dock) as pilot:
        dock.set_busy(True); dock.enqueue("one"); dock.enqueue("two")
        assert dock.queued_count == 2
        await pilot.press("up")          # 空输入时取回最后一条
        assert dock.text() == "two" and dock.queued_count == 1

async def test_at_file_completion(tmp_path, monkeypatch):
    (tmp_path / "neow").mkdir(); (tmp_path / "neow" / "main.py").write_text("")
    monkeypatch.chdir(tmp_path)
    dock = InputDock()
    async with _host(dock) as pilot:
        await pilot.press(*"@ne")
        await pilot.pause()
        assert any("neow/" in p for p in dock.completion_options())
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
class InputDock(Vertical):
    def text(self) -> str
    def set_text(self, value: str) -> None
    def set_busy(self, busy: bool) -> None
    def enqueue(self, text: str) -> None
    def queued_count(self) -> int
    def pop_last_queued(self) -> str | None
    def completion_options(self) -> list[str]
    def _remember(self, text: str) -> None
    def _history(self) -> list[str]
```
- `TextArea` 子类重绑 `enter→submit`（`action_submit` 发 `InputDock.Submitted`）；`ctrl+j`/`shift+enter` 插入换行。
- 补全：`on_text_area_changed` 判断行首 `/` 或当前 token `@`；`OptionList` 浮层展示最多 20 条；`Tab` 补全、`Enter` 提交、`Esc` 关浮层。
- 历史：复用 `.neow_history`（一行一条，utf-8，末尾追加）；`↑`/`↓` 仅在光标首/末行时触发。
- 排队：`enqueue` 返回文本；`set_busy` 切换提示行 `⏳ 排队 N · ↑ 取回`。
- `@` 扫描排除 `SKIP_DIRS`（复用 `neow/tools/search.py` 的常量）。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/widgets/input_dock.py neow/tui/screens/chat.py tests/tui/test_input_dock.py
git commit -m "feat(tui): input dock with completion, history and queue"
```

---

### 任务 13：CommandDispatcher + 内联命令

**文件：**
- 创建：`neow/tui/commands.py`
- 修改：`neow/tui/screens/chat.py`（提交时先走命令分发）
- 创建：`tests/tui/test_commands.py`

- [ ] **步骤 1：编写失败的测试**

```python
def test_ls_lists_context_files():
    d = make_dispatcher(conversation=FakeConvWithContext(["a.py"]))
    assert "a.py" in d.dispatch(ParsedCommand(Command.LS)).text

def test_add_reports_file_not_found():
    d = make_dispatcher(conversation=FakeConv(add_context_file=FileNotFoundError("nope")))
    assert "nope" in d.dispatch(ParsedCommand(Command.ADD, "x.py")).text

def test_approval_mode_switch_updates_policy_and_config():
    policy = ApprovalPolicy(mode=ApprovalMode.WRITE); cfg = ConfigStub()
    d = make_dispatcher(approval_policy=policy, config=cfg)
    d.dispatch(ParsedCommand(Command.APPROVAL, "yolo"))
    assert policy.mode == ApprovalMode.YOLO and cfg._config["approval"]["mode"] == "yolo"

def test_verbose_toggles():
    d = make_dispatcher(); assert d.dispatch(ParsedCommand(Command.VERBOSE)).text  # 返回状态文本

def test_exit_returns_exit_signal():
    assert make_dispatcher().dispatch(ParsedCommand(Command.EXIT)).should_exit

def test_unknown_falls_back_to_plugin_then_error():
    d = make_dispatcher(plugin_api=None)
    r = d.dispatch(ParsedCommand(None, None, raw_command="nope"))
    assert "Unknown command" in r.text

def test_ui_commands_delegate_to_hooks():
    calls = []
    d = make_dispatcher(hooks={"help": lambda: calls.append("help")})
    d.dispatch(ParsedCommand(Command.HELP))
    assert calls == ["help"]
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

```python
@dataclass
class CommandResult:
    text: str = ""; should_exit: bool = False; kind: str = "info"  # info|warn|error

class CommandDispatcher:
    def __init__(self, *, conversation, config, session_manager=None,
                 token_tracker=None, approval_policy=None, web_fetcher=None,
                 event_bus=None, plugin_api=None, hooks: dict[str, Callable] | None = None)
    def dispatch(self, parsed: ParsedCommand) -> CommandResult
```
- 内联命令逐一镜像 `REPL._handle_command`（`neow/cli/repl.py:625-931`），API 调用完全一致：`/clear`→`conversation.clear_history()`；`/add`/`/drop`/`/ls`；`/web`→`web_fetcher.fetch`+`add_web_content`；`/compact` 三变体（`--keep-tokens`/`incremental`/`handoff`，`repl.py:845-867`）；`/export`→`session_manager.export_markdown`；`/image`→`conversation.queue_image`；`/lint` `/test` 含 `on/off` 与失败后反馈回合；`/think`；`/architect` `/code`；`/verbose` 翻转 `self.verbose`；`/approval` 模式映射与 config 回写（`repl.py:884-921`）；`/save` JSONL 逻辑（`repl.py:757-776`）；`/exit` 返回 `should_exit=True`。
- UI 类命令（`/help /model /history /load /tree /branch /diff /commit /undo /cost`）通过 `hooks` 委托；hook 未注册时返回 error 文案（任务 14 注册）。
- `/commit` 无参数时走 `hooks["commit_ai"]`（复用 REPL 的 AI 生成 commit message 语义：把提示词丢给对话流）；有参数时直接 `git_commit`。
- 未知命令先查 `plugin_api.plugin_commands`，否则 `CommandResult("Unknown command: ...", kind="error")`。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/commands.py neow/tui/screens/chat.py tests/tui/test_commands.py
git commit -m "feat(tui): slash command dispatcher with REPL parity"
```

---

### 任务 14：功能屏（help/model/session/tree/diff/cost/approval picker）+ 侧栏

**文件：**
- 创建：`neow/tui/screens/help.py`、`model_picker.py`、`session_picker.py`、`tree.py`、`diff_view.py`、`cost.py`
- 修改：`neow/tui/screens/chat.py`（注册 hooks、侧栏三页签）
- 创建：`tests/tui/test_screens.py`

- [ ] **步骤 1：编写失败的测试（每个屏最小可用断言）**

```python
async def test_help_screen_lists_all_commands():
    app = _screen_app(HelpScreen())
    async with app.run_test() as pilot:
        text = app.screen.render_str()
        for c in ["/help", "/model", "/diff", "/tree", "/approval"]: assert c in text

async def test_model_picker_switches_via_callback():
    switched = []
    app = _screen_app(ModelPickerScreen(models=["deepseek", "openai"], on_select=switched.append))
    async with app.run_test() as pilot:
        await pilot.press("down", "enter"); await pilot.pause()
        assert switched == ["openai"]

async def test_session_picker_lists_sessions():
    app = _screen_app(SessionPickerScreen(sessions=[{"name": "s1", "message_count": 3, "model": "m", "created_at": "2026-10-07"}], on_select=lambda n: None))
    async with app.run_test() as pilot:
        assert "s1" in app.screen.render_str()

async def test_tree_screen_renders_nodes():
    tree_data = {"a": {"parentId": None, "children": ["b"], "role": "user", "content_preview": "hi"}}
    app = _screen_app(SessionTreeScreen(tree=tree_data, leaf_id="b", on_goto=lambda n: None))
    async with app.run_test() as pilot:
        assert "hi" in app.screen.render_str()

async def test_diff_screen_shows_diff_and_binds_commit():
    app = _screen_app(DiffScreen(diff_text="+added\n-removed", on_commit=lambda: None, on_undo=lambda: None))
    async with app.run_test() as pilot:
        assert "added" in app.screen.render_str()
        await pilot.press("c"); assert app.screen.committed

async def test_cost_screen_shows_summary():
    app = _screen_app(CostScreen(summary="deepseek 1.2k in / 3.4k out $0.0042"))
    async with app.run_test() as pilot:
        assert "$0.0042" in app.screen.render_str()

async def test_sidebar_tabs_cycle_and_refresh():
    app = _chat_app(...)
    async with app.run_test() as pilot:
        screen = app.query_one(ChatScreen)
        await pilot.press("tab"); assert screen.sidebar_visible
        await pilot.press("ctrl+t"); assert screen.sidebar_tab == "tree"
        await pilot.press("ctrl+t"); assert screen.sidebar_tab == "git"
```

- [ ] **步骤 2：运行确认失败**

- [ ] **步骤 3：实现**

- 每个 Screen 构造参数即其依赖的数据/回调（可测、可注入）；展示用 `Static`/`Markdown`/`Tree`/`SelectionList`；返回用 `dismiss(value)`。
- `ModelPickerScreen`：列表来自 `config.models`；选择回调由 ChatScreen 实现：`create_model_client(config, name)` → `validate_connection()` → 成功则 `conversation.model_client = new_client`（镜像 `repl.py:645-660`），失败弹 ErrorCard。
- `SessionPickerScreen`：数据 `session_manager.list_sessions()`；选择后镜像 `/load`（JSONL 优先，回退 JSON，`repl.py:778-798`）。
- `SessionTreeScreen`：数据 `session_manager.session_tree.get_tree(name)`；`Enter` 导航（`branch_at` + 重载 messages），`b` 分叉，镜像 `repl.py:954-1045`。
- `DiffScreen`：`git_diff(staged)` 文本；`c` 提交（无 message 时打开 `CommitInputModal`，向对话流发 "Please generate..." 提示，镜像 `repl.py:670-680`），`u` 回退（确认后 `git_undo()`）。
- `CostScreen`：`token_tracker.get_session_summary()`。
- `ApprovalPicker`（可用 `ModalScreen` 实现，放在 `commands.py` 或 `screens/approval.py`）：三模式 `RadioSet`，选择后 `policy.set_mode` + config 回写。
- 侧栏：`Sidebar` 容器三页签（CONTEXT 文件列表 / SESSION TREE 内联树 / GIT `git_status()` + 最近 3 条 `git_log`）；`Tab` 显隐（宽 <72 时 toast「终端宽度不足」）；`Ctrl+T` 循环；数据在 `on_show` 时刷新。
- `ChatScreen` 注册 hooks：help/model/history/load/tree/branch/diff/commit/undo/cost/approval。

- [ ] **步骤 4：运行确认通过**

- [ ] **步骤 5：Commit**

```bash
git add neow/tui/screens neow/tui/screens/chat.py tests/tui/test_screens.py
git commit -m "feat(tui): feature screens and sidebar tabs"
```

---

### 任务 15：动效打磨、README、全量回归与 PTY 三入口验收

**文件：**
- 修改：`neow/tui/widgets/logo.py`、`app.py`、`screens/chat.py`、`widgets/cards/base.py`、`theme.tcss`
- 修改：`README.md`、`tests/tui/pty_smoke.py`
- 修改：`tests/tui/test_app.py`（effects 配置行为）

- [ ] **步骤 1：编写失败的测试**

```python
async def test_effects_off_disables_logo_timer():
    app = _chat_app(effects="off")
    async with app.run_test() as pilot:
        assert app.query_one(NeowLogo)._timer is None
        assert app.query_one(CardBase).styles.opacity == 1.0

async def test_logo_skips_on_any_key():
    app = _chat_app(scramble_effects="full")
    async with app.run_test() as pilot:
        await pilot.press("x"); await pilot.pause()
        assert app.query_one(NeowLogo).collapsed_splash

def test_effect_mode_from_config_and_env(monkeypatch):
    monkeypatch.setenv("TEXTUAL_ANIMATIONS", "none")
    assert resolve_effects("full") == "off"
    assert resolve_effects("subtle", env_none=False) == "subtle"
```

- [ ] **步骤 2：实现**

- `NeowLogo`：12fps 渐变相位动画；连接成功后 600ms 收起为顶栏标记；任意按键跳过；`effects != full` 时跳过动画直接显示标记。
- 卡片入场：`CardBase.on_mount` 在 `full` 下 `styles.animate("opacity", ...)`；`subtle/off` 不动画。流式光标脉冲、工具完成 150ms 边框过渡、审批边框脉冲按规格 §6.1。
- `resolve_effects(config_value, *, env_none: bool | None = None) -> str` 集中在 `app.py`；`TEXTUAL_ANIMATIONS=none` 或 stdout 非 TTY → `"off"`。
- README：新增 "Full-screen TUI (default)" 小节（截图路径、`--plain`、`neow --tui`、`tui.effects`、`Ctrl+P`/`Tab`/`Esc` 键位摘要）。

- [ ] **步骤 3：全量验收（规格 §11.2 逐条执行）**

```bash
PATH="/home/neow/.venv/bin:$PATH" .venv/bin/python -m pytest -q          # 0 failed
.venv/bin/black --check .                                                # clean
.venv/bin/python tests/tui/pty_smoke.py                                  # PTY SMOKE OK
git diff --stat e397f9d..HEAD -- neow/core neow/models neow/tools        # 语义零改动（无输出或仅 __init__）
```

- [ ] **步骤 4：对照规格 §4–§10 列出逐条核对表**（放 commit message 或回复中），覆盖：布局断点、卡片 7 类、动效 7 项、键位 16 项、命令 27 个、入口 8 场景、测试 8 层。

- [ ] **步骤 5：Commit**

```bash
git add neow/tui README.md tests/tui
git commit -m "feat(tui): animated logo, effects modes and docs; full acceptance pass"
```

---

## 规格覆盖对照（编写时自检）

| 规格章节 | 覆盖任务 |
|---------|---------|
| §4 布局/断点/区域 | 2、8、12、14 |
| §5 卡片体系 | 4、5、6、7 |
| §6 动效与性能 | 3、5、7、15 |
| §7 交互/键位/命令/审批 | 10、11、12、13、14 |
| §8 视觉系统 | 2、3、15 |
| §9 架构/线程/桥/取消/配置 | 2、9、10、11 |
| §10 入口与兼容 | 1、2、15 |
| §11 测试与验收 | 每个任务的测试步骤 + 15 的验收步骤 |

**类型一致性检查（编写时已核对）：** `RunMode`/`ModeError`；`GRADIENT`/`gradient_hex`/`gradient_text`；`ScrambleEngine.frame/settle/advance`；`CardBase.toggle/collapsed/body_text/title_text`；`ThinkingCard.append_reasoning/finish_reasoning/_frame/truncation_hint`；`AssistantCard.append_content/finish/cursor_visible/rendered_markdown/meta_text`；`ToolCard.start/finish/status_icon/truncation_hint`；`TimelineScroll.add_card/stuck_to_bottom/jump_to_bottom`；`ChatController.run_turn/cancel/busy`；`ApprovalBridge.__call__`；`ApprovalModal`/`ApprovalDecision`；`ChatScreen.submit_prompt/cancel_turn/busy/queued/handle_event`；`InputDock.text/set_text/set_busy/enqueue/queued_count/pop_last_queued/completion_options`；`CommandDispatcher.dispatch`/`CommandResult`。

**步骤扫描：** 每个任务以「失败测试 → 确认失败 → 实现 → 确认通过 → commit」收束；测试步骤给出确切断言，代码步骤只给签名与规格定值，未重复实现体。
