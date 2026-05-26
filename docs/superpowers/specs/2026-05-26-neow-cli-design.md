# Neow CLI 设计文档

## 1. 项目概述

### 1.1 项目名称
Neow

### 1.2 项目目标
创建一个轻量级、通用的 AI CLI 助手，支持多种任务（代码编辑、文档处理、数据分析等），保持快速响应和良好的用户体验。

### 1.3 核心特性
- 支持多种 AI 模型（DeepSeek、Anthropic Claude、OpenAI GPT）
- 交互式 REPL 界面
- 代码编辑、命令执行、代码库理解、对话记忆等核心功能
- 轻量级设计，快速启动和响应

## 2. 技术选型

### 2.1 编程语言
Python 3.10+

### 2.2 核心依赖
- `anthropic>=0.39.0` - Anthropic Claude SDK
- `openai>=1.0.0` - OpenAI SDK
- `rich>=13.0.0` - 终端格式化
- `click>=8.0.0` - CLI 框架
- `prompt-toolkit>=3.0.0` - REPL 交互
- `pyyaml>=6.0` - 配置文件解析

### 2.3 AI 模型支持
- DeepSeek（首选）
- Anthropic Claude
- OpenAI GPT

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────┐
│           CLI 入口层 (cli/)             │
│  - 命令行参数解析                        │
│  - REPL 交互循环                        │
│  - 用户输入处理                         │
├─────────────────────────────────────────┤
│           核心引擎层 (core/)            │
│  - 对话管理器 (ConversationManager)     │
│  - 工具执行器 (ToolExecutor)            │
│  - 上下文管理器 (ContextManager)        │
├─────────────────────────────────────────┤
│           工具层 (tools/)               │
│  - 文件操作 (read, write, edit)         │
│  - 命令执行 (bash)                      │
│  - 代码搜索 (grep, glob)               │
├─────────────────────────────────────────┤
│           AI 模型层 (models/)           │
│  - Anthropic Claude SDK                 │
│  - OpenAI SDK                           │
│  - DeepSeek API                         │
└─────────────────────────────────────────┘
```

### 3.2 核心组件

#### 3.2.1 对话管理器 (ConversationManager)

负责管理多轮对话和上下文：

```python
class ConversationManager:
    def __init__(self, model_client):
        self.messages = []  # 对话历史
        self.system_prompt = ""  # 系统提示
        self.model_client = model_client  # AI 模型客户端
    
    def add_message(self, role, content):
        """添加消息到对话历史"""
        
    def get_response(self, user_input):
        """获取 AI 响应，支持工具调用"""
        
    def clear_history(self):
        """清空对话历史"""
```

#### 3.2.2 工具执行器 (ToolExecutor)

负责执行 AI 请求的工具调用：

```python
class ToolExecutor:
    def __init__(self):
        self.tools = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "execute_command": self.execute_command,
            "search_code": self.search_code,
        }
    
    def execute(self, tool_name, parameters):
        """执行指定工具"""
        
    def read_file(self, file_path):
        """读取文件内容"""
        
    def write_file(self, file_path, content):
        """写入文件内容"""
```

#### 3.2.3 上下文管理器 (ContextManager)

负责理解代码库结构：

```python
class ContextManager:
    def __init__(self, project_root):
        self.project_root = project_root
        self.file_cache = {}  # 文件内容缓存
        
    def get_project_structure(self):
        """获取项目目录结构"""
        
    def get_relevant_files(self, query):
        """根据查询获取相关文件"""
        
    def build_context(self, user_input):
        """为 AI 构建上下文信息"""
```

## 4. 数据流设计

### 4.1 用户输入处理流程

```
用户输入 → CLI 解析 → 上下文构建 → AI 模型调用 → 工具执行 → 结果返回 → 显示输出
```

详细流程：

1. **用户输入**：用户在 REPL 中输入自然语言指令
2. **CLI 解析**：解析输入，识别特殊命令（如 /clear, /exit）
3. **上下文构建**：ContextManager 分析项目结构，构建相关上下文
4. **AI 模型调用**：将用户输入 + 上下文发送给 AI 模型
5. **工具执行**：如果 AI 返回工具调用，ToolExecutor 执行相应操作
6. **结果返回**：将工具执行结果返回给 AI 模型，获取最终响应
7. **显示输出**：格式化并显示 AI 的响应

### 4.2 工具调用流程

```
AI 响应 (包含 tool_use) 
    ↓
解析工具调用参数
    ↓
ToolExecutor 执行工具
    ↓
