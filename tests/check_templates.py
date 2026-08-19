#!/usr/bin/env python3
"""Checks that documents and the code describing them cannot drift apart. Two jobs.

1. TEMPLATES vs the hx-lint schema. The silent-breakage scenario: someone renames a heading in
   `templates/state.md`, `SPEC` in `hx_lint.py` is not updated, and the validator either reports
   that section as forever "missing" or stops checking it at all.

2. TRELLO ROUTING vs `hx_trello.py`. A subcommand named in a skill but absent from the script
   fails during `ship`, against a live board. An implemented subcommand absent from
   `playbooks/trello.md` is an operation for which nobody chose MCP or script.

Usage: python tests/check_templates.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "hx"
sys.path.insert(0, str(PLUGIN / "scripts"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError, OSError):
        pass

from hx_common import effective_lines, find_section, sections  # noqa: E402
from hx_lint import SPEC  # noqa: E402


TRELLO_SCRIPT = PLUGIN / "scripts" / "hx_trello.py"
TRELLO_PLAYBOOK = PLUGIN / "playbooks" / "trello.md"
VERB_RE = re.compile(r"(\w+)\s*=\s*sub\.add_parser\(\"(\w+)\"\)")
OP_RE = re.compile(r"(\w+)\.add_parser\(\"(\w+)\"\)")
REF_RE = re.compile(r"hx_trello\.py\s+(\w+)\s+(\w+)")


def trello_subcommands() -> set[tuple[str, str]]:
    """The (verb, op) pairs hx_trello.py actually implements, read from its parser."""
    src = TRELLO_SCRIPT.read_text(encoding="utf-8")
    verb_of_var = {var: verb for var, verb in VERB_RE.findall(src)}
    pairs = set()
    for var, op in OP_RE.findall(src):
        if var in verb_of_var:
            pairs.add((verb_of_var[var], op))
    return pairs


def check_trello_routing(problems: list[str]) -> int:
    """Documentation and script must not drift apart.

    Both directions matter. A documented subcommand that does not exist makes a phase fail at the
    worst moment - during ship, against a live board. An implemented subcommand missing from the
    routing playbook is worse than dead code: the playbook is what decides MCP versus script, so
    an unrouted operation is one nobody chose a mechanism for.
    """
    implemented = trello_subcommands()
    if not implemented:
        problems.append("hx_trello.py: no subcommands found - has the parser been restructured?")
        return 0

    for path in sorted(PLUGIN.rglob("*.md")):
        for verb, op in REF_RE.findall(path.read_text(encoding="utf-8")):
            if (verb, op) not in implemented:
                problems.append(
                    f"{path.relative_to(PLUGIN)}: references 'hx_trello.py {verb} {op}' "
                    "which the script does not implement")

    routed = set(REF_RE.findall(TRELLO_PLAYBOOK.read_text(encoding="utf-8")))
    for verb, op in sorted(implemented - routed):
        problems.append(
            f"playbooks/trello.md: '{verb} {op}' is implemented but not in the routing table "
            "- no mechanism was chosen for it")
    return len(implemented)


def main() -> int:
    problems: list[str] = []
    checked = 0

    for name, spec in sorted(SPEC.items()):
        path = PLUGIN / "templates" / name
        if not path.is_file():
            problems.append(f"{name}: template file missing but defined in SPEC")
            continue
        checked += 1
        text = path.read_text(encoding="utf-8")
        secs = sections(text)

        for required in spec["required"]:
            if find_section(secs, required)[0] is None:
                problems.append(
                    f"{name}: SPEC expects a '{required}' section but the template has none "
                    "— if the heading was renamed, SPEC must be updated")

        n = len(effective_lines(text))
        if n > spec["budget"]:
            problems.append(
                f"{name}: the template itself is {n} lines > budget {spec['budget']} "
                "— a filled-in copy could never fit")

        for allowed in spec.get("prose_ok", []):
            if find_section(secs, allowed)[0] is None:
                problems.append(f"{name}: prose_ok section '{allowed}' is not in the template")

    # Any template missing from SPEC (an unchecked artifact)
    for path in sorted((PLUGIN / "templates").glob("*.md")):
        if path.name not in SPEC:
            problems.append(f"{path.name}: template exists but is absent from SPEC — hx-lint ignores it")

    n_trello = check_trello_routing(problems)

    print()
    print("hx-flow template/schema consistency")
    print("-" * 100)
    if problems:
        for p in problems:
            print(f"FAIL  {p}")
    else:
        print(f"OK    {checked} templates consistent with SPEC "
              "(headings, budgets, prose allowances)")
        print(f"OK    {n_trello} Trello subcommands match the docs and the routing table")
    print("-" * 100)
    print("CONSISTENT" if not problems else f"{len(problems)} INCONSISTENCY(S)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
