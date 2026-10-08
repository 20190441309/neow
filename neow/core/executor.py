"""Tool executor for Neow CLI."""

import inspect
from typing import Any, Callable, Dict, List, Optional

from neow.core.approval import ApprovalTier
from neow.core.tools_registry import ToolRegistry, ToolSpec
from neow.tools.builtin import builtin_specs
from neow.utils.logger import logger


class ToolError(Exception):
    """Tool execution error."""

    pass


class ToolNotFound(ToolError):
    """The model asked for a tool that is not registered."""


class ToolInvalidArguments(ToolError):
    """The arguments do not fit the tool's signature or schema."""


class ToolDenied(ToolError):
    """The user, the approval policy or the security guard refused the call."""


MAX_LISTED_TOOLS = 20


def describe_parameters(schema: Dict[str, Any]) -> str:
    """``file_path (string, required), content (string)`` for error messages."""

    required = set(schema.get("required", []))
    parts = []
    for name, prop in schema.get("properties", {}).items():
        flags = [str(prop.get("type", "any"))]
        if name in required:
            flags.append("required")
        parts.append(f"{name} ({', '.join(flags)})")
    return ", ".join(parts) or "none"


def _plural(word: str, items: List[str]) -> str:
    return f"{word}{'s' if len(items) > 1 else ''}: {', '.join(items)}"


def check_arguments(spec: ToolSpec, parameters: Any) -> None:
    """Raise :class:`ToolInvalidArguments` before a call that cannot work.

    Uses the schema's ``required`` list plus the function signature, so
    both missing and unexpected arguments are caught without running the
    tool (or asking the user to approve a doomed call).
    """

    expected = describe_parameters(spec.parameters)
    if not isinstance(parameters, dict):
        raise ToolInvalidArguments(
            f"Invalid arguments for {spec.name}: must be a JSON object. "
            f"Expected parameters: {expected}"
        )
    missing = [r for r in spec.parameters.get("required", []) if r not in parameters]
    unexpected: List[str] = []
    try:
        signature = inspect.signature(spec.func)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        kinds = {p.kind for p in signature.parameters.values()}
        if inspect.Parameter.VAR_KEYWORD not in kinds:
            unexpected = [k for k in parameters if k not in signature.parameters]
        for name, param in signature.parameters.items():
            needs_value = param.default is inspect.Parameter.empty and param.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
            if needs_value and name not in parameters and name not in missing:
                missing.append(name)
    problems = []
    if missing:
        problems.append(_plural("missing required argument", missing))
    if unexpected:
        problems.append(_plural("unexpected argument", unexpected))
    if problems:
        raise ToolInvalidArguments(
            f"Invalid arguments for {spec.name}: {'; '.join(problems)}. "
            f"Expected parameters: {expected}"
        )


def _not_implemented(name: str) -> Callable[..., str]:
    def stub(**_: Any) -> str:
        raise NotImplementedError(f"{name} not yet implemented")

    return stub


class ToolExecutor:
    """Executes tools requested by AI models.

    Tools live in :attr:`registry`. A fresh executor knows every built-in
    tool's schema but binds placeholder implementations; ``cli.main.setup_tools``
    binds the real ones.
    """

    def __init__(self):
        """Initialize tool executor."""
        self.registry = ToolRegistry(
            [spec.with_func(_not_implemented(spec.name)) for spec in builtin_specs()]
        )
        self.on_file_change: Optional[Callable[[str, str], None]] = None
        self.security_guard: Optional[Any] = None
        self.allowed_commands: List[str] = []
        self.approval_policy: Optional[Any] = None  # ApprovalPolicy
        self.approval_callback: Optional[Callable[[str, Dict[str, Any], str], bool]] = None

    @property
    def tools(self) -> Dict[str, Callable]:
        """Tool name -> implementation (read-only view)."""
        return {spec.name: spec.func for spec in self.registry}

    def register_spec(self, spec: ToolSpec) -> None:
        """Register a fully described tool."""
        self.registry.register(spec)
        logger.debug(f"Registered tool: {spec.name} ({spec.source})")

    def register_tool(
        self,
        name: str,
        func: Callable,
        *,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        tier: Optional[ApprovalTier] = None,
        read_only: bool = False,
        mutates_files: bool = False,
        source: str = "builtin",
    ) -> None:
        """Register a tool.

        With only ``name`` and ``func``, a known tool keeps its schema and
        policy and just gets a new implementation; an unknown tool gets a
        schema inferred from the function signature.

        Args:
            name: Tool name.
            func: Tool function.
        """
        described = description or parameters or tier is not None
        if name in self.registry and not described:
            self.registry.bind(name, func)
            logger.debug(f"Bound tool: {name}")
            return
        self.register_spec(
            ToolSpec.from_function(
                name,
                func,
                description=description,
                parameters=parameters,
                tier=tier or ApprovalTier.EXEC,
                read_only=read_only,
                mutates_files=mutates_files,
                source=source,
            )
        )

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
        spec = self.registry.get(tool_name)
        if spec is None:
            names = self.registry.names()
            listed = ", ".join(names[:MAX_LISTED_TOOLS])
            if len(names) > MAX_LISTED_TOOLS:
                listed += ", …"
            raise ToolNotFound(
                f"Tool '{tool_name}' not found. Available tools: {listed}"
            )
        check_arguments(spec, parameters)

        # Security checks
        if self.security_guard:
            if tool_name == "execute_command":
                check = self.security_guard.check_command(
                    parameters.get("command", ""), self.allowed_commands
                )
                if not check.allowed:
                    raise ToolDenied(f"Security: {check.reason}")
            elif spec.mutates_files:
                operation = tool_name.removesuffix("_file")
                check = self.security_guard.check_file_access(
                    parameters.get("file_path", ""), operation
                )
                if not check.allowed:
                    raise ToolDenied(f"Security: {check.reason}")

        # Approval gate
        if self.approval_policy:
            is_dangerous = False
            if self.security_guard and tool_name == "execute_command":
                is_dangerous = self.security_guard.is_dangerous(parameters.get("command", ""))
            approval = self.approval_policy.check_approval(
                tool_name, parameters, is_dangerous=is_dangerous, tier=spec.tier,
            )
            if approval.needs_approval:
                if self.approval_callback:
                    approved = self.approval_callback(tool_name, parameters, approval.reason)
                    if not approved:
                        raise ToolDenied(f"User denied: {tool_name}")
                else:
                    # No callback available (non-interactive or misconfigured) -- deny
                    raise ToolDenied(
                        f"Approval required but no callback: {approval.reason}"
                    )

        try:
            result = spec.func(**parameters)
            logger.debug(f"Tool '{tool_name}' executed successfully")

            # Fire callback for file-mutating tools
            if spec.mutates_files and self.on_file_change:
                file_path = parameters.get("file_path", "")
                if file_path:
                    try:
                        self.on_file_change(tool_name, file_path)
                    except Exception as e:
                        logger.warning(f"File change callback failed: {e}")

            return str(result)
        except Exception as e:
            logger.debug(f"Tool '{tool_name}' execution failed: {e}")
            raise ToolError(f"Tool execution failed: {e}")

    def get_tool_definitions(self) -> list:
        """Get tool definitions for AI models (every registered tool).

        Returns:
            List of tool definitions.
        """
        return self.registry.definitions()
