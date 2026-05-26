# Neow CLI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个轻量级、通用的 AI CLI 助手，支持多种任务（代码编辑、文档处理、数据分析等），保持快速响应和良好的用户体验。

**Architecture:** 采用分层架构设计，包括 CLI 入口层、核心引擎层、工具层和 AI 模型层。使用 Python 实现，支持多种 AI 模型（DeepSeek、Anthropic Claude、OpenAI GPT），提供交互式 REPL 界面。

**Tech Stack:** Python 3.10+, Anthropic SDK, OpenAI SDK, Rich, Click, Prompt Toolkit, PyYAML

---

## 文件结构

### 项目根目录
- `neow/` - 主包目录
- `tests/` - 测试目录
- `docs/` - 文档目录
- `pyproject.toml` - 项目配置
- `requirements.txt` - 依赖列表
- `README.md` - 项目说明

### neow/ 主包
- `neow/__init__.py` - 包初始化
- `neow/cli/` - CLI 入口层
  - `neow/cli/__init__.py`
  - `neow/cli/main.py` - CLI 入口点
  - `neow/cli/repl.py` - REPL 交互循环
  - `neow/cli/commands.py` - 特殊命令处理
- `neow/core/` - 核心引擎层
  - `neow/core/__init__.py`
  - `neow/core/conversation.py` - 对话管理器
  - `neow/core/executor.py` - 工具执行器
  - `neow/core/context.py` - 上下文管理器
  - `neow/core/config.py` - 配置管理
- `neow/tools/` - 工具层
  - `neow/tools/__init__.py`
  - `neow/tools/file_ops.py` - 文件操作工具
  - `neow/tools/command.py` - 命令执行工具
  - `neow/tools/search.py` - 代码搜索工具
- `neow/models/` - AI 模型层
  - `neow/models/__init__.py`
  - `neow/models/anthropic.py` - Anthropic Claude 客户端
  - `neow/models/openai.py` - OpenAI 客户端
  - `neow/models/deepseek.py` - DeepSeek 客户端
- `neow/utils/` - 工具函数
  - `neow/utils/__init__.py`
  - `neow/utils/logger.py` - 日志工具
  - `neow/utils/formatter.py` - 输出格式化

### tests/ 测试目录
- `tests/__init__.py`
- `tests/test_cli.py` - CLI 测试
- `tests/test_core.py` - 核心组件测试
- `tests/test_tools.py` - 工具测试
- `tests/test_models.py` - 模型测试

---

## 任务分解

### 任务 1：项目初始化和基础结构

**文件：**
- 创建: `pyproject.toml`
- 创建: `requirements.txt`
- 创建: `README.md`
- 创建: `LICENSE`
- 创建: `.gitignore`
- 创建: `neow/__init__.py`
- 创建: `tests/__init__.py`

- [ ] **步骤 1：创建 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "neow"
version = "0.1.0"
description = "A lightweight, general-purpose AI CLI assistant"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Your Name", email = "your.email@example.com"},
]
keywords = ["ai", "cli", "assistant", "code", "editor"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Libraries :: Python Modules",
]
dependencies = [
    "anthropic>=0.39.0",
    "openai>=1.0.0",
    "rich>=13.0.0",
    "click>=8.0.0",
    "prompt-toolkit>=3.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-mock>=3.10.0",
    "black>=23.0.0",
    "flake8>=6.0.0",
    "mypy>=1.0.0",
]

[project.urls]
Homepage = "https://github.com/yourusername/neow"
Repository = "https://github.com/yourusername/neow"
Issues = "https://github.com/yourusername/neow/issues"

[project.scripts]
neow = "neow.cli.main:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["neow*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
addopts = "-v --cov=neow --cov-report=term-missing"

[tool.black]
line-length = 88
target-version = ["py310"]

[tool.flake8]
max-line-length = 88
extend-ignore = ["E203"]
```

- [ ] **步骤 2：创建 requirements.txt**

```
anthropic>=0.39.0
openai>=1.0.0
rich>=13.0.0
click>=8.0.0
prompt-toolkit>=3.0.0
pyyaml>=6.0
```

- [ ] **步骤 3：创建 README.md**

```markdown
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

## Usage

```bash
neow
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
```

- [ ] **步骤 4：创建 LICENSE**

```text
MIT License

Copyright (c) 2026 Your Name

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **步骤 5：创建 .gitignore**

```gitignore
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Translations
*.mo
*.pot

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# macOS
.DS_Store

# Neow specific
~/.neow/
.neow.json
```

- [ ] **步骤 6：创建 neow/__init__.py**

```python
"""Neow - A lightweight, general-purpose AI CLI assistant."""

__version__ = "0.1.0"
__author__ = "Your Name"
```

- [ ] **步骤 7：创建 tests/__init__.py**

```python
"""Tests for Neow CLI."""
```

- [ ] **步骤 8：提交初始项目结构**

```bash
git add pyproject.toml requirements.txt README.md LICENSE .gitignore neow/__init__.py tests/__init__.py
git commit -m "feat: initialize project structure with pyproject.toml and basic files"
```

---

### 任务 2：配置管理模块

**文件：**
- 创建: `neow/core/__init__.py`
- 创建: `neow/core/config.py`
- 创建: `tests/test_core.py`

- [ ] **步骤 1：编写配置管理测试**

```python
# tests/test_core.py
"""Tests for core modules."""

import json
import os
import tempfile
from pathlib import Path

import pytest

from neow.core.config import Config, ConfigError


class TestConfig:
    """Tests for Config class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        assert config.default_model == "deepseek-chat"
        assert "deepseek" in config.models
        assert "anthropic" in config.models
        assert "openai" in config.models

    def test_load_from_file(self, tmp_path):
        """Test loading configuration from file."""
        config_data = {
            "default_model": "gpt-4o",
            "models": {
                "openai": {
                    "api_key": "sk-test",
                    "model": "gpt-4o"
                }
            }
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = Config(config_file)
        assert config.default_model == "gpt-4o"
        assert config.models["openai"]["api_key"] == "sk-test"

    def test_load_from_env(self, monkeypatch):
        """Test loading API keys from environment variables."""
        monkeypatch.setenv("NEOW_DEEPSEEK_API_KEY", "sk-env-test")
        config = Config()
        assert config.models["deepseek"]["api_key"] == "sk-env-test"

    def test_invalid_config_file(self, tmp_path):
        """Test handling of invalid config file."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("invalid json")

        with pytest.raises(ConfigError):
            Config(config_file)

    def test_merge_configs(self, tmp_path):
        """Test merging file config with defaults."""
        config_data = {
            "default_model": "gpt-4o"
        }
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config_data))

        config = Config(config_file)
        assert config.default_model == "gpt-4o"
        # Should still have default models
        assert "deepseek" in config.models
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_core.py::TestConfig -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.core.config'`

- [ ] **步骤 3：创建 neow/core/__init__.py**

```python
"""Core modules for Neow CLI."""
```

- [ ] **步骤 4：实现配置管理模块**

