# Neow

A lightweight, general-purpose AI CLI assistant.

## Features

- Support for multiple AI models (DeepSeek, Anthropic Claude, OpenAI GPT)
- Interactive REPL interface
- Code editing, command execution, codebase understanding, conversation memory
- Lightweight design for fast startup and response

## Installation

```bash
pip install -e .
```

## Configuration

Create a `.neow.json` file in your project root or `~/.neow/config.json`:

```json
{
  "default_model": "deepseek-v4-flash",
  "models": {
    "deepseek": {
      "api_key": "your-api-key-here",
      "model": "deepseek-v4-flash"
    }
  }
}
```

Or set environment variables:

```bash
export NEOW_DEEPSEEK_API_KEY="your-api-key-here"
```

## Usage

```bash
neow
```

### Commands

- `/help` - Show help message
- `/clear` - Clear conversation history
- `/exit` - Exit the CLI
- `/model <name>` - Switch AI model (deepseek, anthropic, openai)

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
