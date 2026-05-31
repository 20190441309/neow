"""Approval mode for Neow CLI -- controls which tool executions require user confirmation."""

from enum import Enum
from typing import Any, Dict, List, Optional

from neow.utils.logger import logger


class ApprovalMode(str, Enum):
    """Approval mode levels.

    - ALWAYS_ASK: Every tool call requires confirmation.
    - WRITE: Only write/exec operations require confirmation.
    - YOLO: All operations proceed automatically (dangerous patterns still prompt).
    """
    ALWAYS_ASK = "always-ask"
    WRITE = "write"
    YOLO = "yolo"


class ApprovalTier(str, Enum):
    """Approval tier for a tool -- determines its sensitivity level.

    - READ: Read-only operations (no side effects).
    - WRITE: File-mutating operations (create, edit, delete).
    - EXEC: Shell command execution.
    """
    READ = "read"
    WRITE = "write"
    EXEC = "exec"


# Default tier assignment per tool name.
TOOL_TIERS: Dict[str, ApprovalTier] = {
    "read_file": ApprovalTier.READ,
    "search_code": ApprovalTier.READ,
    "git_status": ApprovalTier.READ,
    "git_diff": ApprovalTier.READ,
    "git_log": ApprovalTier.READ,
    "write_file": ApprovalTier.WRITE,
    "edit_file": ApprovalTier.WRITE,
    "create_file": ApprovalTier.WRITE,
    "delete_file": ApprovalTier.WRITE,
    "git_commit": ApprovalTier.WRITE,
    "execute_command": ApprovalTier.EXEC,
}


class ApprovalCheck:
    """Result of an approval check."""

    __slots__ = ("needs_approval", "reason", "tool_name", "tier")

    def __init__(self, needs_approval: bool, reason: str,
                 tool_name: str = "", tier: Optional[ApprovalTier] = None):
        self.needs_approval = needs_approval
        self.reason = reason
        self.tool_name = tool_name
        self.tier = tier

    def __bool__(self) -> bool:
        return self.needs_approval

    def __repr__(self) -> str:
        return f"ApprovalCheck(needs_approval={self.needs_approval}, tool={self.tool_name!r})"


class ApprovalPolicy:
    """Determines whether a tool execution requires user approval.

    Combines the current mode, per-tool overrides, and forced-dangerous
    detection to decide if the user must confirm before a tool runs.
    """

    def __init__(
        self,
        mode: ApprovalMode = ApprovalMode.WRITE,
        tool_overrides: Optional[Dict[str, str]] = None,
        dangerous_tools: Optional[List[str]] = None,
    ):
        """Initialize approval policy.

        Args:
            mode: Current approval mode.
            tool_overrides: Per-tool override policy.
                Keys are tool names, values are "allow" | "deny" | "prompt".
            dangerous_tools: Tool names that always require prompt
                regardless of mode (e.g. tools that can run rm -rf).
        """
        self.mode = mode
        self.tool_overrides: Dict[str, str] = tool_overrides or {}
        self.dangerous_tools: List[str] = dangerous_tools or ["execute_command"]

    def check_approval(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
        is_dangerous: bool = False,
    ) -> ApprovalCheck:
        """Check whether a tool call requires user approval.

        Args:
            tool_name: Name of the tool about to execute.
            parameters: Tool parameters (used for display in the reason).
            is_dangerous: Whether the SecurityGuard flagged this call
                as dangerous (e.g. rm -rf).  If True, *always* prompt.

        Returns:
            ApprovalCheck indicating whether the user must confirm.
        """
        tier = TOOL_TIERS.get(tool_name, ApprovalTier.EXEC)

        # 1. Forced-dangerous always prompts, regardless of mode.
        if is_dangerous:
            return ApprovalCheck(
                needs_approval=True,
                reason=f"Dangerous operation detected: {tool_name}",
                tool_name=tool_name,
                tier=tier,
            )

        # 2. Per-tool override takes precedence over mode.
        override = self.tool_overrides.get(tool_name)
        if override == "allow":
            return ApprovalCheck(
                needs_approval=False, reason="", tool_name=tool_name, tier=tier,
            )
        if override == "deny":
            return ApprovalCheck(
                needs_approval=True,
                reason=f"Tool '{tool_name}' is denied by policy",
                tool_name=tool_name,
                tier=tier,
            )
        if override == "prompt":
            return ApprovalCheck(
                needs_approval=True,
                reason=f"Tool '{tool_name}' requires confirmation (policy override)",
                tool_name=tool_name,
                tier=tier,
            )

        # 3. Mode-based decision.
        if self.mode == ApprovalMode.YOLO:
            return ApprovalCheck(
                needs_approval=False, reason="", tool_name=tool_name, tier=tier,
            )

        if self.mode == ApprovalMode.WRITE:
            # Only write/exec tiers need approval.
            if tier in (ApprovalTier.WRITE, ApprovalTier.EXEC):
                return ApprovalCheck(
                    needs_approval=True,
                    reason=f"{tier.value} operation requires approval: {tool_name}",
                    tool_name=tool_name,
                    tier=tier,
                )
            return ApprovalCheck(
                needs_approval=False, reason="", tool_name=tool_name, tier=tier,
            )

        # ALWAYS_ASK: everything needs approval.
        return ApprovalCheck(
            needs_approval=True,
            reason=f"Approval required (always-ask mode): {tool_name}",
            tool_name=tool_name,
            tier=tier,
        )

    def set_mode(self, mode: ApprovalMode) -> None:
        """Switch the approval mode at runtime."""
        self.mode = mode
        logger.info(f"Approval mode set to: {mode.value}")

    def set_tool_override(self, tool_name: str, policy: str) -> None:
        """Set a per-tool override policy.

        Args:
            tool_name: Tool name.
            policy: One of "allow", "deny", "prompt".
        """
        if policy not in ("allow", "deny", "prompt"):
            raise ValueError(f"Invalid override policy: {policy!r}. Use allow/deny/prompt.")
        self.tool_overrides[tool_name] = policy
        logger.info(f"Tool override: {tool_name}={policy}")
