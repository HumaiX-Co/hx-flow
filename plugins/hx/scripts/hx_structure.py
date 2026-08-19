#!/usr/bin/env python3
"""structure-check — catches codebase structural drift.

The "Placement rules (allowed patterns)" table in `.flow/repo-map.md` is a CONTRACT.
This script glob-matches changed files against those patterns. No model judgement involved.

Rules:
  * Every NEWLY added file must match at least one allowed pattern, otherwise FAIL.
  * Modifying existing files is free — their placement is already established.
  * A `requires:<glob>` directive in the "extra requirement" column: when a file matching
    that rule changes, the changeset must also contain a file matching <glob>.
    Example: a data model changed but no migration was added -> FAIL.

Usage:
    python hx_structure.py [--base origin/main] [--json] [--repo .]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from hx_common import (
    Report, changed_files, find_section, flow_root, pattern_to_regex, sections, table_rows,
)

REQUIRES_RE = re.compile(r"requires:\s*(\S+)", re.I)


def load_rules(repo_map: Path) -> list[dict]:
    """repo-map.md -> [{name, what, pattern, regex, requires[]}]"""
    secs = sections(repo_map.read_text(encoding="utf-8"))
    _, body = find_section(secs, "Placement rules")
    if body is None:
        return []
    rules = []
    for row in table_rows(body):
        # NOTE: <name> in the pattern column is valid SYNTAX, not a placeholder, so it must
        # not be filtered with has_placeholder — only emptiness is checked.
        if len(row) < 3 or not row[0].strip() or not row[2].strip():
            continue
        extra = row[3] if len(row) > 3 else ""
        rules.append({
            "name": row[0],
            "what": row[1],
            "pattern": row[2].strip().strip("`"),
            "regex": pattern_to_regex(row[2]),
            "requires": REQUIRES_RE.findall(extra),
        })
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow structural drift check")
    ap.add_argument("--repo", default=".", help="git repository root")
    ap.add_argument("--base", help="comparison ref (for example origin/main)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--flow", help=".flow directory")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    rep = Report("structure-check — placement contract")

    root = Path(args.flow) if args.flow else flow_root(repo)
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2

    repo_map = root / "repo-map.md"
    if not repo_map.is_file():
        rep.fail("repo-map.md", "missing — placement contract undefined")
        return rep.emit(args.json)

    rules = load_rules(repo_map)
    if not rules:
        rep.fail("placement rules", "table is empty — /hx:map must be re-run")
        return rep.emit(args.json)
    rep.ok("placement rules", f"{len(rules)} rule(s) loaded")

    # Contract consistency: a requires: target must itself be an allowed pattern, otherwise the
    # very file that satisfies the requirement counts as an illegal placement.
    known = {r["pattern"].replace("\\", "/") for r in rules}
    for r in rules:
        for req in r["requires"]:
            if req.replace("\\", "/") not in known:
                rep.add("WARN", f"contract gap: {r['name']}",
                        f"requires:{req} is not defined as an allowed pattern — add a repo-map rule")

    added, modified = changed_files(repo, args.base)
    # hx-flow's own workspace is not codebase; it is not subject to placement rules.
    keep = lambda ps: [p for p in ps if not p.replace("\\", "/").startswith(".flow/")]
    added, modified = keep(added), keep(modified)
    changeset = set(added) | set(modified)
    if not changeset:
        rep.skip("changeset", "empty — nothing to check")
        return rep.emit(args.json)
    rep.ok("changeset", f"{len(added)} added, {len(modified)} modified")

    # 1) Do new files match an allowed pattern?
    orphans = []
    for path in added:
        norm = path.replace("\\", "/")
        if not any(r["regex"].match(norm) for r in rules):
            orphans.append(norm)
    if orphans:
        for o in orphans[:8]:
            rep.fail("illegal placement", f"{o} — matches no allowed pattern")
        if len(orphans) > 8:
            rep.fail("illegal placement", f"... and {len(orphans) - 8} more file(s)")
    else:
        rep.ok("illegal placement", f"{len(added)} new file(s) conform")

    # 2) requires: directives — modified files trigger rules too
    for r in rules:
        if not r["requires"]:
            continue
        triggered = [p.replace("\\", "/") for p in changeset
                     if r["regex"].match(p.replace("\\", "/"))]
        if not triggered:
            continue
        for req in r["requires"]:
            req_re = pattern_to_regex(req)
            if any(req_re.match(p.replace("\\", "/")) for p in changeset):
                rep.ok(f"requirement: {r['name']}", f"{req} satisfied")
            else:
                rep.fail(f"requirement: {r['name']}",
                         f"{triggered[0]} changed but nothing matches '{req}'")

    return rep.emit(args.json)


if __name__ == "__main__":
    sys.exit(main())