```python
# neow/core/config.py
"""Configuration management for Neow CLI."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(Exception):
    """Configuration error."""
    pass


class Config:
    """Manages Neow configuration."""

    DEFAULT_CONFIG = {
        "default_model": "deepseek-chat",
        "models": {
            "anthropic": {
                "api_key": "",
                "model": "claude-sonnet-4-6"
            },
            "openai": {
                "api_key": "",
                "model": "gpt-4o"
            },
            "deepseek": {
                "api_key": "",
                "model": "deepseek-chat"
            }
        },
        "tools": {
            "enabled": [
                "read_file",
                "write_file",
                "edit_file",
                "execute_command",
                "search_code"
            ],
            "allowed_commands": [
                "ls",
                "cat",
                "grep",
                "find",
                "python",
                "npm"
            ]
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        self._config = self.DEFAULT_CONFIG.copy()
        self._load_config(config_path)
        self._load_env_vars()

    def _load_config(self, config_path: Optional[Path]) -> None:
        """Load configuration from file."""
        if config_path is None:
            # Try default locations
            home_config = Path.home() / ".neow" / "config.json"
            local_config = Path(".neow.json")

            if home_config.exists():
                config_path = home_config
            elif local_config.exists():
                config_path = local_config
            else:
                return

        if not config_path.exists():
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix in (".yml", ".yaml"):
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)

            if file_config:
                self._merge_config(self._config, file_config)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ConfigError(f"Invalid config file: {e}")

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Merge override config into base config."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _load_env_vars(self) -> None:
        """Load API keys from environment variables."""
        env_mapping = {
            "NEOW_DEEPSEEK_API_KEY": ("deepseek", "api_key"),
            "NEOW_ANTHROPIC_API_KEY": ("anthropic", "api_key"),
            "NEOW_OPENAI_API_KEY": ("openai", "api_key"),
        }

        for env_var, (model, key) in env_mapping.items():
            value = os.environ.get(env_var)
            if value:
                self._config["models"][model][key] = value

    @property
    def default_model(self) -> str:
        """Get default model name."""
        return self._config["default_model"]

    @property
    def models(self) -> Dict[str, Dict[str, str]]:
        """Get models configuration."""
        return self._config["models"]

    @property
    def tools(self) -> Dict[str, Any]:
        """Get tools configuration."""
        return self._config["tools"]

    def get_model_config(self, model_name: str) -> Dict[str, str]:
        """Get configuration for specific model.

        Args:
            model_name: Name of the model (anthropic, openai, deepseek).

        Returns:
            Model configuration dictionary.

        Raises:
            ConfigError: If model not found.
        """
        if model_name not in self._config["models"]:
            raise ConfigError(f"Model '{model_name}' not found in configuration")
        return self._config["models"][model_name]
```

- [ ] **步骤 5：运行测试确认通过**

```bash
pytest tests/test_core.py::TestConfig -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 6：提交配置管理模块**

```bash
git add neow/core/__init__.py neow/core/config.py tests/test_core.py
git commit -m "feat: add configuration management module with Config class"
```

---

### 任务 3：日志和格式化工具

**文件：**
- 创建: `neow/utils/__init__.py`
- 创建: `neow/utils/logger.py`
- 创建: `neow/utils/formatter.py`

- [ ] **步骤 1：创建 neow/utils/__init__.py**

```python
"""Utility functions for Neow CLI."""
```

- [ ] **步骤 2：实现日志工具**

```python
# neow/utils/logger.py
"""Logging utilities for Neow CLI."""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "neow",
    level: int = logging.INFO,
    log_file: Optional[Path] = None
) -> logging.Logger:
    """Setup logger with console and optional file handler.

    Args:
        name: Logger name.
        level: Logging level.
        log_file: Optional path to log file.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_format = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger


# Default logger
logger = setup_logger()
```

- [ ] **步骤 3：实现输出格式化工具**

```python
# neow/utils/formatter.py
"""Output formatting utilities for Neow CLI."""

from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


console = Console()


def print_user_message(message: str) -> None:
    """Print user message with formatting.

    Args:
        message: User message to print.
    """
    console.print(f"[bold blue]You:[/bold blue] {message}")


def print_assistant_message(message: str) -> None:
    """Print assistant message with formatting.

    Args:
        message: Assistant message to print.
    """
    console.print(f"[bold green]Assistant:[/bold green] {message}")


def print_tool_call(tool_name: str, parameters: Dict[str, Any]) -> None:
    """Print tool call with formatting.

    Args:
        tool_name: Name of the tool being called.
        parameters: Tool call parameters.
    """
    console.print(f"[bold yellow]Tool Call:[/bold yellow] {tool_name}")
    console.print(f"[dim]Parameters:[/dim] {parameters}")


def print_tool_result(result: str, is_error: bool = False) -> None:
    """Print tool result with formatting.

    Args:
        result: Tool execution result.
        is_error: Whether the result is an error.
    """
    color = "red" if is_error else "green"
    console.print(f"[bold {color}]Tool Result:[/bold {color}]")
    console.print(result)


def print_code(code: str, language: str = "python") -> None:
    """Print code with syntax highlighting.

    Args:
        code: Code to print.
        language: Programming language for syntax highlighting.
    """
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    console.print(syntax)


def print_markdown(content: str) -> None:
    """Print markdown content.

    Args:
        content: Markdown content to print.
    """
    md = Markdown(content)
    console.print(md)


def print_error(message: str) -> None:
    """Print error message.

    Args:
        message: Error message to print.
    """
    console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print warning message.

    Args:
        message: Warning message to print.
    """
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print info message.

    Args:
        message: Info message to print.
    """
    console.print(f"[bold cyan]Info:[/bold cyan] {message}")


def print_welcome() -> None:
    """Print welcome message."""
    welcome_text = """
# Neow CLI

A lightweight, general-purpose AI CLI assistant.

**Commands:**
- `/help` - Show this help message
- `/clear` - Clear conversation history
- `/exit` - Exit the CLI
- `/model <name>` - Switch AI model (deepseek, anthropic, openai)

**Usage:**
Type your message and press Enter to interact with the AI assistant.
"""
    print_markdown(welcome_text)
```

- [ ] **步骤 4：提交日志和格式化工具**

```bash
git add neow/utils/__init__.py neow/utils/logger.py neow/utils/formatter.py
git commit -m "feat: add logging and output formatting utilities"
```

---

### 任务 4：AI 模型客户端基础

**文件：**
- 创建: `neow/models/__init__.py`
- 创建: `neow/models/base.py`

- [ ] **步骤 1：创建 neow/models/__init__.py**

```python
"""AI model clients for Neow CLI."""
```

- [ ] **步骤 2：实现模型客户端基类**

```python
# neow/models/base.py
"""Base class for AI model clients."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ModelResponse:
    """Response from AI model."""

    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        usage: Optional[Dict[str, int]] = None
    ):
        """Initialize model response.

        Args:
            content: Response content.
            tool_calls: List of tool calls requested by the model.
            usage: Token usage statistics.
        """
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}

    @property
    def has_tool_calls(self) -> bool:
        """Check if response has tool calls."""
        return len(self.tool_calls) > 0


class BaseModelClient(ABC):
    """Base class for AI model clients."""

    def __init__(self, api_key: str, model: str):
        """Initialize model client.

        Args:
            api_key: API key for the model service.
            model: Model name/identifier.
        """
        self.api_key = api_key
        self.model = model

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> ModelResponse:
        """Send chat request to AI model.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Validate connection to AI model service.

        Returns:
            True if connection is valid, False otherwise.
        """
        pass
