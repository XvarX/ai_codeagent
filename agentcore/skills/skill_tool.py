"""Skill tool — lets LLM invoke skills by name."""

from agentcore.tools.base import Tool, ToolContext
from agentcore.skills.loader import SkillDef


class SkillTool(Tool):
    """Invoke a skill by name, returning its SKILL.md content.

    Mirrors src/tools/SkillTool/SkillTool.ts (inline mode).
    """

    def __init__(self, skills: list[SkillDef]):
        self.name = "Skill"
        self.description = (
            "Execute a skill within the main conversation. "
            "Use when the user references a slash command (/name) or "
            "a skill matches the user's request."
        )
        self.parameters = {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "The skill name, e.g. 'pdf' or 'commit'",
                },
                "args": {
                    "type": "string",
                    "description": "Optional arguments for the skill",
                },
            },
            "required": ["skill"],
        }
        self._skills: dict[str, SkillDef] = {s.name: s for s in skills}

    def is_read_only(self) -> bool:
        return True

    async def call(self, input: dict, context: ToolContext) -> str:
        skill_name = input.get("skill", "")
        args = input.get("args", "")

        sd = self._skills.get(skill_name)
        if not sd:
            available = ", ".join(self._skills.keys())
            return f"Unknown skill: {skill_name}\nAvailable: {available}"

        parts = [
            f"# Skill: {sd.name}",
        ]
        if sd.description:
            parts.append(f"\n_{sd.description}_")
        if args:
            parts.append(f"\n\n## Arguments\n{args}")

        parts.append(f"\nBase directory for this skill: {sd.base_dir}")
        parts.append(f"\n---\n{sd.content}")

        return "\n".join(parts)

    def get_skill_list(self) -> str:
        """Return formatted skill list for system reminder."""
        if not self._skills:
            return ""
        lines = []
        for name, sd in sorted(self._skills.items()):
            if sd.user_invocable:
                lines.append(f"- {name}: {sd.description}")
        if not lines:
            return ""
        return "\n".join(lines)
