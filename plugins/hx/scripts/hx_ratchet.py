#!/usr/bin/env python3
"""hx-ratchet — drift control. "Clearing existing debt is not required; adding new debt is not allowed."

In a brownfield repo, demanding "everything must be clean" makes the tool unusable. Instead each
metric keeps a baseline and the COUNT IS NOT ALLOWED TO RISE. When the count falls, the ratchet
clicks tighter: the baseline is permanently pulled down and can never go back up.

This script is a POLICY ENGINE too. Measurement commands live in the `measure` fields of
`.flow/ratchet.json`, owned by the target repo. A command must print a NUMBER; the script reads
the last integer in its output.

Rules:
    no-increase    : current <= baseline
    must-be-zero   : current == 0 (baseline ignored)

Usage:
    python hx_ratchet.py --baseline          # measure and write baselines (/hx:map)
    python hx_ratchet.py --check             # compare (/hx:verify)
    python hx_ratchet.py --check --tighten   # pull baselines down where they fell (/hx:ship)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hx_common import (
    Report, checks_shell, flow_root, has_placeholder, last_int, run_cmd, tail,
)

VALID_RULES = {"no-increase", "must-be-zero"}


def measurable(spec: dict) -> str | None:
    cmd = spec.get("measure")
    if not cmd or has_placeholder(str(cmd)) or str(cmd).startswith("checks.md"):
        return None
    return str(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow drift (ratchet) control")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--baseline", action="store_true", help="measure and write baselines")
    mode.add_argument("--check", action="store_true", help="compare against baselines")
    ap.add_argument("--tighten", action="store_true",
                    help="with --check: permanently lower baselines that fell")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--flow")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = Path(args.flow) if args.flow else flow_root(repo)
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2
    path = root / "ratchet.json"
    if not path.is_file():
        print(f"error: {path} is missing. /hx:map must be run.", file=sys.stderr)
        return 2

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"error: could not read ratchet.json: {e}", file=sys.stderr)
        return 2

    metrics: dict = data.get("metrics", {})
    rep = Report("hx-ratchet — " + ("baseline measurement" if args.baseline else "drift check"))
    if not metrics:
        rep.fail("metric list", "ratchet.json is empty — /hx:map must be re-run")
        return rep.emit(args.json)

    shell = checks_shell(root)
    changed = False
    for name, spec in sorted(metrics.items()):
        if not isinstance(spec, dict):
            continue
        rule = spec.get("rule", "no-increase")
        if rule not in VALID_RULES:
            rep.fail(name, f"unknown rule '{rule}' — {'|'.join(sorted(VALID_RULES))}")
            continue

        cmd = measurable(spec)
        if cmd is None:
            # An unconfigured metric must not pass silently.
            (rep.add("WARN", name, "no measure command — /hx:map should fill this in")
             if args.baseline else rep.skip(name, "no measure command"))
            continue

        rc, out = run_cmd(cmd, repo, shell=shell)
        current = last_int(out)
        if current is None:
            rep.fail(name, f"command printed no number (exit {rc}) — {tail(out)}")
            continue

        if args.baseline:
            spec["baseline"] = 0 if rule == "must-be-zero" else current
            changed = True
            rep.ok(name, f"baseline = {spec['baseline']}"
                         + (f" (measured {current})" if rule == "must-be-zero" else ""))
            continue

        if rule == "must-be-zero":
            if current == 0:
                rep.ok(name, "0")
            else:
                rep.fail(name, f"found {current}, must be 0")
            continue

        baseline = spec.get("baseline")
        if baseline is None:
            rep.skip(name, f"no baseline, measured {current} — run /hx:map")
        elif current > baseline:
            rep.fail(name, f"{baseline} -> {current} rose — new debt is not allowed")
        elif current < baseline:
            if args.tighten:
                spec["baseline"] = current
                changed = True
                rep.ok(name, f"{baseline} -> {current} fell, baseline TIGHTENED")
            else:
                rep.ok(name, f"{current} < baseline {baseline} (--tighten locks this in)")
        else:
            rep.ok(name, f"{current} = baseline")

    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return rep.emit(args.json)


if __name__ == "__main__":
    sys.exit(main())
