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

**Key resolution order:** `api_key` → `api_key_env` → `NEOW_<MODEL_NAME>_API_KEY` → `NEOW_DEEPSEEK_API_KEY` / `NEOW_ANTHROPIC_API_KEY` / `NEOW_OPENAI_API_KEY`. Keys are never logged or echoed.

`/model` lists every configured model with its provider and endpoint. Token prices for custom models can be added under `token.prices` keyed by the model name (unset models count as $0).

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
