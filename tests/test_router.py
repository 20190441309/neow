"""Tests for adaptive model routing based on task complexity (task 22.1)."""

from unittest.mock import MagicMock, patch

from neow.core.config import Config
from neow.core.router import (
    ModelRouter,
    TaskComplexity,
    TaskComplexityClassifier,
)


def test_simple_prompt_classification():
    classifier = TaskComplexityClassifier()

    simple_prompts = [
        "what is a decorator in Python?",
        "how to read a file in rust",
        "explain the difference between process and thread",
        "hello there",
        "什么是上下文管理器？",
        "怎么用 pytest 运行指定测试？",
        "解释一下 hashline edit 的原理",
        "fix typo in docstring",
    ]
    for prompt in simple_prompts:
        complexity, reason = classifier.classify(prompt)
        assert (
            complexity == TaskComplexity.SIMPLE
        ), f"Expected SIMPLE for: {prompt} (reason: {reason})"


def test_complex_prompt_classification():
    classifier = TaskComplexityClassifier()

    complex_prompts = [
        "Please refactor the authentication module to support OAuth2 tokens.",
        "Design the system architecture for high-concurrency order processing.",
        "We are seeing a race condition and possible deadlock between threads.",
        "对整个项目进行架构重构，支持分布式调度",
        "分析此处的内存泄漏和并发竞态问题",
    ]
    for prompt in complex_prompts:
        complexity, reason = classifier.classify(prompt)
        assert (
            complexity == TaskComplexity.COMPLEX
        ), f"Expected COMPLEX for: {prompt} (reason: {reason})"


def test_multi_step_and_long_prompts_are_complex():
    classifier = TaskComplexityClassifier(long_prompt_threshold=200)

    # 3+ numbered steps
    step_prompt = "Do the following:\n1. Update setup.py\n2. Rewrite tests\n3. Deploy"
    complexity, reason = classifier.classify(step_prompt)
    assert complexity == TaskComplexity.COMPLEX
    assert "steps" in reason

    # Long detailed prompt
    long_prompt = "x" * 250
    complexity, reason = classifier.classify(long_prompt)
    assert complexity == TaskComplexity.COMPLEX
    assert "Detailed instruction" in reason


def test_multi_file_context_escalates_to_complex():
    classifier = TaskComplexityClassifier()

    # Even a brief prompt becomes COMPLEX when >= 3 files are in context
    complexity, reason = classifier.classify(
        "update imports",
        context_files=["a.py", "b.py", "c.py"],
    )
    assert complexity == TaskComplexity.COMPLEX
    assert "Multi-file context" in reason


def test_model_router_selection():
    config = MagicMock()
    config.router = {
        "enabled": True,
        "auto_route": True,
        "fast_model": "deepseek",
        "strong_model": "anthropic",
    }
    router = ModelRouter(config)
    assert router.is_auto_enabled is True

    # Simple task -> fast model
    model, complexity, _ = router.route("what is python?")
    assert complexity == TaskComplexity.SIMPLE
    assert model == "deepseek"

    # Complex task -> strong model
    model, complexity, _ = router.route("refactor database connection pool")
    assert complexity == TaskComplexity.COMPLEX
    assert model == "anthropic"


def test_router_disabled_by_default():
    config = Config()
    router = ModelRouter(config)
    assert router.is_auto_enabled is False


def test_router_repl_auto_switch():
    from neow.cli.commands import Command, ParsedCommand
    from neow.cli.repl import REPL

    mock_conv = MagicMock()
    repl = REPL(conversation=mock_conv, config=Config())
    repl.token_tracker = MagicMock()

    # Switch to auto
    repl._handle_command(ParsedCommand(Command.MODEL, "auto"))
    assert repl.config.router["auto_route"] is True

    # Test _maybe_auto_route
    repl.conversation.context_files = {}
    client_mock = MagicMock()
    client_mock.config_name = "anthropic"
    repl.conversation.model_client = client_mock

    new_mock = MagicMock()
    new_mock.config_name = "deepseek"
    with patch("neow.cli.main.create_model_client", return_value=new_mock):
        repl._maybe_auto_route("what is GIL?")

    assert repl.conversation.model_client == new_mock