```

- [ ] **步骤 3：提交模型基类**

```bash
git add neow/models/__init__.py neow/models/base.py
git commit -m "feat: add base model client class with ModelResponse"
```

---

### 任务 5：DeepSeek 模型客户端

**文件：**
- 创建: `neow/models/deepseek.py`
- 修改: `tests/test_models.py`

- [ ] **步骤 1：编写 DeepSeek 客户端测试**

```python
# tests/test_models.py
"""Tests for AI model clients."""

from unittest.mock import MagicMock, patch

import pytest

from neow.models.base import ModelResponse
from neow.models.deepseek import DeepSeekClient


class TestDeepSeekClient:
    """Tests for DeepSeekClient."""

    def test_init(self):
        """Test client initialization."""
        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.api_key == "sk-test"
        assert client.model == "deepseek-chat"

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_chat_without_tools(self, mock_openai):
        """Test chat without tools."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_chat_with_tools(self, mock_openai):
        """Test chat with tools."""
        # Mock OpenAI response with tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function.name = "read_file"
        mock_tool_call.function.arguments = '{"file_path": "test.py"}'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 30

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        messages = [{"role": "user", "content": "Read test.py"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"}
                        }
                    }
                }
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "call_123"
        assert response.tool_calls[0]["function"]["name"] == "read_file"

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_validate_connection_success(self, mock_openai):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.validate_connection() is True

    @patch("neow.models.deepseek.openai.OpenAI")
    def test_validate_connection_failure(self, mock_openai):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Connection failed")
        mock_openai.return_value = mock_client

        client = DeepSeekClient(api_key="sk-test", model="deepseek-chat")
        assert client.validate_connection() is False
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_models.py::TestDeepSeekClient -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.models.deepseek'`

- [ ] **步骤 3：实现 DeepSeek 客户端**

```python
# neow/models/deepseek.py
"""DeepSeek model client."""

import json
from typing import Any, Dict, List, Optional

import openai

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class DeepSeekClient(BaseModelClient):
    """DeepSeek model client using OpenAI-compatible API."""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """Initialize DeepSeek client.

        Args:
            api_key: DeepSeek API key.
            model: Model name (default: deepseek-chat).
        """
        super().__init__(api_key, model)
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> ModelResponse:
        """Send chat request to DeepSeek.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # Parse tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            # Parse usage
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }

            return ModelResponse(
                content=choice.message.content or "",
                tool_calls=tool_calls,
                usage=usage
            )
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to DeepSeek API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"DeepSeek connection validation failed: {e}")
            return False
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_models.py::TestDeepSeekClient -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交 DeepSeek 客户端**

```bash
git add neow/models/deepseek.py tests/test_models.py
git commit -m "feat: add DeepSeek model client with OpenAI-compatible API"
```

---

### 任务 6：Anthropic Claude 模型客户端

**文件：**
- 创建: `neow/models/anthropic.py`
- 修改: `tests/test_models.py`

- [ ] **步骤 1：编写 Anthropic 客户端测试**

在 `tests/test_models.py` 中添加：

```python
from neow.models.anthropic import AnthropicClient


class TestAnthropicClient:
    """Tests for AnthropicClient."""

    def test_init(self):
        """Test client initialization."""
        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.api_key == "sk-ant-test"
        assert client.model == "claude-sonnet-4-6"

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_chat_without_tools(self, mock_anthropic):
        """Test chat without tools."""
        # Mock Anthropic response
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Hello!"
        mock_response.content[0].type = "text"
        mock_response.stop_reason = "end_turn"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_chat_with_tools(self, mock_anthropic):
        """Test chat with tools."""
        # Mock Anthropic response with tool use
        mock_tool_use = MagicMock()
        mock_tool_use.type = "tool_use"
        mock_tool_use.id = "toolu_123"
        mock_tool_use.name = "read_file"
        mock_tool_use.input = {"file_path": "test.py"}

        mock_response = MagicMock()
        mock_response.content = [mock_tool_use]
        mock_response.stop_reason = "tool_use"
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 10

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        messages = [{"role": "user", "content": "Read test.py"}]
        tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    }
                }
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "toolu_123"
        assert response.tool_calls[0]["function"]["name"] == "read_file"

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_validate_connection_success(self, mock_anthropic):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = MagicMock()
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.validate_connection() is True

    @patch("neow.models.anthropic.anthropic.Anthropic")
    def test_validate_connection_failure(self, mock_anthropic):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Connection failed")
        mock_anthropic.return_value = mock_client

        client = AnthropicClient(api_key="sk-ant-test", model="claude-sonnet-4-6")
        assert client.validate_connection() is False
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_models.py::TestAnthropicClient -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.models.anthropic'`

- [ ] **步骤 3：实现 Anthropic 客户端**

```python
# neow/models/anthropic.py
"""Anthropic Claude model client."""

import json
from typing import Any, Dict, List, Optional

import anthropic

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class AnthropicClient(BaseModelClient):
    """Anthropic Claude model client."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key.
            model: Model name (default: claude-sonnet-4-6).
        """
        super().__init__(api_key, model)
        self.client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> ModelResponse:
        """Send chat request to Anthropic Claude.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": messages,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)

            # Parse content
            content = ""
            tool_calls = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append({
                        "id": block.id,
                        "function": {
                            "name": block.name,
                            "arguments": json.dumps(block.input)
                        }
                    })

            # Parse usage
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                }

            return ModelResponse(
                content=content,
                tool_calls=tool_calls,
                usage=usage
            )
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to Anthropic API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic connection validation failed: {e}")
            return False
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_models.py::TestAnthropicClient -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交 Anthropic 客户端**

```bash
git add neow/models/anthropic.py tests/test_models.py
git commit -m "feat: add Anthropic Claude model client"
```

---

### 任务 7：OpenAI 模型客户端

**文件：**
- 创建: `neow/models/openai.py`
- 修改: `tests/test_models.py`

- [ ] **步骤 1：编写 OpenAI 客户端测试**

在 `tests/test_models.py` 中添加：

```python
from neow.models.openai import OpenAIClient


