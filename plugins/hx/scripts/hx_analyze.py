#!/usr/bin/env python3
"""hx-analyze - checks a feature against its siblings, its history and its own coherence.

WHY THIS EXISTS, and why it is not just another phase. Every other check looks at ONE feature in
isolation. Three failure modes escape all of them:

  1. COLLISION - two developers plan changes to the same files at the same time. Nothing else in
     the workflow ever compares one feature's plan against another's.
  2. PRECEDENT - the work was already done and archived. The tool accumulates knowledge; not
     consulting it wastes the accumulation.
  3. INCOHERENCE - the same subject appears in both Scope IN and Scope OUT, the acceptance
     criteria say nothing about regressions, or the feature is plainly two features.

These are cheap to detect mechanically and expensive to discover late. Everything requiring
judgement (alternatives, blast radius, ambiguity) belongs to the skill, not to this script.

Usage:
    python hx_analyze.py --feature <slug> [--json]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from hx_common import Report, find_section, flow_root, front_fields, sections, table_rows

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "without",
    "new", "add", "adds", "support", "feature", "flow", "page", "screen", "api",
}
# Criteria that guard against regressions read like this.
NEGATIVE_MARKERS = [
    "does not", "do not", "must not", "never", "unchanged", "no new", "not reachable",
    "still", "remains", "no longer", "without breaking",
]
MAX_IN_ITEMS = 5
MAX_ACS = 7


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in STOPWORDS}


def scope_lines(state_text: str) -> tuple[str, str]:
    _, body = find_section(sections(state_text), "Scope")
    in_line = out_line = ""
    for line in (body or "").splitlines():
        s = line.strip()
        if s.upper().startswith("IN:"):
            in_line = s.split(":", 1)[1].strip()
        elif s.upper().startswith("OUT:"):
            out_line = s.split(":", 1)[1].strip()
    return in_line, out_line


def acceptance(state_text: str) -> list[str]:
    _, body = find_section(sections(state_text), "Acceptance criteria")
    out = []
    for line in (body or "").splitlines():
        m = re.match(r"^-\s*\[[ xX]\]\s*(?:AC\d+\s*)?(.+)$", line.strip())
        if m:
            out.append(m.group(1).strip())
    return out


def plan_touches(plan_path: Path) -> set[str]:
    """Paths a plan intends to touch, from the slice table."""
    if not plan_path.is_file():
        return set()
    _, body = find_section(sections(plan_path.read_text(encoding="utf-8")), "Slice table")
    paths: set[str] = set()
    for row in table_rows(body or ""):
        if len(row) >= 4:
            for p in re.split(r"[,\s]+", row[3]):
                p = p.strip().replace("\\", "/")
                if "/" in p:
                    paths.add(p)
    return paths


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow cross-feature and coherence analysis")
    ap.add_argument("--feature", required=True)
    ap.add_argument("--flow")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root = Path(args.flow) if args.flow else flow_root(Path(args.repo).resolve())
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2
    fdir = root / "features" / args.feature
    state_path = fdir / "state.md"
    if not state_path.is_file():
        print(f"error: no state.md for feature '{args.feature}'", file=sys.stderr)
        return 2

    rep = Report(f"hx-analyze - {args.feature}")
    text = state_path.read_text(encoding="utf-8")
    in_line, out_line = scope_lines(text)
    acs = acceptance(text)
    mine = tokens(in_line)

    # --- 1) IN and OUT must not claim the same subject ---
    clash = mine & tokens(out_line)
    if clash:
        rep.fail("scope coherence",
                 "in both IN and OUT: " + ", ".join(sorted(clash)) + " - decide which it is")
    else:
        rep.ok("scope coherence", "IN and OUT are disjoint")

    # --- 2) Sizing signals ---
    in_items = [i for i in in_line.split(",") if i.strip()]
    reasons = []
    if len(in_items) > MAX_IN_ITEMS:
        reasons.append(f"{len(in_items)} IN items > {MAX_IN_ITEMS}")
    if len(acs) >= MAX_ACS:
        reasons.append(f"{len(acs)} acceptance criteria at the limit of {MAX_ACS}")
    if reasons:
        rep.add("WARN", "sizing", "; ".join(reasons) + " - consider splitting the feature")
    else:
        rep.ok("sizing", f"{len(in_items)} IN item(s), {len(acs)} criteria")

    # --- 3) Is any criterion a regression guard? ---
    if acs and not any(m in a.lower() for a in acs for m in NEGATIVE_MARKERS):
        rep.add("WARN", "regression guard",
                "no criterion states what must NOT change - the most commonly forgotten one")
    elif acs:
        rep.ok("regression guard", "present")

    # --- 4) Collision with other in-flight features ---
    my_touches = plan_touches(fdir / "plan.md")
    siblings = [d for d in sorted((root / "features").glob("*"))
                if d.is_dir() and d.name != args.feature and (d / "state.md").is_file()]
    hard, soft = [], []
    for sib in siblings:
        sib_text = (sib / "state.md").read_text(encoding="utf-8")
        if front_fields(sib_text).get("phase") == "ship":
            continue
        shared_paths = my_touches & plan_touches(sib / "plan.md")
        if shared_paths:
            hard.append(f"{sib.name}: {', '.join(sorted(shared_paths)[:3])}")
            continue
        overlap = mine & tokens(scope_lines(sib_text)[0])
        if len(overlap) >= 2:
            soft.append(f"{sib.name} ({', '.join(sorted(overlap)[:3])})")
    if hard:
        rep.fail("collision with in-flight work",
                 "same files planned by: " + "; ".join(hard)
                 + " - sequence them or merge the features")
    elif soft:
        rep.add("WARN", "overlap with in-flight work",
                "similar scope: " + "; ".join(soft) + " - confirm they are separate")
    elif siblings:
        rep.ok("collision with in-flight work", f"{len(siblings)} sibling(s), no overlap")
    else:
        rep.ok("collision with in-flight work", "no other feature in flight")

    # --- 5) Precedent in the archive ---
    archive = root / "archive"
    precedents = []
    if archive.is_dir():
        for old in sorted(archive.glob("*")):
            old_state = old / "state.md"
            if not old_state.is_file():
                continue
            old_text = old_state.read_text(encoding="utf-8")
            _, intent = find_section(sections(old_text), "Intent")
            overlap = mine & tokens(scope_lines(old_text)[0] + " " + (intent or ""))
            if len(overlap) >= 2:
                precedents.append(f"{old.name} ({', '.join(sorted(overlap)[:3])})")
    if precedents:
        rep.add("WARN", "archive precedent",
                "similar shipped work: " + "; ".join(precedents[:3])
                + " - read it before planning")
    else:
        rep.ok("archive precedent", "nothing similar shipped")

    # --- 6) Questions still owed an answer ---
    _, questions = find_section(sections(text), "Open questions")
    pending = [q.strip() for q in (questions or "").splitlines()
               if q.strip().startswith("-") and "→" in q or "->" in q]
    if pending:
        rep.add("WARN", "open questions",
                f"{len(pending)} unanswered - research may build on an assumption")
    else:
        rep.ok("open questions", "none pending")

    return rep.emit(args.json)


if __name__ == "__main__":
    sys.exit(main())
