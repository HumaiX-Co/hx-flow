#!/usr/bin/env python3
"""Enforces hx-flow's own design principles.

Three rules erode if they stay mere intentions, so they are protected by a test:

  RULE 1 - A phase body is <= 40 lines.
           Heavyweight toolkits also started light. Without a budget every phase bloats.

  RULE 2 - No stack-specific tool name appears in a command that actually runs.
           Stack knowledge is written into the target repo's `.flow/checks.md`.
           Tool names may appear as EXPLANATION, never inside a command we execute.

  RULE 3 - The repository is English-only.
           Skill bodies and descriptions are prompts the model reads, and this plugin is meant
           to outlive one team - it may be published, and a prompt in one team's language is one
           the next maintainer cannot review. Per-team vocabulary belongs in
           data/criteria-language.json, never in code.

Usage: python tests/check_self.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "hx"

# The Windows console crashes on non-ASCII under cp1252; every entrypoint must pin this itself.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

BODY_BUDGET = 40

# Stack-specific TOOL names. These belong in the target repo's checks.md, never run from the plugin.
FORBIDDEN = [
    "pytest", "dotnet", "cargo", "gradle", "mvn", "npm", "yarn", "pnpm",
    "poetry", "ruff", "eslint", "prettier", "jest", "vitest", "playwright",
    "phpunit", "rspec", "rubocop", "tsc", "mypy", "bandit", "semgrep",
    "pip-audit", "govulncheck", "bundler-audit", "alembic", "uvicorn", "nox", "tox",
]
# Deliberate exemptions: the git host decision (GitHub) and git itself are stack-independent.
# `python` is exempt too: the scripts are written in it, which is not a target-repo assumption.
EXEMPT_WORDS = {"git", "gh", "python"}

# Detection lists and explanatory prose are exempt: a tool name there is DATA, not a command.
EXEMPT_DIRS = {"playbooks", "data", "templates"}

# RULE 3 allowances. Every non-ASCII character is flagged except these typographic and
# mathematical symbols, which are punctuation rather than language. They are given as CODE POINTS
# on purpose: spelling them out as literals would make this check flag its own source file.
ALLOWED_CODEPOINTS = frozenset({
    0x00A0,  # no-break space
    0x00B7,  # middle dot
    0x00A9, 0x00AE, 0x2122,  # copyright, registered, trademark
    0x2013, 0x2014,  # en dash, em dash
    0x2018, 0x2019, 0x201C, 0x201D,  # curly quotes
    0x2022,  # bullet
    0x2190, 0x2192, 0x2194,  # left, right, both arrows
    0x2264, 0x2265,  # less-or-equal, greater-or-equal
    0x2500, 0x2502, 0x251C, 0x2514,  # box drawing
    0x274C, 0x2705,  # cross mark, check mark
})
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt"}

DOCSTRING_RE = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
FENCE_RE = re.compile(r"```(?:[a-z!]*)\n(.*?)```", re.S)
INLINE_RE = re.compile(r"`([^`\n]+)`")
FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.S)


def executable_text(path: Path) -> str:
    """Extract only the parts of a file that ACTUALLY RUN."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        text = DOCSTRING_RE.sub("", text)
        return "\n".join(ln.split("#")[0] for ln in text.splitlines())
    if path.suffix == ".md":
        # In markdown a command is a fenced block or inline code. Plain text is explanation.
        return "\n".join(FENCE_RE.findall(text) + INLINE_RE.findall(text))
    return text


def repo_text_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(".git/") or "__pycache__" in rel:
            continue
        yield path, rel


def main() -> int:
    problems: list[str] = []
    checked = {"bodies": 0, "commands": 0, "language": 0}

    # --- RULE 1: phase body budget ---
    skills = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
    if not skills:
        problems.append("RULE 1  skills/ is empty - no phase skill found")
    for skill in skills:
        body = FRONTMATTER_RE.sub("", skill.read_text(encoding="utf-8"), count=1)
        lines = [ln for ln in body.splitlines() if ln.strip()]
        checked["bodies"] += 1
        if len(lines) > BODY_BUDGET:
            problems.append(
                f"RULE 1  {skill.parent.name}: body is {len(lines)} lines > {BODY_BUDGET} "
                "- move detail into a playbook")

    # --- RULE 2: no stack name in executed commands ---
    for path in sorted(PLUGIN.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
            continue
        if any(part in EXEMPT_DIRS for part in path.relative_to(PLUGIN).parts):
            continue
        code = executable_text(path).lower()
        checked["commands"] += 1
        for word in FORBIDDEN:
            if word in EXEMPT_WORDS:
                continue
            if re.search(rf"(?<![a-z0-9_-]){re.escape(word)}(?![a-z0-9_-])", code):
                problems.append(
                    f"RULE 2  {path.relative_to(ROOT)}: an executed command contains '{word}' "
                    "- stack knowledge belongs in checks.md")

    # --- RULE 3: English-only repository ---
    for path, rel in repo_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        checked["language"] += 1
        for n, line in enumerate(text.splitlines(), 1):
            bad = sorted({c for c in line
                          if ord(c) > 127 and ord(c) not in ALLOWED_CODEPOINTS})
            if bad:
                shown = " ".join(f"U+{ord(c):04X}" for c in bad[:6])
                problems.append(
                    f"RULE 3  {rel}:{n}: non-English character(s) {shown} "
                    "- this repository is English-only")

    print()
    print("hx-flow self-check")
    print("-" * 100)
    if problems:
        for p in problems:
            print(f"FAIL  {p}")
    else:
        print(f"OK    RULE 1 - {checked['bodies']} phase bodies <= {BODY_BUDGET} lines")
        print(f"OK    RULE 2 - no stack-specific command in {checked['commands']} files")
        print(f"OK    RULE 3 - {checked['language']} files are English-only")
    print("-" * 100)
    print("DESIGN PRINCIPLES HOLD" if not problems else f"{len(problems)} VIOLATION(S)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