返回工具执行结果
    ↓
AI 继续处理 (可能再次调用工具)
    ↓
最终响应
```

## 5. 项目结构

```
neow/
├── README.md
├── pyproject.toml
├── requirements.txt
├── LICENSE
├── neow/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py          # CLI 入口
│   │   ├── repl.py          # REPL 交互循环
│   │   └── commands.py      # 特殊命令处理
│   ├── core/
│   │   ├── __init__.py
│   │   ├── conversation.py  # 对话管理器
│   │   ├── executor.py      # 工具执行器
│   │   ├── context.py       # 上下文管理器
│   │   └── config.py        # 配置管理
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── file_ops.py      # 文件操作工具
│   │   ├── command.py       # 命令执行工具
│   │   └── search.py        # 代码搜索工具
│   ├── models/
│   │   ├── __init__.py
│   │   ├── anthropic.py     # Anthropic Claude 客户端
│   │   ├── openai.py        # OpenAI 客户端
│   │   └── deepseek.py      # DeepSeek 客户端
│   └── utils/
│       ├── __init__.py
│       ├── logger.py        # 日志工具
│       └── formatter.py     # 输出格式化
└── tests/
    ├── __init__.py
    ├── test_cli.py
    ├── test_core.py
    ├── test_tools.py
    └── test_models.py
```

## 6. 配置管理

### 6.1 配置优先级

1. **命令行参数**：最高优先级
2. **环境变量**：API 密钥等敏感信息
3. **配置文件**：`~/.neow/config.json` 或项目级 `.neow.json`

### 6.2 配置示例

```json
{
  "default_model": "deepseek-chat",
  "models": {
    "anthropic": {
      "api_key": "sk-ant-...",
      "model": "claude-sonnet-4-6"
    },
    "openai": {
      "api_key": "sk-...",
      "model": "gpt-4o"
    },
    "deepseek": {
      "api_key": "sk-...",
      "model": "deepseek-chat"
    }
  },
  "tools": {
    "enabled": ["read_file", "write_file", "edit_file", "execute_command", "search_code"],
    "allowed_commands": ["ls", "cat", "grep", "find", "python", "npm"]
  }
}
```

## 7. 错误处理策略

### 7.1 错误分类

```python
class NeowError(Exception):
    """基础异常类"""
    pass

class APIError(NeowError):
    """AI 模型 API 调用错误"""
    pass

class ToolError(NeowError):
    """工具执行错误"""
    pass

class ConfigError(NeowError):
    """配置错误"""
    pass

class FileError(NeowError):
    """文件操作错误"""
    pass
```

### 7.2 错误处理原则

1. **优雅降级**：API 调用失败时，提供重试机制或友好提示
2. **安全第一**：文件操作前确认，危险命令需要用户确认
3. **详细日志**：记录错误堆栈，便于调试
4. **用户友好**：错误信息清晰易懂，不暴露技术细节

## 8. 测试策略

### 8.1 测试层次

1. **单元测试**：测试单个函数和类
2. **集成测试**：测试组件间的交互
3. **端到端测试**：测试完整的用户场景

### 8.2 Mock 策略

- **AI 模型调用**：使用 mock 对象，避免真实 API 调用
- **文件系统**：使用临时目录，测试后自动清理
- **命令执行**：使用 mock，避免执行危险命令

## 9. 开发路线图

### 阶段 1：基础框架（第 1-2 周）

- [ ] 项目结构搭建
- [ ] CLI 入口和 REPL 交互
- [ ] 基础配置管理
- [ ] 单个 AI 模型集成（DeepSeek）

### 阶段 2：核心功能（第 3-4 周）

- [ ] 文件操作工具（read, write, edit）
- [ ] 命令执行工具
- [ ] 对话管理器
- [ ] 工具执行器

### 阶段 3：高级功能（第 5-6 周）

- [ ] 多模型支持（Anthropic Claude, OpenAI）
- [ ] 代码库理解（ContextManager）
- [ ] 代码搜索工具
- [ ] 上下文管理优化

### 阶段 4：完善和优化（第 7-8 周）

- [ ] 错误处理完善
- [ ] 性能优化
- [ ] 测试覆盖
- [ ] 文档编写

## 10. 附录

### 10.1 参考项目

- [Aider](https://github.com/Aider-AI/aider) - AI Pair Programming in Your Terminal
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) - Anthropic 官方 CLI 工具

### 10.2 相关技术文档

- [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Rich 文档](https://rich.readthedocs.io/)
- [Click 文档](https://click.palletsprojects.com/)
