"""Skill registry: discover, index and load SKILL.md packages.

Skills were previously write-only. ``EvolutionEngine.evolve_skill`` emitted flat
markdown files into the vault and nothing ever read them back, so every skill the
system generated was invisible to the agents meant to use them. This module is the
missing read side.

Two layouts are discovered:

    <dir>/<name>/SKILL.md    canonical - frontmatter (name, description) + body
    <dir>/<name>.md          legacy flat file, kept readable so old output is not
                             stranded; treated as body-only with a derived name

Frontmatter is parsed with the standard library on purpose. PyYAML appears in
``requirements.txt`` but not in ``pyproject.toml``'s dependencies, so a
``pip install .`` install would not have it, and a registry that fails to import
is worse than one that understands a small subset of YAML.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import core

logger = logging.getLogger(__name__)

# Directory name searched under each root, and under the vault.
_FALLBACK_SKILLS_DIRNAME = "skills"

# How many shared terms make a skill apply to a task. One is deliberate: a
# missed skill means the work is done wrong, a spurious one costs a moment.
# Override with NOUGEN_SKILL_MATCH_MIN.
_FALLBACK_MATCH_MIN = 1

# Words too common to signal anything about which skill applies.
_STOPWORDS = frozenset("""
a an and are as at be build by can create do does for from get give go
have how i in into is it its make me my need new of on or our out please
should so that the their them then there these they this to up us use
used using want was we what when where which who will with would you your
""".split())

# Frontmatter delimiters, tolerant of CRLF - these files are edited on Windows.
_FRONTMATTER = re.compile(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_SCALAR = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or default


def resolve_skill_roots() -> list[Path]:
    """Directories to search for skills, in precedence order.

    ``NOUGEN_SKILLS_DIR`` wins and may list several paths separated by the
    platform path separator. Otherwise the packaged ``skills/`` directory that
    ships with the repository is probed, then the vault's own ``skills/``
    directory where evolved skills land.
    """
    explicit = _env("NOUGEN_SKILLS_DIR")
    if explicit:
        roots = [Path(p).expanduser() for p in explicit.split(os.pathsep) if p.strip()]
        if roots:
            return roots

    roots: list[Path] = []
    for parent in Path(__file__).resolve().parents:
        candidate = parent / _FALLBACK_SKILLS_DIRNAME
        if candidate.is_dir():
            roots.append(candidate)
            break

    vault_skills = core.GLOBAL_DIR / _FALLBACK_SKILLS_DIRNAME
    if vault_skills not in roots:
        roots.append(vault_skills)

    if not roots:
        logger.warning("no skill roots resolved; set NOUGEN_SKILLS_DIR")
    return roots


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split ``---`` frontmatter from the body.

    Understands the flat ``key: value`` subset that SKILL.md files actually use.
    Quotes are stripped; nested structures are ignored rather than guessed at.
    Returns ``({}, text)`` when no frontmatter is present.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line[:1] in (" ", "\t"):
            continue  # comments and nested keys are out of scope
        found = _SCALAR.match(stripped)
        if not found:
            continue
        value = found.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[found.group(1).lower()] = value

    return meta, text[match.end():]


@dataclass
class Skill:
    """One discovered skill."""

    name: str
    description: str
    path: Path
    body: str = field(repr=False, default="")

    @property
    def summary(self) -> str:
        return f"{self.name} - {self.description}" if self.description else self.name


def _load_file(path: Path, fallback_name: str) -> Optional[Skill]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("skipping unreadable skill %s: %s", path, exc)
        return None

    meta, body = parse_frontmatter(text)
    name = meta.get("name") or fallback_name
    description = meta.get("description", "").strip()
    if not description:
        # Legacy flat files carry no frontmatter. Use the first meaningful line
        # so the roster still says something useful about them.
        for line in body.splitlines():
            candidate = line.strip().lstrip("#").strip()
            if candidate:
                description = candidate[:200]
                break
    return Skill(name=name, description=description, path=path, body=body)


def discover(roots: Optional[list[Path]] = None) -> list[Skill]:
    """Find every skill across the resolved roots.

    Earlier roots win on name collision, so an explicitly configured directory
    can shadow a packaged skill of the same name.
    """
    found: dict[str, Skill] = {}
    for root in roots if roots is not None else resolve_skill_roots():
        if not root.is_dir():
            continue
        try:
            entries = sorted(root.iterdir())
        except OSError as exc:
            logger.warning("skipping unreadable skill root %s: %s", root, exc)
            continue

        for entry in entries:
            skill: Optional[Skill] = None
            if entry.is_dir():
                manifest = entry / "SKILL.md"
                if manifest.is_file():
                    skill = _load_file(manifest, entry.name)
            elif entry.suffix.lower() == ".md" and entry.name != "SKILL.md":
                skill = _load_file(entry, entry.stem)

            if skill and skill.name not in found:
                found[skill.name] = skill

    return sorted(found.values(), key=lambda s: s.name)


def get(name: str, roots: Optional[list[Path]] = None) -> Optional[Skill]:
    """Look up one skill by name, case-insensitively."""
    wanted = name.strip().lower()
    for skill in discover(roots):
        if skill.name.lower() == wanted:
            return skill
    return None


def _stem(word: str) -> str:
    """Crude singularisation so 'palette' matches 'palettes'.

    Not linguistics - just enough that a plural in the task does not miss a
    singular in the description. That near-miss is invisible when it happens,
    which makes it the worst kind of matching bug.
    """
    if len(word) < 4 or not word.endswith("s") or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    # Only strip a full "es" after a sibilant (boxes, churches). Elsewhere the
    # "e" belongs to the stem: palettes -> palette, not palett.
    if word.endswith(("ses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    return word[:-1]


def _terms(text: str) -> set[str]:
    """Lowercase stemmed word set, minus filler that would match everything."""
    words = set(re.findall(r"[a-z0-9]+", text.lower())) - _STOPWORDS
    return {_stem(w) for w in words}


def match(task: str, roots: Optional[list[Path]] = None) -> list[Skill]:
    """Skills that govern ``task``, best first.

    Matching is deliberately generous. Skills are mandatory, so returning one
    that turns out to be marginal costs the reader a moment, while missing one
    means the work is done wrong. A skill's own description is the trigger
    surface - that is what descriptions are for.
    """
    wanted = _terms(task)
    if not wanted:
        return []

    threshold = int(_env("NOUGEN_SKILL_MATCH_MIN", "") or _FALLBACK_MATCH_MIN)
    scored: list[tuple[int, Skill]] = []
    for skill in discover(roots):
        surface = _terms(f"{skill.name} {skill.description}")
        overlap = len(wanted & surface)
        # A skill named in the task always applies, however short the overlap.
        if skill.name.lower() in task.lower():
            overlap = max(overlap, threshold)
        if overlap >= threshold:
            scored.append((overlap, skill))

    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return [skill for _, skill in scored]


def roster(roots: Optional[list[Path]] = None) -> str:
    """One line per skill, for surfacing the catalogue to a connecting agent."""
    skills = discover(roots)
    if not skills:
        return "(no skills installed)"
    return "\n".join(f"- {s.summary}" for s in skills)
