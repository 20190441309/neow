"""On-demand Skills loader (.neow/skills/<name>/SKILL.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Skill:
    """Metadata and path for a discoverable skill."""

    name: str
    description: str
    path: Path
    scope: str  # "workspace" or "user"


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_skill_file(skill_md: Path, scope: str) -> Optional[Skill]:
    """Parse YAML frontmatter (or fallback heading) from a SKILL.md file."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    name = skill_md.parent.name
    description = ""

    match = _FRONTMATTER_RE.match(text)
    if match:
        block = match.group(1)
        for line in block.splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            key = k.strip().lower()
            val = v.strip().strip("\"'")
            if key == "name" and val:
                name = val
            elif key == "description" and val:
                description = val

    if not description:
        # Fallback: first non-empty non-heading paragraph line
        body = text[match.end() :] if match else text
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:140]
                break
        if not description:
            description = f"Skill {name}"

    return Skill(name=name, description=description, path=skill_md, scope=scope)


def discover_skills(workspace_root: Optional[Path | str] = None) -> List[Skill]:
    """Discover all skills in workspace (.neow/skills) and user home (~/.neow/skills).

    Workspace skills override user skills with the same name.
    """
    root = Path(workspace_root) if workspace_root else Path.cwd()
    found: Dict[str, Skill] = {}

    user_dir = Path.home() / ".neow" / "skills"
    if user_dir.is_dir():
        for skill_md in sorted(user_dir.glob("*/SKILL.md")):
            skill = _parse_skill_file(skill_md, scope="user")
            if skill:
                found[skill.name] = skill

    ws_dir = root / ".neow" / "skills"
    if ws_dir.is_dir():
        for skill_md in sorted(ws_dir.glob("*/SKILL.md")):
            skill = _parse_skill_file(skill_md, scope="workspace")
            if skill:
                found[skill.name] = skill

    return sorted(found.values(), key=lambda s: s.name)


def load_skill_content(name: str, workspace_root: Optional[Path | str] = None) -> str:
    """Load the full markdown instructions of a skill by name."""
    skills = discover_skills(workspace_root)
    target = (name or "").strip().lower()
    for skill in skills:
        if skill.name.lower() == target:
            try:
                content = skill.path.read_text(encoding="utf-8", errors="replace")
                return (
                    f"# Skill: {skill.name} ({skill.scope})\n"
                    f"Path: {skill.path}\n\n{content}"
                )
            except OSError as e:
                return f"Error reading skill '{name}': {e}"
    available = ", ".join(s.name for s in skills) or "none"
    return f"Error: skill '{name}' not found. Available skills: {available}"


def format_skills_index(skills: List[Skill]) -> str:
    """Format a compact index of available skills for the system prompt."""
    if not skills:
        return ""
    lines = ["\n\n# Available Skills (call `load_skill` to read full instructions):"]
    for s in skills:
        lines.append(f"- {s.name} ({s.scope}): {s.description}")
    return "\n".join(lines)
