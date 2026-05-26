# P3 Features Design Spec

> Date: 2026-05-26
> Scope: P3 — Web 上下文、插件系统

---

## 1. Web 上下文

### 功能概述

- `/web <url>` — 手动抓取网页内容，加入会话上下文
- 自动检测 — 用户输入中出现 URL 时自动抓取并注入上下文
- 智能提取 — 使用 readability 算法提取正文，解析代码块
- GitHub 支持 — issue/PR 链接通过 GitHub API 获取结构化数据

### 新增文件

- `neow/tools/web.py` — WebFetcher 和相关类

### 数据结构

```python
@dataclass
class WebContent:
    url: str
    title: str
    text: str              # 正文纯文本
    code_blocks: list      # [(language, code), ...]
    content_type: str      # "webpage" | "github_issue" | "github_pr"
```

### WebFetcher

```python
class WebFetcher:
    def __init__(self, config: dict):
        self.timeout = config.get("timeout", 10)
        self.max_length = config.get("max_content_length", 10000)

    def fetch(self, url: str) -> WebContent:
        """抓取 URL，返回结构化内容。
        - 普通网页：readability 提取正文 + BeautifulSoup 提取代码块
        - GitHub issue/PR：调用 extract_github()
        - 内容超过 max_length 时截断
        """

    def extract_github(self, url: str) -> WebContent:
        """GitHub issue/PR 专用提取。
        - 使用 gh CLI 获取 issue/PR 详情（标题、正文、评论）
        - 格式化为结构化文本
        - gh CLI 不可用时回退到 requests + GitHub API
        """

    def _extract_code_blocks(self, html: str) -> list:
        """从 HTML 中提取 <pre><code> 块，保留语言标注"""

    def _clean_text(self, text: str) -> str:
        """清理多余空白，截断到 max_length"""
```

### GitHub URL 匹配

```
https://github.com/{owner}/{repo}/issues/{number}
https://github.com/{owner}/{repo}/pull/{number}
```

优先用 `gh issue view {number} --repo {owner}/{repo}` 和 `gh pr view {number} --repo {owner}/{repo}`。

### 集成点

**手动 — `/web` 命令：**
- `commands.py`：新增 `Command.WEB`
- `repl.py`：`_handle_command` 中处理 `/web`，调用 `WebFetcher.fetch()`，结果存入 `conversation.add_context_file(url_key, content)`
- URL 作为 context_files 的 key（以 `web:` 前缀区分本地文件）

**自动检测 — 输入中的 URL：**
- `repl.py`：`_process_input` 中用正则匹配 URL
- 检测到 URL 时自动 fetch，将内容作为附加上下文拼接到 prompt 前
- 同一 URL 在同一会话中不重复抓取（缓存在 `conversation.web_cache`）

**对话管理：**
- `conversation.py`：新增 `web_cache: Dict[str, WebContent]` 和 `add_web_content(url, content)` 方法
- 系统提示词中说明上下文中包含网页内容

### 配置

```python
# config.py DEFAULT_CONFIG 扩展
"web": {
    "enabled": True,
    "auto_detect": True,
    "max_content_length": 10000,
    "timeout": 10,
}
```

### 依赖

```
requests
readability-lxml
beautifulsoup4
lxml
```

---

## 2. 插件系统

### 功能概述

- Python 包格式的插件，放在 `~/.neow/plugins/` 目录
- 每个插件包含 `register(api)` 入口函数
- 插件可以注册工具、命令、事件监听
- 启动时自动扫描和加载

### 新增文件

- `neow/core/plugin.py` — PluginManager、PluginAPI、EventBus

### PluginAPI

```python
class PluginAPI:
    """暴露给插件的注册接口。"""

    def __init__(self, executor, event_bus):
        self._executor = executor
        self._events = event_bus
        self.plugin_commands: Dict[str, Callable] = {}  # name -> handler

    def register_tool(self, name: str, func: Callable, description: str = ""):
        """注册一个 AI 可调用的工具。
        工具函数签名：func(**kwargs) -> str
        """

    def register_command(self, name: str, handler: Callable, description: str = ""):
        """注册一个 / 斜杠命令。
        handler 签名：handler(args: str) -> None
        name 格式："/my-command"（带斜杠）
        """

    def on_event(self, event: str, handler: Callable):
        """监听事件。
        可用事件见事件列表。
        """
```

### EventBus

```python
class EventBus:
    """轻量事件总线。"""

    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def on(self, event: str, handler: Callable):
        """注册事件处理器。"""

    def emit(self, event: str, **kwargs):
        """触发事件，调用所有注册的 handler。
        handler 异常不影响其他 handler 和主流程。
        """
```

### PluginManager

