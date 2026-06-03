"""Skill loader — scans .myagent/skills/ for SKILL.md files."""

import re
import yaml
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class SkillDef:
    """Parsed skill definition from a SKILL.md file."""
    name: str
    description: str
    content: str           # full markdown body (after frontmatter)
    base_dir: str          # directory containing SKILL.md
    user_invocable: bool = True


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text. Returns (frontmatter_dict, body)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, m.group(2)


def load_skills(cwd: Path | str | None = None) -> list[SkillDef]:
    """Scan .myagent/skills/ directories within cwd for SKILL.md files.

    Scans:
      - {cwd}/.myagent/skills/  (project)
      - ~/.myagent/skills/      (user)
    """
    cwd = Path(cwd) if cwd else Path.cwd()
    search_dirs = [
        cwd / ".myagent" / "skills",
        Path.home() / ".myagent" / "skills",
    ]

    seen: set[str] = set()
    skills: list[SkillDef] = []

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for skill_dir in sorted(search_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue

            try:
                text = skill_md.read_text(encoding="utf-8")
            except Exception:
                continue

            fm, body = _parse_frontmatter(text)
            name = fm.get("name", skill_dir.name)
            if name in seen:
                continue  # project overrides user
            seen.add(name)

            description = fm.get("description", "")
            user_invocable = fm.get("user-invocable", True)

            skills.append(SkillDef(
                name=name,
                description=description,
                content=body.strip(),
                base_dir=str(skill_dir),
                user_invocable=user_invocable,
            ))

    return skills
