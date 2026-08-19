#!/usr/bin/env python3
"""hx-lint — validates the SCHEMA of produced documents.

Goal: you should not be able to tell which developer wrote an artifact. Template headings are
fixed, line budgets are enforced, unmeasurable acceptance criteria are rejected.

Usage:
    python hx_lint.py --feature <slug> [--json]
    python hx_lint.py --file .flow/features/x/state.md
    python hx_lint.py --all

Exit codes: 0 = every check passed, 1 = at least one FAIL, 2 = usage/environment error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from hx_structure import load_rules
from hx_common import (
    FIELD_RE, Report, effective_lines, find_section, front_fields, has_placeholder,
    flow_root, plugin_data, sections, table_rows,
)

# The template contract. Headings are matched by PREFIX so long headings stay robust.
SPEC: dict[str, dict] = {
    "state.md": {
        "budget": 60,
        "required": ["Intent", "Scope", "Module decision", "Dependency decision",
                     "Acceptance criteria", "Decisions", "Open questions", "Slice status"],
        "prose_ok": ["Intent"],
    },
    "findings.md": {
        "budget": 60,
        "required": ["Files to touch", "Pattern to follow", "Reusable existing code",
                     "Risks", "Unknowns", "Summary for main context"],
        "prose_ok": ["Summary for main context"],
    },
    "plan.md": {
        "budget": 80,
        "required": ["Slice table", "Placement check", "Slices requiring migration",
                     "Acceptance mapping", "Pre-ship one-time checks", "Risks"],
        "prose_ok": [],
    },
    "repo-map.md": {
        "budget": 120,
        "required": ["Scopes", "Layers", "Placement rules", "Naming", "Test placement"],
        "prose_ok": [],
        # In these sections <name> is pattern SYNTAX, not an unfilled placeholder.
        "placeholder_skip": ["Placement rules", "Layers", "Naming", "Test placement", "Scopes"],
    },
    "checks.md": {"budget": 25, "required": [], "prose_ok": []},
    "rules.md": {"budget": 30, "required": [], "prose_ok": []},
}

VALID_PHASES = {"discuss", "analyze", "research", "plan", "execute", "verify", "ship"}

# Universal capability vocabulary. Names are identical in every language; commands are local.
KNOWN_CAPS = {
    "lint", "format", "typecheck", "test-unit", "test-integration", "test-all",
    "e2e", "build", "migration", "run-dev", "extra", "doctor",
}

# The acceptance-criteria language rules live in data/criteria-language.json so teams writing
# criteria in another language can extend them without touching this file. A criterion is rejected
# only when a vague word appears AND no measurable trace is present.
try:
    _CRIT = plugin_data("criteria-language.json")
    VAGUE = [w.lower() for w in _CRIT["vague"]]
    _UNITS = [re.escape(u) for u in _CRIT["units"]]
except (OSError, KeyError, ValueError):
    VAGUE = ["works", "fast", "better", "clean", "nice", "robust", "easy"]
    _UNITS = ["ms", "sec", "seconds"]

# Measurable traces: a number, ratio, comparison, code span, path/endpoint, HTTP status, or unit.
MEASURABLE_RE = re.compile(
    r"(\d|%|≤|≥|<=|>=|<|>|`[^`]+`|/[a-z0-9_\-]+|HTTP\s*\d{3}"
    r"|\b(?:" + "|".join(_UNITS) + r")\b)",
    re.I,
)
AC_RE = re.compile(r"^-\s*\[( |x|X)\]\s*(?:AC\d+\s*)?(.+)$")


def check_budget(rep: Report, name: str, text: str, budget: int) -> None:
    n = len(effective_lines(text))
    if n > budget:
        rep.fail(f"{name}: line budget", f"{n} meaningful lines > limit {budget} — must be trimmed")
    else:
        rep.ok(f"{name}: line budget", f"{n}/{budget}")


def check_required(rep: Report, name: str, secs: dict[str, str], required: list[str]) -> None:
    if not required:
        rep.skip(f"{name}: required sections", "no required sections in schema")
        return
    missing = [r for r in required if find_section(secs, r)[0] is None]
    if missing:
        rep.fail(f"{name}: required sections", "missing: " + ", ".join(missing))
    else:
        rep.ok(f"{name}: required sections", f"{len(required)} sections present")


def check_empty_rows(rep: Report, name: str, secs: dict[str, str]) -> None:
    """A fully empty table row left over from the template = unfilled section."""
    empties = []
    for sec, body in secs.items():
        for row in table_rows(body):
            if row and not any(c.strip() for c in row):
                empties.append(sec)
                break
    if empties:
        rep.fail(f"{name}: empty table row", "unfilled: " + ", ".join(sorted(set(empties))))
    else:
        rep.ok(f"{name}: empty table row", "none")


def check_prose(rep: Report, name: str, secs: dict[str, str], prose_ok: list[str]) -> None:
    """Three or more consecutive plain-text lines where a table is expected = prose leak."""
    leaks = []
    for sec, body in secs.items():
        if any(sec.lower().startswith(p.lower()) for p in prose_ok):
            continue
        run, in_fence = 0, False
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("```"):
                in_fence = not in_fence
                run = 0
                continue
            # Tables, bullets, numbered lists and `key: value` lines are structural, not prose.
            if (in_fence or not s or s.startswith(("|", "-", "*", "+", ">", "#"))
                    or re.match(r"^\d+\.", s) or FIELD_RE.match(s)):
                run = 0
                continue
            run += 1
            if run >= 3:
                leaks.append(sec)
                break
    if leaks:
        rep.fail(f"{name}: prose leak", "table/list expected in: " + ", ".join(sorted(set(leaks))))
    else:
        rep.ok(f"{name}: prose leak", "none")


def check_placeholders(rep: Report, name: str, text: str, skip: list[str] | None = None) -> None:
    """Look for leftover <placeholders>. In `skip` sections <name> is pattern syntax."""
    from hx_common import PLACEHOLDER_RE, strip_comments
    body = strip_comments(text)
    if skip:
        for sec, sec_body in sections(text).items():
            if any(sec.lower().startswith(s.lower()) for s in skip):
                body = body.replace(sec_body, "")
    found = sorted(set(PLACEHOLDER_RE.findall(body)))
    if found:
        rep.fail(f"{name}: unfilled field",
                 f"{len(found)} placeholder(s) left: " + ", ".join(found[:6]))
    else:
        rep.ok(f"{name}: unfilled field", "none")


def lint_checks(rep: Report, checks_text: str, repo_map_text: str | None) -> None:
    """The checks.md contract: capability names must be universal, scopes must match repo-map."""
    from hx_common import parse_checks

    blocks = parse_checks(checks_text)
    scopes = {k: v for k, v in blocks.items() if k not in {"_global", "security"}}

    unknown = sorted({
        cap for caps in scopes.values() for cap in caps if cap not in KNOWN_CAPS
    })
    if unknown:
        rep.fail("checks: capability names",
                 "unknown: " + ", ".join(unknown) + " — outside the universal vocabulary")
    else:
        rep.ok("checks: capability names", f"{len(scopes)} scope(s), all known")

    no_pattern = [s for s, caps in scopes.items()
                  if "test-unit" in caps and "{pattern}" not in caps["test-unit"]]
    if no_pattern:
        rep.add("WARN", "checks: test-unit {pattern}",
                "missing in: " + ", ".join(no_pattern) + " — slice-level testing impossible")
    elif scopes:
        rep.ok("checks: test-unit {pattern}", "targeted testing possible")

    sec = blocks.get("security", {})
    if "audit-block" in sec:
        rep.ok("checks: security gate", "audit-block defined")
    else:
        rep.fail("checks: security gate",
                 "audit-block missing — ship cannot run without a security gate")
    for opt in ("secret-scan", "audit-count", "sast"):
        if opt not in sec:
            rep.add("WARN", f"checks: {opt}", "undefined — recommended")

    fields = front_fields(checks_text)
    for f in ("platform", "runner", "verified"):
        if has_placeholder(fields.get(f, "")):
            rep.fail(f"checks: {f} field", "unfilled")

    if repo_map_text:
        declared = {
            r[0].strip().lower()
            for r in table_rows(find_section(sections(repo_map_text), "Scopes")[1] or "")
            if r and r[0].strip()
        }
        mismatch = sorted(set(scopes) - declared)
        if mismatch and declared:
            rep.fail("checks: scope match", "not in repo-map Scopes: " + ", ".join(mismatch))
        elif declared:
            rep.ok("checks: scope match", "consistent with repo-map")


def lint_repo_map_contract(rep: Report, path: Path) -> None:
    """Every `requires:<glob>` target must itself be an allowed pattern.

    Otherwise the very file written to satisfy the requirement counts as an illegal placement, and
    the contract can never be satisfied by anyone. structure-check reports this too, but only once
    code is being written: `map` validates its own output through this linter, so a repo-map that
    contradicts itself has to fail HERE. Found by driving the phases end to end, where the first
    sign of a dangling requires: was a WARN in the middle of `execute`, long after the repo-map
    had been accepted and every later feature had started depending on it.
    """
    rules = load_rules(path)
    if not rules:
        return  # an empty table is reported by the section checks already
    known = {r["pattern"].replace("\\", "/") for r in rules}
    gaps = [f"{r['name']} -> requires:{req}"
            for r in rules for req in r["requires"] if req.replace("\\", "/") not in known]
    if gaps:
        rep.fail("repo-map: requires targets",
                 "; ".join(gaps) + " — not defined as an allowed pattern")
    else:
        rep.ok("repo-map: requires targets", f"{len(rules)} rule(s) internally consistent")


def lint_ratchet(rep: Report, path: Path) -> None:
    """ratchet.json must parse and every metric must be coherent.

    A malformed regex escape here silently breaks drift control, so it is validated as an
    artifact like any other document.
    """
    import json as _json
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError) as e:
        rep.fail("ratchet.json: parses", f"{e} - drift control is dead until this is fixed")
        return
    rep.ok("ratchet.json: parses", "valid JSON")

    metrics = data.get("metrics")
    if not isinstance(metrics, dict) or not metrics:
        rep.fail("ratchet.json: metrics", "empty or not an object")
        return

    bad_rule, no_measure, no_baseline = [], [], []
    for name, spec in sorted(metrics.items()):
        if not isinstance(spec, dict):
            bad_rule.append(f"{name} (not an object)")
            continue
        if spec.get("rule") not in {"no-increase", "must-be-zero"}:
            bad_rule.append(f"{name} (rule={spec.get('rule')})")
        measure = spec.get("measure")
        if not measure or has_placeholder(str(measure)):
            no_measure.append(name)
        elif spec.get("rule") == "no-increase" and spec.get("baseline") is None:
            no_baseline.append(name)
    if bad_rule:
        rep.fail("ratchet.json: rule names", ", ".join(bad_rule))
    else:
        rep.ok("ratchet.json: rule names", f"{len(metrics)} metric(s) valid")
    if no_measure:
        rep.add("WARN", "ratchet.json: measure command",
                "unconfigured, never enforced: " + ", ".join(no_measure))
    if no_baseline:
        rep.fail("ratchet.json: baseline",
                 "no-increase without a baseline: " + ", ".join(no_baseline)
                 + " - run hx_ratchet.py --baseline")


def lint_state(rep: Report, text: str) -> list[str]:
    """state.md specific checks. Returns the acceptance criteria texts."""
    secs = sections(text)
    fields = front_fields(text)

    phase = fields.get("phase", "")
    if phase in VALID_PHASES:
        rep.ok("state: phase field", phase)
    else:
        rep.fail("state: phase field", f"invalid '{phase}' — {'|'.join(sorted(VALID_PHASES))}")

    _, scope = find_section(secs, "Scope")
    out_line = ""
    for line in (scope or "").splitlines():
        if line.strip().upper().startswith("OUT:"):
            out_line = line.split(":", 1)[1].strip()
    if has_placeholder(out_line):
        rep.fail("state: scope OUT", "must not be empty — state what will NOT be built")
    else:
        rep.ok("state: scope OUT", out_line[:48])

    _, module = find_section(secs, "Module decision")
    mfields = {}
    for line in (module or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            mfields[k.strip().lower()] = v.strip()
    missing = [k for k in ("type", "feature-flag", "default") if has_placeholder(mfields.get(k, ""))]
    if missing:
        rep.fail("state: module decision", "unfilled: " + ", ".join(missing))
    else:
        rep.ok("state: module decision", f"{mfields.get('type')} / default {mfields.get('default')}")

    _, ac_body = find_section(secs, "Acceptance criteria")
    acs: list[str] = []
    for line in (ac_body or "").splitlines():
        m = AC_RE.match(line.strip())
        if m:
            acs.append(m.group(2).strip())
    if not acs:
        rep.fail("state: acceptance criteria count", "at least 1 required, found 0")
    elif len(acs) > 7:
        rep.fail("state: acceptance criteria count", f"{len(acs)} > 7 — scope must be split")
    else:
        rep.ok("state: acceptance criteria count", f"{len(acs)}/7")

    unmeasurable = [
        a for a in acs
        if any(v in a.lower() for v in VAGUE) and not MEASURABLE_RE.search(a)
    ]
    if unmeasurable:
        rep.fail("state: measurability",
                 f"{len(unmeasurable)} unmeasurable: " + " | ".join(x[:34] for x in unmeasurable[:3]))
    else:
        rep.ok("state: measurability", "all criteria measurable")

    return acs


def lint_plan(rep: Report, text: str, acs: list[str]) -> None:
    secs = sections(text)

    _, slice_body = find_section(secs, "Slice table")
    rows = [r for r in table_rows(slice_body or "") if len(r) >= 6 and r[0]]
    if not rows:
        rep.fail("plan: slice table", "empty — at least 1 slice required")
        return
    rep.ok("plan: slice table", f"{len(rows)} slice(s)")

    ids = [r[0] for r in rows]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        rep.fail("plan: slice id uniqueness", "duplicated: " + ", ".join(sorted(dupes)))
    else:
        rep.ok("plan: slice id uniqueness", "unique")

    no_verify = [r[0] for r in rows if has_placeholder(r[4])]
    if no_verify:
        rep.fail("plan: verification column", "empty for: " + ", ".join(no_verify))
    else:
        rep.ok("plan: verification column", "all filled")

    # A full-stack slice must be split: one slice cannot touch two different top-level scopes.
    cross = []
    for r in rows:
        tops = {p.strip().split("/")[0] for p in re.split(r"[,\s]+", r[3]) if "/" in p}
        if len(tops) > 1 and not re.search(r"-(be|fe)$", r[0], re.I):
            cross.append(f"{r[0]} ({', '.join(sorted(tops))})")
    if cross:
        rep.fail("plan: full-stack slice split",
                 "must be split (-be/-fe): " + "; ".join(cross))
    else:
        rep.ok("plan: full-stack slice split", "rule satisfied")

    _, map_body = find_section(secs, "Acceptance mapping")
    mapped = {r[0].strip().upper() for r in table_rows(map_body or "") if r and r[0]}
    expected = {f"AC{i}" for i in range(1, len(acs) + 1)}
    unmapped = sorted(expected - mapped)
    if acs and unmapped:
        rep.fail("plan: acceptance mapping", "not covered by any slice: " + ", ".join(unmapped))
    elif acs:
        rep.ok("plan: acceptance mapping", f"{len(expected)} criteria mapped")
    else:
        rep.skip("plan: acceptance mapping", "no criteria in state.md")

    _, place_body = find_section(secs, "Placement check")
    placed = {r[0].strip() for r in table_rows(place_body or "") if r and r[0]}
    missing = [i for i in ids if i not in placed]
    if missing:
        rep.fail("plan: placement check", "no repo-map rule recorded for: " + ", ".join(missing))
    else:
        rep.ok("plan: placement check", "every slice bound to a rule")


def lint_file(rep: Report, path: Path) -> list[str]:
    name = path.name
    spec = SPEC.get(name)
    if spec is None:
        rep.skip(f"{name}", "no schema defined, skipped")
        return []
    text = path.read_text(encoding="utf-8")
    secs = sections(text)
    check_budget(rep, name, text, spec["budget"])
    check_required(rep, name, secs, spec["required"])
    check_prose(rep, name, secs, spec["prose_ok"])
    check_placeholders(rep, name, text, spec.get("placeholder_skip"))
    check_empty_rows(rep, name, secs)
    if name == "state.md":
        return lint_state(rep, text)
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow document schema validator")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--feature", help="slug — validates .flow/features/<slug>/")
    g.add_argument("--file", help="a single file")
    g.add_argument("--all", action="store_true", help="the whole .flow tree")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--flow", help=".flow directory (default: search upwards)")
    args = ap.parse_args()

    rep = Report("hx-lint — document schema")

    if args.file:
        p = Path(args.file)
        if not p.is_file():
            print(f"error: no such file: {p}", file=sys.stderr)
            return 2
        lint_file(rep, p)
        return rep.emit(args.json)

    root = Path(args.flow) if args.flow else flow_root()
    if root is None or not root.is_dir():
        print("error: no .flow directory found. Has /hx:map been run?", file=sys.stderr)
        return 2

    repo_map_text = None
    for shared in ("repo-map.md", "checks.md", "rules.md"):
        p = root / shared
        if p.is_file():
            lint_file(rep, p)
            if shared == "repo-map.md":
                repo_map_text = p.read_text(encoding="utf-8")
                lint_repo_map_contract(rep, p)
            elif shared == "checks.md":
                lint_checks(rep, p.read_text(encoding="utf-8"), repo_map_text)
        elif shared == "repo-map.md":
            rep.fail("repo-map.md", "missing — no placement contract, planning impossible")
        elif shared == "checks.md":
            rep.fail("checks.md", "missing — command set undefined, /hx:map required")

    ratchet = root / "ratchet.json"
    if ratchet.is_file():
        lint_ratchet(rep, ratchet)
    else:
        rep.fail("ratchet.json", "missing — drift control undefined, /hx:map required")

    feats = ([root / "features" / args.feature] if args.feature
             else sorted((root / "features").glob("*")) if (root / "features").is_dir() else [])
    if args.feature and not feats[0].is_dir():
        print(f"error: no such feature: {feats[0]}", file=sys.stderr)
        return 2

    for fdir in feats:
        if not fdir.is_dir():
            continue
        acs: list[str] = []
        state = fdir / "state.md"
        if state.is_file():
            acs = lint_file(rep, state)
        else:
            rep.fail(f"{fdir.name}/state.md", "missing — no single source of truth")
        if (fdir / "findings.md").is_file():
            lint_file(rep, fdir / "findings.md")
        plan = fdir / "plan.md"
        if plan.is_file():
            lint_file(rep, plan)
            lint_plan(rep, plan.read_text(encoding="utf-8"), acs)

    return rep.emit(args.json)


if __name__ == "__main__":
    sys.exit(main())