class TestOpenAIClient:
    """Tests for OpenAIClient."""

    def test_init(self):
        """Test client initialization."""
        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.api_key == "sk-test"
        assert client.model == "gpt-4o"

    @patch("neow.models.openai.openai.OpenAI")
    def test_chat_without_tools(self, mock_openai):
        """Test chat without tools."""
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages)

        assert isinstance(response, ModelResponse)
        assert response.content == "Hello!"
        assert response.has_tool_calls is False
        assert response.usage["total_tokens"] == 15

    @patch("neow.models.openai.openai.OpenAI")
    def test_chat_with_tools(self, mock_openai):
        """Test chat with tools."""
        # Mock OpenAI response with tool call
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_456"
        mock_tool_call.function.name = "write_file"
        mock_tool_call.function.arguments = '{"file_path": "test.py", "content": "print(1)"}'

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_response.usage.prompt_tokens = 20
        mock_response.usage.completion_tokens = 10
        mock_response.usage.total_tokens = 30

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        messages = [{"role": "user", "content": "Write test.py"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string"},
                            "content": {"type": "string"}
                        }
                    }
                }
            }
        ]
        response = client.chat(messages, tools=tools)

        assert response.has_tool_calls is True
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["id"] == "call_456"
        assert response.tool_calls[0]["function"]["name"] == "write_file"

    @patch("neow.models.openai.openai.OpenAI")
    def test_validate_connection_success(self, mock_openai):
        """Test successful connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.return_value = []
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.validate_connection() is True

    @patch("neow.models.openai.openai.OpenAI")
    def test_validate_connection_failure(self, mock_openai):
        """Test failed connection validation."""
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("Connection failed")
        mock_openai.return_value = mock_client

        client = OpenAIClient(api_key="sk-test", model="gpt-4o")
        assert client.validate_connection() is False
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_models.py::TestOpenAIClient -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.models.openai'`

- [ ] **步骤 3：实现 OpenAI 客户端**

```python
# neow/models/openai.py
"""OpenAI model client."""

import json
from typing import Any, Dict, List, Optional

import openai

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class OpenAIClient(BaseModelClient):
    """OpenAI model client."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key.
            model: Model name (default: gpt-4o).
        """
        super().__init__(api_key, model)
        self.client = openai.OpenAI(api_key=api_key)

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None
    ) -> ModelResponse:
        """Send chat request to OpenAI.

        Args:
            messages: List of message dictionaries.
            system_prompt: Optional system prompt.
            tools: Optional list of tool definitions.

        Returns:
            ModelResponse object.
        """
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        # Prepare request kwargs
        kwargs = {
            "model": self.model,
            "messages": full_messages,
        }

        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.chat.completions.create(**kwargs)
            choice = response.choices[0]

            # Parse tool calls
            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            # Parse usage
            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }

            return ModelResponse(
                content=choice.message.content or "",
                tool_calls=tool_calls,
                usage=usage
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def validate_connection(self) -> bool:
        """Validate connection to OpenAI API.

        Returns:
            True if connection is valid, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI connection validation failed: {e}")
            return False
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_models.py::TestOpenAIClient -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交 OpenAI 客户端**

```bash
git add neow/models/openai.py tests/test_models.py
git commit -m "feat: add OpenAI model client"
```

---

### 任务 8：工具执行器基础

**文件：**
- 创建: `neow/tools/__init__.py`
- 创建: `neow/core/executor.py`
- 修改: `tests/test_core.py`

- [ ] **步骤 1：创建 neow/tools/__init__.py**

```python
"""Tools for Neow CLI."""
```

- [ ] **步骤 2：编写工具执行器测试**

在 `tests/test_core.py` 中添加：

```python
from neow.core.executor import ToolExecutor, ToolError


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def test_init(self):
        """Test executor initialization."""
        executor = ToolExecutor()
        assert "read_file" in executor.tools
        assert "write_file" in executor.tools
        assert "edit_file" in executor.tools
        assert "execute_command" in executor.tools
        assert "search_code" in executor.tools

    def test_execute_unknown_tool(self):
        """Test executing unknown tool."""
        executor = ToolExecutor()
        with pytest.raises(ToolError):
            executor.execute("unknown_tool", {})

    def test_register_custom_tool(self):
        """Test registering custom tool."""
        executor = ToolExecutor()

        def custom_tool(param: str) -> str:
            return f"Custom: {param}"

        executor.register_tool("custom", custom_tool)
        assert "custom" in executor.tools

        result = executor.execute("custom", {"param": "test"})
        assert result == "Custom: test"
```

- [ ] **步骤 3：运行测试确认失败**

```bash
pytest tests/test_core.py::TestToolExecutor -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.core.executor'`

- [ ] **步骤 4：实现工具执行器**

```python
# neow/core/executor.py
"""Tool executor for Neow CLI."""

from typing import Any, Callable, Dict, Optional

from neow.utils.logger import logger


class ToolError(Exception):
    """Tool execution error."""
    pass


class ToolExecutor:
    """Executes tools requested by AI models."""

    def __init__(self):
        """Initialize tool executor."""
        self.tools: Dict[str, Callable] = {}

    def register_tool(self, name: str, func: Callable) -> None:
        """Register a tool.

        Args:
            name: Tool name.
            func: Tool function.
        """
        self.tools[name] = func
        logger.debug(f"Registered tool: {name}")

    def execute(self, tool_name: str, parameters: Dict[str, Any]) -> str:
        """Execute a tool.

        Args:
            tool_name: Name of the tool to execute.
            parameters: Tool parameters.

        Returns:
            Tool execution result as string.

        Raises:
            ToolError: If tool not found or execution fails.
        """
        if tool_name not in self.tools:
            raise ToolError(f"Tool '{tool_name}' not found")

        try:
            result = self.tools[tool_name](**parameters)
            logger.debug(f"Tool '{tool_name}' executed successfully")
            return str(result)
        except Exception as e:
            logger.error(f"Tool '{tool_name}' execution failed: {e}")
            raise ToolError(f"Tool execution failed: {e}")

    def get_tool_definitions(self) -> list:
        """Get tool definitions for AI models.

        Returns:
            List of tool definitions.
        """
        # This will be implemented when we add specific tools
        return []
```

- [ ] **步骤 5：运行测试确认通过**

```bash
pytest tests/test_core.py::TestToolExecutor -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 6：提交工具执行器**

```bash
git add neow/tools/__init__.py neow/core/executor.py tests/test_core.py
git commit -m "feat: add tool executor with tool registration"
```

---

### 任务 9：文件操作工具

**文件：**
- 创建: `neow/tools/file_ops.py`
- 修改: `tests/test_tools.py`

- [ ] **步骤 1：编写文件操作工具测试**

```python
# tests/test_tools.py
"""Tests for tools."""

import os
import tempfile
from pathlib import Path

import pytest

from neow.tools.file_ops import (
    read_file,
    write_file,
    edit_file,
    FileError
)


class TestFileOps:
    """Tests for file operation tools."""

    def test_read_file(self, tmp_path):
        """Test reading a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = read_file(str(test_file))
        assert result == "Hello, World!"

    def test_read_file_not_found(self):
        """Test reading non-existent file."""
        with pytest.raises(FileError):
            read_file("/nonexistent/file.txt")

    def test_write_file(self, tmp_path):
        """Test writing a file."""
        test_file = tmp_path / "test.txt"

        result = write_file(str(test_file), "Hello, World!")
        assert test_file.read_text() == "Hello, World!"
        assert "successfully" in result.lower()

    def test_write_file_creates_dirs(self, tmp_path):
        """Test writing a file creates parent directories."""
        test_file = tmp_path / "subdir" / "test.txt"

        write_file(str(test_file), "Hello")
        assert test_file.read_text() == "Hello"

    def test_edit_file(self, tmp_path):
        """Test editing a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        result = edit_file(str(test_file), "World", "Python")
        assert test_file.read_text() == "Hello, Python!"
        assert "successfully" in result.lower()

    def test_edit_file_not_found(self):
        """Test editing non-existent file."""
        with pytest.raises(FileError):
            edit_file("/nonexistent/file.txt", "old", "new")

    def test_edit_file_pattern_not_found(self, tmp_path):
        """Test editing file with non-existent pattern."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        with pytest.raises(FileError):
            edit_file(str(test_file), "NotFound", "Replacement")
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_tools.py::TestFileOps -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.tools.file_ops'`

- [ ] **步骤 3：实现文件操作工具**

```python
# neow/tools/file_ops.py
"""File operation tools for Neow CLI."""

from pathlib import Path
from typing import Optional

from neow.utils.logger import logger


class FileError(Exception):
    """File operation error."""
    pass


def read_file(file_path: str) -> str:
    """Read file content.

    Args:
        file_path: Path to the file.

    Returns:
        File content as string.

    Raises:
        FileError: If file cannot be read.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8")
        logger.debug(f"Read file: {file_path}")
        return content
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        raise FileError(f"Failed to read file: {e}")