```python
class PluginManager:
    """扫描、加载、管理插件。"""

    def __init__(self, plugins_dir: Path, api: PluginAPI):
        self.plugins_dir = plugins_dir    # ~/.neow/plugins/
        self.api = api
        self.loaded_plugins: Dict[str, ModuleType] = {}

    def discover_and_load(self) -> List[str]:
        """扫描 plugins_dir 下的子目录，加载含 __init__.py 的插件。
        Returns: 已加载的插件名称列表。
        """

    def _load_plugin(self, plugin_dir: Path) -> bool:
        """加载单个插件：
        1. 用 importlib 导入插件包
        2. 检查是否有 register 函数
        3. 调用 register(api)
        4. 记录到 loaded_plugins
        失败时 log 错误，不影响其他插件
        """

    def _is_valid_plugin(self, plugin_dir: Path) -> bool:
        """检查目录是否为有效插件（含 __init__.py）"""
```

### 事件列表

| 事件 | 触发时机 | 参数 |
|------|---------|------|
| `session_start` | REPL 启动后 | `conversation` |
| `session_end` | `/exit` 退出前 | `conversation` |
| `pre_prompt` | 发送给 AI 之前 | `prompt: str, conversation` |
| `post_response` | AI 回复之后 | `response, conversation` |
| `file_changed` | 文件编辑后 | `tool_name: str, file_path: str` |

### 集成点

**main.py：**
```python
# 在 executor 和 conversation 创建之后
event_bus = EventBus()
plugin_api = PluginAPI(executor, event_bus)
plugin_manager = PluginManager(Path.home() / ".neow" / "plugins", plugin_api)
loaded = plugin_manager.discover_and_load()
# plugin_api.plugin_commands dict 自动被填充
```

**repl.py：**
```python
# __init__ 接收 plugin_api 参数
# 命令分发：当 parse_command 返回 command=None 且输入以 "/" 开头时，
# 检查 plugin_api.plugin_commands 字典
def _handle_command(self, parsed):
    if parsed.command is not None:
        # 内置命令处理（现有逻辑）
        ...
    else:
        # 检查插件命令
        cmd_name = parsed.raw_command  # 如 "/my-cmd"
        if cmd_name in self.plugin_api.plugin_commands:
            self.plugin_api.plugin_commands[cmd_name](parsed.args)
            return False
        print_error(f"Unknown command: {cmd_name}")
```

**commands.py：**
- `ParsedCommand` 新增 `raw_command: Optional[str]` 字段，存储原始命令字符串（如 `/web`）
- `parse_command` 在 command_map 匹配失败但输入以 `/` 开头时，设置 `raw_command`

**executor.py：**
- 插件通过 `PluginAPI.register_tool()` 注册的工具写入 `executor.tools` dict
- 后续执行流程自动覆盖，无需额外改动

**conversation.py：**
- 不直接持有 EventBus，事件在 REPL 层 emit（REPL 有完整上下文）

**事件 emit 位置（REPL 层）：**
- `session_start`：`repl.start()` 开头
- `session_end`：`_handle_command` 的 EXIT 分支中
- `pre_prompt`：`_process_input` 开头
- `post_response`：`_process_input` 结尾
- `file_changed`：在 `executor.on_file_change` 回调中（main.py 已有此回调）

### 插件目录结构

```
~/.neow/plugins/
  my_plugin/
    __init__.py      # 必须包含 register(api)
    helpers.py       # 可选内部模块
  another_plugin/
    __init__.py
```

### 插件示例

```python
# ~/.neow/plugins/web_tools/__init__.py
import requests

def register(api):
    api.register_tool("summarize_url", summarize_url, "Fetch and summarize a URL")
    api.register_command("/summary", handle_summary, "Summarize a web page")
    api.on_event("post_response", log_response)

def summarize_url(url: str) -> str:
    resp = requests.get(url, timeout=10)
    return resp.text[:5000]

def handle_summary(args: str):
    print(f"Summarizing: {args}")

def log_response(**kwargs):
    pass  # Logging hook
```

---

## 文件变更总结

| 文件 | 变更类型 | 描述 |
|------|----------|------|
| `neow/tools/web.py` | **新建** | WebFetcher — 网页抓取和内容提取 |
| `neow/core/plugin.py` | **新建** | PluginManager, PluginAPI, EventBus |
| `neow/core/config.py` | 修改 | 新增 web 配置段 |
| `neow/core/conversation.py` | 修改 | 新增 web_cache, add_web_content() |
| `neow/cli/commands.py` | 修改 | 新增 Command.WEB, ParsedCommand.raw_command |
| `neow/cli/repl.py` | 修改 | 处理 /web 命令，URL 自动检测，插件命令分发 |
| `neow/cli/main.py` | 修改 | 初始化 PluginManager, EventBus |
| `neow/utils/formatter.py` | 修改 | 更新帮助文本 |
| `CLAUDE.md` | 修改 | 勾选 P3 项目 |

---

## 测试计划

- `tests/test_web.py` — WebFetcher 测试（mock HTTP）
- `tests/test_plugin.py` — PluginManager, PluginAPI, EventBus 测试
- 更新 `tests/test_cli.py` — /web 命令和 URL 自动检测测试
- 更新 `tests/test_core.py` — ConversationManager web_cache 集成测试
