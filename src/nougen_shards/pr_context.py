"""PR review context injection (Shang Tsung Phase 3, partial).

Gathers the canon a reviewer needs before judging a diff: repo rule files,
plus a precedence order so conflicting guidance resolves the same way every
time. Deliberately dumb — no LLM calls here, just collection + ordering.
Precedence (highest wins): GM instruction > repo canon/rules > active relay
objective > agent skill > generic reviewer defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

RULE_FILENAMES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md")


@dataclass
class ReviewContext:
    repo_root: str
    rule_files: dict = field(default_factory=dict)   # filename -> content
    skill_files: list = field(default_factory=list)   # paths under skills/
    relay_objective: Optional[str] = None
    gm_instruction: Optional[str] = None

    def precedence_note(self) -> str:
        return (
            "Precedence (highest wins): GM instruction > repo canon/rules "
            "(CLAUDE.md/AGENTS.md/GEMINI.md) > active relay objective > "
            "agent skill > generic reviewer defaults."
        )

    def as_prompt_block(self, max_chars_per_file: int = 4000) -> str:
        """Render collected context as a single text block a reviewer prompt
        can prepend. Truncates per-file, not silently drops files, so a huge
        CLAUDE.md doesn't starve the rest of the context."""
        parts = [self.precedence_note()]
        if self.gm_instruction:
            parts.append(f"## GM instruction\n{self.gm_instruction}")
        for name, content in self.rule_files.items():
            trimmed = content[:max_chars_per_file]
            if len(content) > max_chars_per_file:
                trimmed += f"\n...[truncated, {len(content) - max_chars_per_file} more chars]"
            parts.append(f"## {name}\n{trimmed}")
        if self.relay_objective:
            parts.append(f"## Active relay objective\n{self.relay_objective}")
        if self.skill_files:
            parts.append("## Relevant skills\n" + "\n".join(f"- {p}" for p in self.skill_files))
        return "\n\n".join(parts)


def gather_context(
    repo_root: str,
    relay_objective: Optional[str] = None,
    gm_instruction: Optional[str] = None,
) -> ReviewContext:
    """Collect rule files + skill index from a repo checkout. Missing files
    are simply absent from rule_files — a repo with no CLAUDE.md just yields
    a shorter block, not an error."""
    root = Path(repo_root)
    ctx = ReviewContext(repo_root=repo_root, relay_objective=relay_objective, gm_instruction=gm_instruction)

    for name in RULE_FILENAMES:
        f = root / name
        if f.is_file():
            try:
                ctx.rule_files[name] = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass

    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
            ctx.skill_files.append(str(skill_md.relative_to(root)))

    return ctx