def write_file(file_path: str, content: str) -> str:
    """Write content to file.

    Args:
        file_path: Path to the file.
        content: Content to write.

    Returns:
        Success message.

    Raises:
        FileError: If file cannot be written.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.debug(f"Wrote file: {file_path}")
        return f"File written successfully: {file_path}"
    except Exception as e:
        logger.error(f"Failed to write file {file_path}: {e}")
        raise FileError(f"Failed to write file: {e}")


def edit_file(file_path: str, old_text: str, new_text: str) -> str:
    """Edit file by replacing text.

    Args:
        file_path: Path to the file.
        old_text: Text to replace.
        new_text: Replacement text.

    Returns:
        Success message.

    Raises:
        FileError: If file cannot be edited.
    """
    try:
        path = Path(file_path)
        if not path.exists():
            raise FileError(f"File not found: {file_path}")

        content = path.read_text(encoding="utf-8")

        if old_text not in content:
            raise FileError(f"Text not found in file: {old_text}")

        new_content = content.replace(old_text, new_text)
        path.write_text(new_content, encoding="utf-8")
        logger.debug(f"Edited file: {file_path}")
        return f"File edited successfully: {file_path}"
    except FileError:
        raise
    except Exception as e:
        logger.error(f"Failed to edit file {file_path}: {e}")
        raise FileError(f"Failed to edit file: {e}")
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_tools.py::TestFileOps -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交文件操作工具**

```bash
git add neow/tools/file_ops.py tests/test_tools.py
git commit -m "feat: add file operation tools (read, write, edit)"
```

---

### 任务 10：命令执行工具

**文件：**
- 创建: `neow/tools/command.py`
- 修改: `tests/test_tools.py`

- [ ] **步骤 1：编写命令执行工具测试**

在 `tests/test_tools.py` 中添加：

```python
from neow.tools.command import execute_command, CommandError


class TestCommand:
    """Tests for command execution tools."""

    def test_execute_command_success(self):
        """Test executing a successful command."""
        result = execute_command("echo hello")
        assert "hello" in result

    def test_execute_command_with_output(self):
        """Test executing command with output."""
        result = execute_command("python -c \"print('test')\"")
        assert "test" in result

    def test_execute_command_failure(self):
        """Test executing a failing command."""
        with pytest.raises(CommandError):
            execute_command("nonexistent_command")

    def test_execute_command_timeout(self):
        """Test command timeout."""
        with pytest.raises(CommandError):
            execute_command("python -c \"import time; time.sleep(10)\"", timeout=1)
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_tools.py::TestCommand -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.tools.command'`

- [ ] **步骤 3：实现命令执行工具**

```python
# neow/tools/command.py
"""Command execution tools for Neow CLI."""

import subprocess
from typing import Optional

from neow.utils.logger import logger


class CommandError(Exception):
    """Command execution error."""
    pass


def execute_command(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None
) -> str:
    """Execute a shell command.

    Args:
        command: Command to execute.
        timeout: Timeout in seconds (default: 30).
        cwd: Working directory (optional).

    Returns:
        Command output as string.

    Raises:
        CommandError: If command fails or times out.
    """
    try:
        logger.debug(f"Executing command: {command}")

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )

        if result.returncode != 0:
            error_msg = result.stderr or f"Command failed with return code {result.returncode}"
            logger.error(f"Command failed: {error_msg}")
            raise CommandError(error_msg)

        logger.debug(f"Command output: {result.stdout[:100]}...")
        return result.stdout

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds")
        raise CommandError(f"Command timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Command execution failed: {e}")
        raise CommandError(f"Command execution failed: {e}")
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_tools.py::TestCommand -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交命令执行工具**

```bash
git add neow/tools/command.py tests/test_tools.py
git commit -m "feat: add command execution tool with timeout support"
```

---

### 任务 11：代码搜索工具

**文件：**
- 创建: `neow/tools/search.py`
- 修改: `tests/test_tools.py`

- [ ] **步骤 1：编写代码搜索工具测试**

在 `tests/test_tools.py` 中添加：

```python
from neow.tools.search import search_code, SearchError


class TestSearch:
    """Tests for code search tools."""

    def test_search_code(self, tmp_path):
        """Test searching code in files."""
        # Create test files
        (tmp_path / "test1.py").write_text("def hello():\n    print('hello')")
        (tmp_path / "test2.py").write_text("def world():\n    print('world')")

        results = search_code("hello", str(tmp_path))
        assert len(results) > 0
        assert any("hello" in r["content"] for r in results)

    def test_search_code_with_pattern(self, tmp_path):
        """Test searching code with file pattern."""
        (tmp_path / "test.py").write_text("def hello(): pass")
        (tmp_path / "test.txt").write_text("hello world")

        results = search_code("hello", str(tmp_path), file_pattern="*.py")
        assert len(results) == 1
        assert results[0]["file"].endswith(".py")

    def test_search_code_no_results(self, tmp_path):
        """Test searching with no results."""
        (tmp_path / "test.py").write_text("def hello(): pass")

        results = search_code("nonexistent", str(tmp_path))
        assert len(results) == 0

    def test_search_code_invalid_directory(self):
        """Test searching in invalid directory."""
        with pytest.raises(SearchError):
            search_code("test", "/nonexistent/directory")
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_tools.py::TestSearch -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.tools.search'`

- [ ] **步骤 3：实现代码搜索工具**

```python
# neow/tools/search.py
"""Code search tools for Neow CLI."""

import re
from pathlib import Path
from typing import Dict, List, Optional

from neow.utils.logger import logger


class SearchError(Exception):
    """Code search error."""
    pass


def search_code(
    query: str,
    directory: str,
    file_pattern: str = "*",
    max_results: int = 50
) -> List[Dict[str, str]]:
    """Search for code patterns in files.

    Args:
        query: Search query (supports regex).
        directory: Directory to search in.
        file_pattern: File pattern to match (e.g., "*.py").
        max_results: Maximum number of results.

    Returns:
        List of dictionaries with 'file', 'line', 'content' keys.

    Raises:
        SearchError: If search fails.
    """
    try:
        search_dir = Path(directory)
        if not search_dir.exists():
            raise SearchError(f"Directory not found: {directory}")

        results = []
        pattern = re.compile(query, re.IGNORECASE)

        for file_path in search_dir.rglob(file_pattern):
            if not file_path.is_file():
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        results.append({
                            "file": str(file_path),
                            "line": str(line_num),
                            "content": line.strip()
                        })

                        if len(results) >= max_results:
                            logger.debug(f"Reached max results ({max_results})")
                            return results
            except (UnicodeDecodeError, PermissionError):
                # Skip binary files or files without read permission
                continue

        logger.debug(f"Found {len(results)} results for query: {query}")
        return results

    except SearchError:
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise SearchError(f"Search failed: {e}")


def grep_code(
    pattern: str,
    directory: str,
    file_pattern: str = "*"
) -> List[Dict[str, str]]:
    """Search for code using grep-like syntax.

    Args:
        pattern: Search pattern.
        directory: Directory to search in.
        file_pattern: File pattern to match.

    Returns:
        List of search results.
    """
    return search_code(pattern, directory, file_pattern)
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_tools.py::TestSearch -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交代码搜索工具**

```bash
git add neow/tools/search.py tests/test_tools.py
git commit -m "feat: add code search tools with regex support"
```

---

### 任务 12：对话管理器

**文件：**
- 创建: `neow/core/conversation.py`
- 修改: `tests/test_core.py`

- [ ] **步骤 1：编写对话管理器测试**

在 `tests/test_core.py` 中添加：

```python
from unittest.mock import MagicMock

from neow.core.conversation import ConversationManager


class TestConversationManager:
    """Tests for ConversationManager."""

    def test_init(self):
        """Test conversation manager initialization."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)
        assert len(manager.messages) == 0
        assert manager.system_prompt == ""

    def test_add_message(self):
        """Test adding messages."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_message("user", "Hello")
        assert len(manager.messages) == 1
        assert manager.messages[0]["role"] == "user"
        assert manager.messages[0]["content"] == "Hello"

    def test_clear_history(self):
        """Test clearing history."""
        mock_client = MagicMock()
        manager = ConversationManager(mock_client)

        manager.add_message("user", "Hello")
        manager.add_message("assistant", "Hi")
        manager.clear_history()
        assert len(manager.messages) == 0

    def test_get_response(self):
        """Test getting response."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello!"
        mock_response.has_tool_calls = False
        mock_response.tool_calls = []
        mock_response.usage = {"total_tokens": 10}
        mock_client.chat.return_value = mock_response

        manager = ConversationManager(mock_client)
        response = manager.get_response("Hello")

        assert response.content == "Hello!"
        assert len(manager.messages) == 2  # user + assistant
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_core.py::TestConversationManager -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.core.conversation'`

