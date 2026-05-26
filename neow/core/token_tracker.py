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
        logger.debug(f"Token usage: {input_tokens} in / {output_tokens} out ({model})")

    def get_session_cost(self) -> float:
        """Calculate total session cost in USD.

        Returns:
            Cost in dollars.
        """
        prices = self.config.token.get("prices", {})
        total = 0.0
        for model_name, model_prices in prices.items():
            input_cost = (self.session_input / 1_000_000) * model_prices.get("input", 0)
            output_cost = (self.session_output / 1_000_000) * model_prices.get("output", 0)
            total += input_cost + output_cost
        return total

    def get_cost_for_model(self, model: str) -> float:
        """Calculate cost using a specific model's prices.

        Args:
            model: Model name.

        Returns:
            Cost in dollars.
        """
        prices = self.config.token.get("prices", {})
        model_prices = prices.get(model, {})
        if not model_prices:
            return 0.0
        input_cost = (self.session_input / 1_000_000) * model_prices.get("input", 0)
        output_cost = (self.session_output / 1_000_000) * model_prices.get("output", 0)
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
        prices = self.config.token.get("prices", {})
        model_prices = prices.get(model, {})
        cost = 0.0
        if model_prices:
            cost = (input_t / 1_000_000) * model_prices.get("input", 0) + \
                   (output_t / 1_000_000) * model_prices.get("output", 0)
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
