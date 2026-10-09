<div align="center">

<pre>
 ███╗   ██╗███████╗ ██████╗ ██╗    ██╗
 ████╗  ██║██╔════╝██╔═══██╗██║    ██║
 ██╔██╗ ██║█████╗  ██║   ██║██║ █╗ ██║
 ██║╚██╗██║██╔══╝  ██║   ██║██║███╗██║
 ██║ ╚████║███████╗╚██████╔╝╚███╔███╔╝
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝  ╚══╝╚══╝
</pre>

<p>
  <strong>A lightweight, general-purpose AI CLI assistant.</strong><br>
  <em>Your intelligent pair programmer, right in the terminal.</em>
</p>

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)](https://opensource.org/licenses/MIT)

</div>

---

## 🚀 Features

**Neow** isn't just another chatbot wrapper. It's a full-featured coding agent designed to seamlessly integrate into your workflow.

- **Multi-Model Support**: Switch effortlessly between **DeepSeek**, **Anthropic Claude**, and **OpenAI GPT** models.
- **Intelligent Code Editing**: 
  - Standard file creation and modification.
  - **Hashline Editing**: A unique, surgical editing system using content-addressable hashing. Make precise changes to specific lines without rewriting entire files.
- **Developer Toolkit**:
  - 📂 **File Operations**: Read, write, and manage your project files.
  - 🔍 **Code Search**: Regex-powered codebase search to find what you need instantly.
  - 🌐 **Web & GitHub**: Fetch web content and extract details from GitHub Issues/PRs directly.
  - 🛠️ **Linting & Testing**: Auto-detects and runs your project's linter and test suite.
- **Rich UI**: Beautiful, syntax-highlighted terminal output powered by `rich`.

---

## 🖥️ Full-screen TUI (default)

Running `neow` on a TTY opens the full-screen TUI:

- **Card timeline**: user, assistant, thinking, tool call, error and compaction cards; tool cards collapse automatically when done.
- **Thinking scramble** (`✻ Thinking`): live reasoning with a crush-style scrambled frontier that settles into `✻ Thought …` and collapses when finished.
- **Keyboard**: `Enter` send · `Ctrl+J` newline · `Esc` interrupt · `Ctrl+B` sidebar · `Ctrl+T` sidebar tab · `Ctrl+O` collapse card · `Ctrl+P` command palette · `F1` help · `Ctrl+Y` copy the last code block (OSC52; not supported by macOS Terminal) · `Ctrl+Q` quit.
- **Completion**: type `/` or `@`, use `Up`/`Down` to choose, `Tab` or `Enter` to complete, and `Esc` to dismiss. Press `Enter` again to submit. `PgUp`/`PgDn` scroll the conversation without leaving the editor.
- `@` completes file paths, `/` lists slash commands; all existing commands (`/help`, `/model`, `/diff`, `/tree`, `/cost`, …) work.
- Approvals appear as a modal: `y` allow once, `a` always allow this tool, `n`/`Esc` deny.
- Design reference: `docs/research/tui-feasibility/screenshots/`.

Prefer the classic line REPL?

```bash
neow --plain        # classic REPL (unchanged)
neow --tui          # force the full-screen TUI
neow "prompt"       # one-shot mode (unchanged)
```

Animation modes via `.neow.json` (defaults to `full`):

```json
{ "tui": { "effects": "full", "theme": "midnight" } }
```

`effects` accepts `full`, `subtle` or `off`; `TEXTUAL_ANIMATIONS=none` also forces `off`. `theme` accepts `midnight` (default) or `light` for bright terminals. Piped or non-TTY output never starts the TUI.

---

## 🛠️ Installation

Get up and running in seconds.

```bash
# Clone the repository
git clone https://github.com/yourusername/neow.git
cd neow

# Install in editable mode
pip install -e .

# Or install dependencies if running from source
pip install -r requirements.txt
```

---

## ⚙️ Configuration

Neow is highly configurable. Create a `.neow.json` file in your project root or `~/.neow/config.json`.

**Example `.neow.json`:**
```json
{
  "default_model": "deepseek",
  "models": {
    "deepseek": {
      "api_key": "your-api-key-here",
      "model": "deepseek-v4-flash"
    },
    "openai": {
      "api_key": "sk-...",
      "model": "gpt-4o"
    }
  }
}
```

Alternatively, use **Environment Variables**:
```bash
export NEOW_DEEPSEEK_API_KEY="your-api-key-here"
export NEOW_ANTHROPIC_API_KEY="your-api-key-here"
```

### Any OpenAI-compatible provider (BYOK)

Point Neow at any OpenAI-compatible endpoint (OpenRouter, SiliconFlow, Moonshot, DeepSeek proxies, vLLM, Ollama, ...), or override the built-in providers' endpoint:

```json
{
  "default_model": "openrouter",
  "models": {
    "openrouter": {
      "provider": "openai-compatible",
      "api_key_env": "OPENROUTER_API_KEY",
      "model": "anthropic/claude-sonnet-4",
      "base_url": "https://openrouter.ai/api/v1"
    },
    "ollama": {
      "provider": "openai-compatible",
      "api_key": "ollama",
      "model": "qwen2.5:14b",
      "base_url": "http://localhost:11434/v1",
      "validate": "skip"
    }
  }
}
```

Model entry fields:

| Field | Values | Notes |
|-------|--------|-------|
| `provider` | `openai` · `openai-compatible` · `anthropic` · `deepseek` | Optional; without it the provider is inferred from the model name |
| `model` | any string | Sent to the provider |
| `api_key` | string | Inline key |
| `api_key_env` | environment variable name | Keeps keys out of the config file |
| `base_url` | URL | Custom endpoint (supported by all providers) |
| `validate` | `auto` (default) · `skip` | `skip` disables the startup probe (local servers, gateways without `/models`) |
| `max_retries` | integer ≥ 0 | Retries for rate limits (429), server errors (5xx), timeouts and dropped connections, with exponential backoff and `retry-after`. Default: the SDK's 2 |
| `context_window` | positive integer | Tokens the model accepts. Drives the `ctx` percentage and auto-compaction (at 80 %). Default: Claude 200000, everything else 128000 — set it for smaller local models |
| `max_output_tokens` | positive integer | Cap on one reply. Defaults: Anthropic 16000 (Claude 3.x: 4096 / 8192), DeepSeek 8192, OpenAI and compatible endpoints send nothing (the model's own maximum) |

If a reply hits `max_output_tokens` while writing tool arguments, the half-written calls are not run; the model is told to split the change and tries again.

`agent.max_turns` (default 50) caps how many model requests one user turn may make, so a tool loop cannot run forever:

```json
{ "agent": { "max_turns": 50, "max_tool_output_chars": 30000 } }
```

`agent.max_tool_output_chars` (default 30000) bounds each tool result kept in the conversation: longer output keeps its first 60 % and last 40 % with a note in between. `read_file` returns numbered lines, 2000 at a time; the model pages with `offset`/`limit`.

**Read before edit.** The agent may only edit (or overwrite) a file it has read in this session, and only if the file has not changed since — for example after you edited it yourself or a command rewrote it. Otherwise the edit is refused and the model reads the file again first.

Shell commands run by the agent time out after 120 s by default (the model may ask for longer, up to `tools.command.max_timeout`, default 600). Pressing **Esc** in the TUI kills the running command and everything it started.

```json
{ "tools": { "command": { "max_timeout": 600 } } }
```

**Key resolution order:** `api_key` → `api_key_env` → `NEOW_<MODEL_NAME>_API_KEY` → `NEOW_DEEPSEEK_API_KEY` / `NEOW_ANTHROPIC_API_KEY` / `NEOW_OPENAI_API_KEY`. Keys are never logged or echoed.

`/model` lists every configured model with its provider and endpoint. Token prices for custom models can be added under `token.prices` keyed by the model name (unset models count as $0).

**Search tools.** The agent explores with `grep` (contents; uses [ripgrep](https://github.com/BurntSushi/ripgrep) when installed, otherwise a built-in fallback), `glob` (file names, newest first) and `list_dir` (directory tree). All three skip files ignored by git; outside a repository they skip `node_modules`, virtualenvs, build output and caches. `search_code` still works but is deprecated.

**Task list.** For multi-step work the agent keeps a checklist with `todo_write` (one task in progress at a time). The TUI shows it as a card that updates in place and in the sidebar's Todos tab (`Ctrl+T`); the REPL prints it after each update. The list is saved with the session and never asks for approval.

**Sub-agents.** The agent can hand a self-contained job to a sub-agent with the `task` tool. An `explore` sub-agent only has read-only tools (several run in parallel) and is meant for broad searches; a `general` sub-agent can edit files and run commands, and its approvals are shown to you labelled with the task. Sub-agents start with a fresh context (plus your project memory), return only a final report, cannot start further sub-agents, stop when you press Esc, and their tokens appear separately in `/cost`. Configure with `agent.subagent_max_turns` (default 25) and `agent.subagent_approval` (`inherit`, the default, or `yolo`).

**Architect mode** (`/architect`): the planner model (`architect.planner`) turns each request into a task list, which the current model then works through with the usual tools and approvals.

**Prompt caching.** The system prompt stays the same for the whole session; files added with `/add`, fetched pages and files matching your question are sent with your message, and only again when they change. Providers can therefore reuse the cached prefix (Anthropic requests carry `cache_control` breakpoints; OpenAI and DeepSeek cache automatically). `/cost` shows how much input was served from cache. Cached input is priced at `cache_read` / `cache_write` if set under `token.prices.<model>`, otherwise at 0.1× / 1.25× the input price.

**Project memory.** At startup Neow loads instructions from `~/.neow/NEOW.md` (your own preferences) and from `AGENTS.md` / `NEOW.md` in every directory from the git root down to the current directory; more specific files come later and win. A line containing only `@docs/style.md` imports that file (up to 5 levels). `/init` asks the agent to explore the repository and write an `AGENTS.md` (the write goes through approval as usual); `/memory` lists the loaded files, `/memory add <text>` appends a note to the project `NEOW.md`, `/memory reload` re-reads them.

---

## 💡 Usage

Simply run `neow` to start the interactive REPL:

```bash
neow
```

Or pass a prompt directly for a one-shot command:

```bash
neow "Explain the main.py file and suggest optimizations"
```

### 📋 Commands

| Command | Description |
| :--- | :--- |
| `/help` | Show the help message |
| `/clear` | Clear conversation history |
| `/model <name>` | Switch active AI model (e.g., `deepseek`, `anthropic`) |
| `/exit` | Exit the CLI |

### 🧠 The Hashline Edit System

Neow uses a sophisticated **Hashline** system to ensure file edits are precise and reliable. 

1. **Snapshot**: When Neow reads a file, it calculates a unique SHA-256 hash (e.g., `a1b2c3d4`).
2. **Anchor**: Edits are requested using the format `¶path/to/file.py#a1b2c3d4`.
3. **Apply**: Neow applies changes strictly to the anchored version of the file. If the file has changed externally (stale hash), Neow intelligently attempts to recover or alerts you, preventing accidental overwrites.

---

## 🧪 Development

We use `pytest` for testing and `black` for formatting.

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black .
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