- [ ] **步骤 3：实现对话管理器**

```python
# neow/core/conversation.py
"""Conversation manager for Neow CLI."""

from typing import Any, Dict, List, Optional

from neow.models.base import BaseModelClient, ModelResponse
from neow.utils.logger import logger


class ConversationManager:
    """Manages conversation history and AI model interactions."""

    def __init__(self, model_client: BaseModelClient):
        """Initialize conversation manager.

        Args:
            model_client: AI model client instance.
        """
        self.model_client = model_client
        self.messages: List[Dict[str, str]] = []
        self.system_prompt: str = ""
        self.tools: List[Dict[str, Any]] = []

    def set_system_prompt(self, prompt: str) -> None:
        """Set system prompt.

        Args:
            prompt: System prompt text.
        """
        self.system_prompt = prompt
        logger.debug(f"System prompt set ({len(prompt)} chars)")

    def set_tools(self, tools: List[Dict[str, Any]]) -> None:
        """Set available tools.

        Args:
            tools: List of tool definitions.
        """
        self.tools = tools
        logger.debug(f"Set {len(tools)} tools")

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history.

        Args:
            role: Message role (user, assistant, tool).
            content: Message content.
        """
        self.messages.append({"role": role, "content": content})
        logger.debug(f"Added {role} message ({len(content)} chars)")

    def get_response(self, user_input: str) -> ModelResponse:
        """Get AI response for user input.

        Args:
            user_input: User input text.

        Returns:
            ModelResponse object.
        """
        # Add user message
        self.add_message("user", user_input)

        # Get response from model
        response = self.model_client.chat(
            messages=self.messages,
            system_prompt=self.system_prompt if self.system_prompt else None,
            tools=self.tools if self.tools else None
        )

        # Add assistant message
        self.add_message("assistant", response.content)

        logger.info(
            f"Response generated ({response.usage.get('total_tokens', 0)} tokens)"
        )

        return response

    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add tool result to conversation history.

        Args:
            tool_call_id: Tool call ID.
            result: Tool execution result.
        """
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result
        })
        logger.debug(f"Added tool result for {tool_call_id}")

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.debug("Conversation history cleared")

    def get_history(self) -> List[Dict[str, str]]:
        """Get conversation history.

        Returns:
            List of message dictionaries.
        """
        return self.messages.copy()
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_core.py::TestConversationManager -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交对话管理器**

```bash
git add neow/core/conversation.py tests/test_core.py
git commit -m "feat: add conversation manager with history and tool support"
```

---

### 任务 13：上下文管理器

**文件：**
- 创建: `neow/core/context.py`
- 修改: `tests/test_core.py`

- [ ] **步骤 1：编写上下文管理器测试**

在 `tests/test_core.py` 中添加：

```python
from neow.core.context import ContextManager


class TestContextManager:
    """Tests for ContextManager."""

    def test_init(self, tmp_path):
        """Test context manager initialization."""
        manager = ContextManager(str(tmp_path))
        assert manager.project_root == tmp_path

    def test_get_project_structure(self, tmp_path):
        """Test getting project structure."""
        # Create test structure
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# Test")

        manager = ContextManager(str(tmp_path))
        structure = manager.get_project_structure()

        assert "src" in structure
        assert "README.md" in structure

    def test_get_relevant_files(self, tmp_path):
        """Test getting relevant files."""
        # Create test files
        (tmp_path / "main.py").write_text("def main(): pass")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "README.md").write_text("# Documentation")

        manager = ContextManager(str(tmp_path))
        files = manager.get_relevant_files("main function")

        assert len(files) > 0

    def test_build_context(self, tmp_path):
        """Test building context."""
        # Create test file
        (tmp_path / "test.py").write_text("def hello(): pass")

        manager = ContextManager(str(tmp_path))
        context = manager.build_context("tell me about test.py")

        assert "test.py" in context
```

- [ ] **步骤 2：运行测试确认失败**

```bash
pytest tests/test_core.py::TestContextManager -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.core.context'`

- [ ] **步骤 3：实现上下文管理器**

