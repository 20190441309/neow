"""Adaptive model router for Neow CLI.

Routes simpler tasks to low-cost fast models and complex tasks
to strong reasoning/planner models based on coarse-grained task classification.
"""

from enum import Enum
import re
from typing import Any, List, Optional, Tuple


class TaskComplexity(str, Enum):
    """Task complexity level."""

    SIMPLE = "simple"
    COMPLEX = "complex"


# Keywords strongly indicating architectural, refactoring, or high-complexity work
COMPLEX_KEYWORDS = {
    # English
    "architect",
    "architecture",
    "refactor",
    "redesign",
    "concurrency",
    "race condition",
    "deadlock",
    "memory leak",
    "security audit",
    "vulnerability",
    "optimize performance",
    "migration",
    "distributed",
    "end-to-end",
    "benchmark",
    # Chinese
    "架构",
    "重构",
    "并发",
    "竞态",
    "死锁",
    "内存泄漏",
    "安全漏洞",
    "性能优化",
    "迁移",
    "分布式",
    "端到端",
    "多模块",
}

# Patterns indicating simple queries or lightweight explanations
SIMPLE_PATTERNS = [
    re.compile(
        r"^(what|how|why|when|where|who)\s+(is|are|to|does|do|can)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(explain|describe|summarize|translate|format|spellcheck)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(什么是|怎么|如何|为什么|解释一下|说明一下|总结|翻译)", re.IGNORECASE
    ),
    re.compile(r"^(hello|hi|hey|thanks|thank you|你好|谢谢)", re.IGNORECASE),
]


class TaskComplexityClassifier:
    """Classifies a user prompt and its context into task complexity."""

    def __init__(self, long_prompt_threshold: int = 400):
        self.long_prompt_threshold = long_prompt_threshold

    def classify(
        self, prompt: str, context_files: Optional[List[str]] = None
    ) -> Tuple[TaskComplexity, str]:
        """Classify task complexity based on prompt content and context.

        Returns:
            Tuple of (TaskComplexity, reasoning_explanation)
        """
        text = (prompt or "").strip()
        lower_text = text.lower()
        files = context_files or []

        # 1. Multi-file context >= 3 indicates complex cross-module task
        if len(files) >= 3:
            return (
                TaskComplexity.COMPLEX,
                f"Multi-file context ({len(files)} files involved)",
            )

        # 2. Check for explicit complex keywords
        for kw in COMPLEX_KEYWORDS:
            if kw in lower_text:
                return (
                    TaskComplexity.COMPLEX,
                    f"Contains high-complexity keyword '{kw}'",
                )

        # 3. Check for multi-step structured instructions (e.g. 1. ... 2. ... 3. ...)
        step_matches = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|[-*])\s+", text)
        if len(step_matches) >= 3:
            return (
                TaskComplexity.COMPLEX,
                f"Structured multi-step task ({len(step_matches)} steps detected)",
            )

        # 4. Long prompts with substantial code or instructions
        if len(text) >= self.long_prompt_threshold:
            return (
                TaskComplexity.COMPLEX,
                f"Detailed instruction ({len(text)} characters)",
            )

        # 5. Check for simple query patterns
        for pattern in SIMPLE_PATTERNS:
            if pattern.search(text):
                return TaskComplexity.SIMPLE, "Direct question or lightweight inquiry"

        # 6. Default to simple if brief and no complex flags
        if len(text) < 150:
            return TaskComplexity.SIMPLE, "Short general request"

        return TaskComplexity.COMPLEX, "Moderate complexity request"


class ModelRouter:
    """Routes requests to the appropriate model based on task complexity."""

    def __init__(self, config: Any):
        self.config = config
        self.classifier = TaskComplexityClassifier()

    @property
    def is_auto_enabled(self) -> bool:
        """True if adaptive routing is enabled via config or model setting."""
        router_cfg = getattr(self.config, "router", {})
        if not isinstance(router_cfg, dict):
            return False
        return bool(router_cfg.get("auto_route") or router_cfg.get("enabled"))

    def get_fast_model(self) -> str:
        """Model identifier for simple/low-cost tasks."""
        router_cfg = getattr(self.config, "router", {})
        if isinstance(router_cfg, dict) and router_cfg.get("fast_model"):
            return router_cfg["fast_model"]
        return "deepseek"

    def get_strong_model(self) -> str:
        """Model identifier for complex reasoning/planner tasks."""
        router_cfg = getattr(self.config, "router", {})
        if isinstance(router_cfg, dict) and router_cfg.get("strong_model"):
            return router_cfg["strong_model"]
        return "anthropic"

    def route(
        self, prompt: str, context_files: Optional[List[str]] = None
    ) -> Tuple[str, TaskComplexity, str]:
        """Determine the model to use for the given prompt.

        Returns:
            Tuple of (model_name, complexity, reason)
        """
        complexity, reason = self.classifier.classify(prompt, context_files)
        if complexity == TaskComplexity.COMPLEX:
            model = self.get_strong_model()
        else:
            model = self.get_fast_model()
        return model, complexity, reason


__all__ = [
    "COMPLEX_KEYWORDS",
    "ModelRouter",
    "SIMPLE_PATTERNS",
    "TaskComplexity",
    "TaskComplexityClassifier",
]
