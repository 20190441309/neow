"""Token usage tracking and cost calculation for Neow CLI."""

from typing import Any, Dict

from neow.utils.logger import logger


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
        self._model_usage: Dict[str, Dict[str, int]] = {}

    def record(self, usage: Dict[str, int], model: str) -> None:
        """Record token usage from a single API response.

        Args:
            usage: Dict with 'prompt_tokens' and 'completion_tokens'.
            model: Model name for cost calculation.
        """
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        self.session_input += input_tokens
        self.session_output += output_tokens

        if model not in self._model_usage:
            self._model_usage[model] = {"input": 0, "output": 0}
        self._model_usage[model]["input"] += input_tokens
        self._model_usage[model]["output"] += output_tokens

        logger.debug(f"Token usage: {input_tokens} in / {output_tokens} out ({model})")

    def get_session_cost(self) -> float:
        """Calculate total session cost in USD using per-model token counts.

        Returns:
            Cost in dollars.
        """
        prices = self.config.token.get("prices", {})
        total = 0.0
        for model_name, model_usage in self._model_usage.items():
            model_prices = prices.get(model_name, {})
            input_cost = (model_usage["input"] / 1_000_000) * model_prices.get("input", 0)
            output_cost = (model_usage["output"] / 1_000_000) * model_prices.get("output", 0)
            total += input_cost + output_cost
        return total

    def get_cost_for_model(self, model: str) -> float:
        """Calculate cost for a specific model using its per-model token counts.

        Args:
            model: Model name.

        Returns:
            Cost in dollars.
        """
        prices = self.config.token.get("prices", {})
        model_prices = prices.get(model, {})
        if not model_prices:
            return 0.0
        usage = self._model_usage.get(model, {"input": 0, "output": 0})
        input_cost = (usage["input"] / 1_000_000) * model_prices.get("input", 0)
        output_cost = (usage["output"] / 1_000_000) * model_prices.get("output", 0)
        return input_cost + output_cost

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