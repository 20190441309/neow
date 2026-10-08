"""Tool registry: one place that knows each tool's schema, function and policy."""

import inspect
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterator, List, Optional

from neow.core.approval import ApprovalTier

_JSON_TYPES = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass(frozen=True)
class ToolSpec:
    """Everything the agent needs to know about one tool."""

    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable[..., Any]
    tier: ApprovalTier = ApprovalTier.EXEC
    read_only: bool = False
    mutates_files: bool = False
    source: str = "builtin"

    def definition(self) -> Dict[str, Any]:
        """OpenAI-style function definition sent to the model."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def with_func(self, func: Callable[..., Any]) -> "ToolSpec":
        return replace(self, func=func)

    @classmethod
    def from_function(
        cls,
        name: str,
        func: Callable[..., Any],
        *,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        tier: ApprovalTier = ApprovalTier.EXEC,
        read_only: bool = False,
        mutates_files: bool = False,
        source: str = "builtin",
    ) -> "ToolSpec":
        """Build a spec, inferring the schema from the signature when omitted."""

        doc = inspect.getdoc(func) or ""
        return cls(
            name=name,
            description=description or (doc.splitlines()[0] if doc else name),
            parameters=parameters or infer_parameters(func),
            func=func,
            tier=ApprovalTier(tier),
            read_only=read_only,
            mutates_files=mutates_files,
            source=source,
        )


def infer_parameters(func: Callable[..., Any]) -> Dict[str, Any]:
    """JSON Schema for *func*'s keyword parameters (annotations → types)."""

    properties: Dict[str, Any] = {}
    required: List[str] = []
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return {"type": "object", "properties": {}}
    for param in signature.parameters.values():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        annotation = param.annotation
        json_type = _JSON_TYPES.get(annotation, "string")
        properties[param.name] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


class ToolRegistry:
    """Ordered collection of :class:`ToolSpec` keyed by tool name."""

    def __init__(self, specs: Optional[List[ToolSpec]] = None):
        self._specs: Dict[str, ToolSpec] = {}
        for spec in specs or []:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        """Add or replace a tool (re-registering keeps its position)."""

        self._specs[spec.name] = spec

    def bind(self, name: str, func: Callable[..., Any]) -> ToolSpec:
        """Swap the implementation of an existing tool, keeping its metadata."""

        spec = self._specs[name].with_func(func)
        self._specs[name] = spec
        return spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def names(self) -> List[str]:
        return list(self._specs)

    def definitions(
        self,
        *,
        names: Optional[List[str]] = None,
        read_only: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Model-facing definitions, optionally filtered."""

        return [
            spec.definition()
            for spec in self._specs.values()
            if (names is None or spec.name in names)
            and (read_only is None or spec.read_only == read_only)
        ]

    def subset(self, predicate: Callable[[ToolSpec], bool]) -> "ToolRegistry":
        return ToolRegistry([spec for spec in self._specs.values() if predicate(spec)])

    def copy(self) -> "ToolRegistry":
        return ToolRegistry(list(self._specs.values()))

    def __contains__(self, name: object) -> bool:
        return name in self._specs

    def __iter__(self) -> Iterator[ToolSpec]:
        return iter(list(self._specs.values()))

    def __len__(self) -> int:
        return len(self._specs)


__all__ = ["ToolSpec", "ToolRegistry", "infer_parameters"]
