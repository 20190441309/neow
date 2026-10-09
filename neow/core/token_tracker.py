"""Token usage tracking and cost calculation for Neow CLI."""

from typing import Any, Dict

from neow.utils.logger import logger

# Cache prices relative to the input price when a model sets none
# (Anthropic: reads 0.1x, 5-minute writes 1.25x).
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


class TokenTracker:
    """Tracks token usage across a session and calculates costs."""

    def __init__(self, config: Any):
        """Initialize token tracker.

        Args:
            config: Config instance with token prices.
        """
        self.config = config
        self.session_input: int = 0
        self.session_output: int = 0
        self.session_cache_read: int = 0
        self.session_cache_write: int = 0
        self._model_usage: Dict[str, Dict[str, int]] = {}

    def record(self, usage: Dict[str, int], model: str) -> None:
        """Record token usage from a single API response.

        Args:
            usage: Dict with 'prompt_tokens' and 'completion_tokens', plus
                optional 'cache_read_tokens' / 'cache_write_tokens' (both
                already counted inside 'prompt_tokens').
            model: Model name for cost calculation.
        """
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        cache_read = usage.get("cache_read_tokens", 0) or 0
        cache_write = usage.get("cache_write_tokens", 0) or 0
        self.session_input += input_tokens
        self.session_output += output_tokens
        self.session_cache_read += cache_read
        self.session_cache_write += cache_write

        counts = self._model_usage.setdefault(
            model, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        )
        counts["input"] += input_tokens
        counts["output"] += output_tokens
        counts["cache_read"] = counts.get("cache_read", 0) + cache_read
        counts["cache_write"] = counts.get("cache_write", 0) + cache_write

        logger.debug(
            f"Token usage: {input_tokens} in ({cache_read} cached) / "
            f"{output_tokens} out ({model})"
        )

    def _cost(self, model: str) -> float:
        prices = self.config.token.get("prices", {}).get(model, {})
        if not prices:
            return 0.0
        usage = self._model_usage.get(model, {})
        read = usage.get("cache_read", 0)
        write = usage.get("cache_write", 0)
        uncached = max(usage.get("input", 0) - read - write, 0)
        input_price = prices.get("input", 0)
        read_price = prices.get("cache_read", input_price * CACHE_READ_FACTOR)
        write_price = prices.get("cache_write", input_price * CACHE_WRITE_FACTOR)
        return (
            uncached * input_price
            + read * read_price
            + write * write_price
            + usage.get("output", 0) * prices.get("output", 0)
        ) / 1_000_000

    def get_session_cost(self) -> float:
        """Calculate total session cost in USD using per-model token counts.

        Cached input is priced with the model's ``cache_read`` /
        ``cache_write`` prices, or 0.1x / 1.25x its input price.

        Returns:
            Cost in dollars.
        """
        return sum(self._cost(model) for model in self._model_usage)

    def get_cost_for_model(self, model: str) -> float:
        """Calculate cost for a specific model using its per-model token counts.

        Args:
            model: Model name.

        Returns:
            Cost in dollars.
        """
        return self._cost(model)

    def format_usage_line(self, usage: Dict[str, int], model: str) -> str:
        """Format a single response's usage as a display line.

        Args:
            usage: Dict with 'prompt_tokens' and 'completion_tokens'.
            model: Model name.

        Returns:
            Formatted string like "(tokens: 1234 in / 567 out | $0.00)"
        """
        input_t = usage.get("prompt_tokens", 0) or 0
        output_t = usage.get("completion_tokens", 0) or 0
        cost = self.get_cost_for_model(model)
        return f"(tokens: {input_t:,} in / {output_t:,} out | ${cost:.4f})"

    def get_session_summary(self) -> str:
        """Return formatted session usage summary.

        Returns:
            Multi-line summary string.
        """
        total = self.session_input + self.session_output
        cost = self.get_session_cost()
        lines = [
            "Session token usage:",
            f"  Input:  {self.session_input:,} tokens",
            f"  Output: {self.session_output:,} tokens",
            f"  Total:  {total:,} tokens",
            f"  Cost:   ${cost:.4f}",
        ]
        if self.session_cache_read or self.session_cache_write:
            hit_rate = (
                self.session_cache_read / self.session_input
                if self.session_input
                else 0.0
            )
            lines.insert(
                2,
                f"  Cache:  {self.session_cache_read:,} read / "
                f"{self.session_cache_write:,} written ({hit_rate:.0%} of input)",
            )
        if len(self._model_usage) > 1:
            lines.append("  Per-model breakdown:")
            for model, mu in self._model_usage.items():
                model_total = mu["input"] + mu["output"]
                model_cost = self.get_cost_for_model(model)
                lines.append(f"    {model}: {model_total:,} tokens (${model_cost:.4f})")
        return "\n".join(lines)

    def check_warn_threshold(self) -> str:
        """Check if session usage exceeds warning threshold.

        Returns:
            Warning message if exceeded, empty string otherwise.
        """
        warn_at = self.config.token.get("warn_at_tokens", 0)
        if warn_at and (self.session_input + self.session_output) > warn_at:
            return f"Token usage ({self.session_input + self.session_output:,}) exceeds warning threshold ({warn_at:,})"
        return ""

    def check_max_tokens(self) -> bool:
        """Check if session usage exceeds hard token limit.

        Returns:
            True if exceeded, False otherwise.
        """
        max_tokens = self.config.token.get("max_tokens", 0)
        if max_tokens and (self.session_input + self.session_output) >= max_tokens:
            return True
        return False