```python
# neow/core/context.py
"""Context manager for Neow CLI."""

from pathlib import Path
from typing import Dict, List, Optional

from neow.utils.logger import logger


class ContextManager:
    """Manages project context for AI model."""

    def __init__(self, project_root: str):
        """Initialize context manager.

        Args:
            project_root: Root directory of the project.
        """
        self.project_root = Path(project_root)
        self.file_cache: Dict[str, str] = {}

    def get_project_structure(self, max_depth: int = 3) -> Dict[str, any]:
        """Get project directory structure.

        Args:
            max_depth: Maximum depth to traverse.

        Returns:
            Dictionary representing project structure.
        """
        structure = {}
        self._build_structure(self.project_root, structure, max_depth, 0)
        return structure

    def _build_structure(
        self,
        path: Path,
        structure: Dict,
        max_depth: int,
        current_depth: int
    ) -> None:
        """Recursively build directory structure."""
        if current_depth >= max_depth:
            return

        try:
            for item in sorted(path.iterdir()):
                # Skip hidden files and common non-essential directories
                if item.name.startswith(".") or item.name in (
                    "__pycache__", "node_modules", ".git", "venv", ".venv"
                ):
                    continue

                if item.is_dir():
                    structure[item.name] = {}
                    self._build_structure(
                        item,
                        structure[item.name],
                        max_depth,
                        current_depth + 1
                    )
                else:
                    structure[item.name] = None
        except PermissionError:
            pass

    def get_relevant_files(
        self,
        query: str,
        max_files: int = 10
    ) -> List[Dict[str, str]]:
        """Get files relevant to a query.

        Args:
            query: Search query.
            max_files: Maximum number of files to return.

        Returns:
            List of dictionaries with 'path' and 'content' keys.
        """
        relevant_files = []
        query_lower = query.lower()

        # Search for files that might be relevant
        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file():
                continue

            # Skip hidden files and non-text files
            if file_path.name.startswith("."):
                continue

            # Check if file name matches query
            if query_lower in file_path.name.lower():
                content = self._read_file(file_path)
                if content:
                    relevant_files.append({
                        "path": str(file_path.relative_to(self.project_root)),
                        "content": content[:1000]  # Limit content size
                    })

            if len(relevant_files) >= max_files:
                break

        return relevant_files

    def _read_file(self, file_path: Path) -> Optional[str]:
        """Read file content with caching.

        Args:
            file_path: Path to file.

        Returns:
            File content or None if cannot read.
        """
        cache_key = str(file_path)
        if cache_key in self.file_cache:
            return self.file_cache[cache_key]

        try:
            content = file_path.read_text(encoding="utf-8")
            self.file_cache[cache_key] = content
            return content
        except (UnicodeDecodeError, PermissionError):
            return None

    def build_context(self, user_input: str) -> str:
        """Build context string for AI model.

        Args:
            user_input: User input to analyze.

        Returns:
            Context string.
        """
        context_parts = []

        # Add project structure
        structure = self.get_project_structure(max_depth=2)
        context_parts.append("Project structure:")
        context_parts.append(self._format_structure(structure, indent=2))

        # Add relevant files
        relevant_files = self.get_relevant_files(user_input)
        if relevant_files:
            context_parts.append("\nRelevant files:")
            for file_info in relevant_files:
                context_parts.append(f"\n{file_info['path']}:")
                context_parts.append(file_info["content"])

        return "\n".join(context_parts)

    def _format_structure(
        self,
        structure: Dict,
        indent: int = 0
    ) -> str:
        """Format structure dictionary as string.

        Args:
            structure: Structure dictionary.
            indent: Indentation level.

        Returns:
            Formatted string.
        """
        lines = []
        prefix = " " * indent

        for key, value in structure.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}/")
                if value:
                    lines.append(self._format_structure(value, indent + 2))
            else:
                lines.append(f"{prefix}{key}")

        return "\n".join(lines)
```

- [ ] **步骤 4：运行测试确认通过**

```bash
pytest tests/test_core.py::TestContextManager -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 5：提交上下文管理器**

```bash
git add neow/core/context.py tests/test_core.py
git commit -m "feat: add context manager for project understanding"
```

---

### 任务 14：CLI 入口和 REPL

**文件：**
- 创建: `neow/cli/__init__.py`
- 创建: `neow/cli/main.py`
- 创建: `neow/cli/repl.py`
- 创建: `neow/cli/commands.py`
- 修改: `tests/test_cli.py`

- [ ] **步骤 1：创建 neow/cli/__init__.py**

```python
"""CLI modules for Neow CLI."""
```

- [ ] **步骤 2：编写 CLI 测试**

```python
# tests/test_cli.py
"""Tests for CLI modules."""

from unittest.mock import MagicMock, patch

import pytest

from neow.cli.commands import parse_command, Command


class TestCommands:
    """Tests for command parsing."""

    def test_parse_help_command(self):
        """Test parsing help command."""
        result = parse_command("/help")
        assert result.command == Command.HELP

    def test_parse_clear_command(self):
        """Test parsing clear command."""
        result = parse_command("/clear")
        assert result.command == Command.CLEAR

    def test_parse_exit_command(self):
        """Test parsing exit command."""
        result = parse_command("/exit")
        assert result.command == Command.EXIT

    def test_parse_model_command(self):
        """Test parsing model command."""
        result = parse_command("/model deepseek")
        assert result.command == Command.MODEL
        assert result.args == "deepseek"

    def test_parse_invalid_command(self):
        """Test parsing invalid command."""
        result = parse_command("not a command")
        assert result.command is None

    def test_parse_empty_input(self):
        """Test parsing empty input."""
        result = parse_command("")
        assert result.command is None
```

- [ ] **步骤 3：运行测试确认失败**

```bash
pytest tests/test_cli.py -v
```

预期输出：`FAIL` - `ModuleNotFoundError: No module named 'neow.cli.commands'`

- [ ] **步骤 4：实现命令解析模块**

```python
# neow/cli/commands.py
"""Command parsing for Neow CLI."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Command(Enum):
    """Available commands."""
    HELP = "help"
    CLEAR = "clear"
    EXIT = "exit"
    MODEL = "model"


@dataclass
class ParsedCommand:
    """Parsed command result."""
    command: Optional[Command]
    args: Optional[str] = None


def parse_command(user_input: str) -> ParsedCommand:
    """Parse user input for commands.

    Args:
        user_input: User input string.

    Returns:
        ParsedCommand object.
    """
    user_input = user_input.strip()

    if not user_input or not user_input.startswith("/"):
        return ParsedCommand(command=None)

    parts = user_input.split(maxsplit=1)
    command_str = parts[0].lower()
    args = parts[1] if len(parts) > 1 else None

    command_map = {
        "/help": Command.HELP,
        "/clear": Command.CLEAR,
        "/exit": Command.EXIT,
        "/model": Command.MODEL,
    }

    command = command_map.get(command_str)
    if command:
        return ParsedCommand(command=command, args=args)

    return ParsedCommand(command=None)
```

- [ ] **步骤 5：运行测试确认通过**

```bash
pytest tests/test_cli.py::TestCommands -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 6：实现 REPL 模块**

```python
# neow/cli/repl.py
"""REPL (Read-Eval-Print Loop) for Neow CLI."""

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from neow.cli.commands import Command, parse_command
from neow.core.conversation import ConversationManager
from neow.utils.formatter import (
    print_welcome,
    print_user_message,
    print_assistant_message,
    print_tool_call,
    print_tool_result,
    print_error,
    print_info,
)
from neow.utils.logger import logger


class REPL:
    """Interactive REPL for Neow CLI."""

    def __init__(self, conversation: ConversationManager):
        """Initialize REPL.

        Args:
            conversation: ConversationManager instance.
        """
        self.conversation = conversation
        self.session: Optional[PromptSession] = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup prompt session with history."""
        try:
            history = FileHistory(".neow_history")
            self.session = PromptSession(history=history)
        except Exception as e:
            logger.warning(f"Failed to setup history: {e}")
            self.session = PromptSession()

    def start(self) -> None:
        """Start the REPL loop."""
        print_welcome()

        while True:
            try:
                user_input = self._get_input()
                if not user_input:
                    continue

                # Check for commands
                parsed = parse_command(user_input)
                if parsed.command:
                    if self._handle_command(parsed):
                        break
                    continue

                # Process with AI
                self._process_input(user_input)

            except KeyboardInterrupt:
                print_info("\nUse /exit to quit")
            except EOFError:
                break
            except Exception as e:
                print_error(f"Error: {e}")
                logger.error(f"REPL error: {e}")

    def _get_input(self) -> str:
        """Get user input.

        Returns:
            User input string.
        """
        try:
            return self.session.prompt("You: ")
        except KeyboardInterrupt:
            return ""
        except EOFError:
            raise

    def _handle_command(self, parsed) -> bool:
        """Handle parsed command.

        Args:
            parsed: ParsedCommand object.

        Returns:
            True if should exit, False otherwise.
        """
        if parsed.command == Command.HELP:
            print_welcome()
        elif parsed.command == Command.CLEAR:
            self.conversation.clear_history()
            print_info("Conversation history cleared")
        elif parsed.command == Command.EXIT:
            print_info("Goodbye!")
            return True
        elif parsed.command == Command.MODEL:
            if parsed.args:
                print_info(f"Switching to model: {parsed.args}")
                # TODO: Implement model switching
            else:
                print_error("Please specify a model name")

        return False

    def _process_input(self, user_input: str) -> None:
        """Process user input with AI.

        Args:
            user_input: User input string.
        """
        try:
            response = self.conversation.get_response(user_input)

            # Handle tool calls
            if response.has_tool_calls:
                for tool_call in response.tool_calls:
                    print_tool_call(
                        tool_call["function"]["name"],
                        tool_call["function"]["arguments"]
                    )
                    # TODO: Execute tool and add result

            # Print response
            if response.content:
                print_assistant_message(response.content)

        except Exception as e:
            print_error(f"Failed to get response: {e}")
            logger.error(f"Failed to get response: {e}")
