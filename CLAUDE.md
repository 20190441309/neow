# Neow CLI Project

## Overview
Neow is a lightweight, general-purpose AI CLI assistant similar to Claude Code.

## Tech Stack
- Python 3.10+
- DeepSeek API (default), Anthropic Claude, OpenAI GPT
- Libraries: openai, anthropic, rich, click, prompt-toolkit

## Project Structure
- `neow/cli/` - CLI entry point and REPL
- `neow/core/` - Core modules (config, conversation, executor, prompts)
- `neow/models/` - AI model clients (deepseek, anthropic, openai)
- `neow/tools/` - Tool implementations (file_ops, command, search)
- `neow/utils/` - Utilities (logger, formatter)
- `tests/` - Test suite (80 tests)

## Current Status
- Basic REPL with multi-turn conversation
- Tool calling works (read_file, write_file, edit_file, execute_command, search_code)
- System prompts define AI persona and capabilities
- Config at `~/.neow/config.json` or `.neow.json` in project root

## Run
```bash
neow              # Start CLI
pytest            # Run tests
```

## Recent Work
- Added system prompts (neow/core/prompts.py)
- Fixed Windows encoding issues
- Fixed DeepSeek API compatibility (reasoning_content, tool_calls)
- Made model name matching flexible (supports deepseek-v4-flash, etc.)