```

- [ ] **步骤 7：实现 CLI 主入口**

```python
# neow/cli/main.py
"""Main entry point for Neow CLI."""

import sys
from pathlib import Path

import click

from neow.core.config import Config
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.context import ContextManager
from neow.models.deepseek import DeepSeekClient
from neow.models.anthropic import AnthropicClient
from neow.models.openai import OpenAIClient
from neow.tools.file_ops import read_file, write_file, edit_file
from neow.tools.command import execute_command
from neow.tools.search import search_code
from neow.cli.repl import REPL
from neow.utils.logger import setup_logger
from neow.utils.formatter import print_error, print_info


def create_model_client(config: Config, model_name: str):
    """Create model client based on configuration.

    Args:
        config: Configuration object.
        model_name: Name of the model to create.

    Returns:
        Model client instance.
    """
    model_config = config.get_model_config(model_name)

    if model_name == "deepseek":
        return DeepSeekClient(
            api_key=model_config["api_key"],
            model=model_config["model"]
        )
    elif model_name == "anthropic":
        return AnthropicClient(
            api_key=model_config["api_key"],
            model=model_config["model"]
        )
    elif model_name == "openai":
        return OpenAIClient(
            api_key=model_config["api_key"],
            model=model_config["model"]
        )
    else:
        raise ValueError(f"Unknown model: {model_name}")


def setup_tools(executor: ToolExecutor) -> None:
    """Register tools with executor.

    Args:
        executor: ToolExecutor instance.
    """
    executor.register_tool("read_file", read_file)
    executor.register_tool("write_file", write_file)
    executor.register_tool("edit_file", edit_file)
    executor.register_tool("execute_command", execute_command)
    executor.register_tool("search_code", search_code)


@click.command()
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--model", "-m", type=str, help="AI model to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(config: str, model: str, verbose: bool):
    """Neow - A lightweight, general-purpose AI CLI assistant."""
    # Setup logging
    log_level = "DEBUG" if verbose else "INFO"
    setup_logger(level=log_level)

    try:
        # Load configuration
        config_path = Path(config) if config else None
        config = Config(config_path)

        # Determine model to use
        model_name = model or config.default_model
        print_info(f"Using model: {model_name}")

        # Create model client
        model_client = create_model_client(config, model_name)

        # Validate connection
        if not model_client.validate_connection():
            print_error(f"Failed to connect to {model_name} API")
            sys.exit(1)

        # Setup conversation manager
        conversation = ConversationManager(model_client)

        # Setup context manager
        context = ContextManager(".")

        # Setup tool executor
        executor = ToolExecutor()
        setup_tools(executor)

        # Start REPL
        repl = REPL(conversation)
        repl.start()

    except Exception as e:
        print_error(f"Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **步骤 8：运行测试确认通过**

```bash
pytest tests/test_cli.py -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 9：提交 CLI 模块**

```bash
git add neow/cli/__init__.py neow/cli/main.py neow/cli/repl.py neow/cli/commands.py tests/test_cli.py
git commit -m "feat: add CLI entry point with REPL and command parsing"
```

---

### 任务 15：集成测试和完善

**文件：**
- 修改: `tests/test_core.py`
- 修改: `tests/test_cli.py`

- [ ] **步骤 1：编写集成测试**

在 `tests/test_core.py` 中添加：

```python
from unittest.mock import MagicMock, patch

from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.tools.file_ops import read_file, write_file


class TestIntegration:
    """Integration tests."""

    def test_conversation_with_tools(self):
        """Test conversation with tool execution."""
        # Mock model client
        mock_client = MagicMock()

        # First response: tool call
        mock_response1 = MagicMock()
        mock_response1.content = ""
        mock_response1.has_tool_calls = True
        mock_response1.tool_calls = [
            {
                "id": "call_1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"file_path": "test.txt"}'
                }
            }
        ]
        mock_response1.usage = {"total_tokens": 10}

        # Second response: final answer
        mock_response2 = MagicMock()
        mock_response2.content = "The file contains: Hello"
        mock_response2.has_tool_calls = False
        mock_response2.tool_calls = []
        mock_response2.usage = {"total_tokens": 20}

        mock_client.chat.side_effect = [mock_response1, mock_response2]

        # Create conversation manager
        conversation = ConversationManager(mock_client)

        # Get response
        response = conversation.get_response("Read test.txt")

        # Verify
        assert response.content == "The file contains: Hello"
        assert mock_client.chat.call_count == 2
```

- [ ] **步骤 2：运行所有测试**

```bash
pytest tests/ -v
```

预期输出：所有测试 `PASS`

- [ ] **步骤 3：提交集成测试**

```bash
git add tests/test_core.py
git commit -m "test: add integration tests for conversation with tools"
```

---

### 任务 16：最终验证和清理

- [ ] **步骤 1：运行完整测试套件**

```bash
pytest tests/ -v --cov=neow --cov-report=term-missing
```

预期输出：所有测试通过，覆盖率报告

- [ ] **步骤 2：代码质量检查**

```bash
black neow/ tests/
flake8 neow/ tests/
mypy neow/
```

- [ ] **步骤 3：提交代码质量修复**

```bash
git add -A
git commit -m "style: apply code formatting and fix linting issues"
```

- [ ] **步骤 4：创建 .neow.json 示例配置**

```json
{
  "default_model": "deepseek-chat",
  "models": {
    "deepseek": {
      "api_key": "your-api-key-here",
      "model": "deepseek-chat"
    }
  }
}
```

- [ ] **步骤 5：提交示例配置**

```bash
git add .neow.json.example
git commit -m "docs: add example configuration file"
```

- [ ] **步骤 6：更新 README.md**

```markdown
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
  "default_model": "deepseek-chat",
  "models": {
    "deepseek": {
      "api_key": "your-api-key-here",
      "model": "deepseek-chat"
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
```

- [ ] **步骤 7：提交 README 更新**

```bash
git add README.md
git commit -m "docs: update README with configuration and usage instructions"
```

- [ ] **步骤 8：最终提交**

```bash
git add -A
git commit -m "feat: complete Neow CLI implementation with all core features"
```

---

## 执行选项

**计划完成并保存到 `docs/superpowers/plans/2026-05-26-neow-cli-implementation.md`。两种执行方式：**

**1. Subagent-Driven (推荐)** - 我为每个任务分发一个新的子代理，任务之间进行审查，快速迭代

**2. Inline Execution** - 在当前会话中使用 executing-plans 执行任务，批量执行并设置检查点

**选择哪种方式？**
