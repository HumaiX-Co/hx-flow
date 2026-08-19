#!/usr/bin/env python3
"""hx-security — the security gate. The one check that can block `ship`.

DESIGN: this script is NOT A SCANNER, it is a POLICY ENGINE. Scan commands live in the
`security` block of `.flow/checks.md`, owned by the target repo. The script only knows when a
check runs and when it blocks. That keeps every ecosystem's audit tool working through one
engine while the plugin knows none of them.

The checks.md contract:
    security
      audit-block: <command>   # exit NON-ZERO when a blocking (critical/high) vuln exists
      audit-count: <command>   # optional: print the TOTAL vulnerability COUNT (for the ratchet)
      secret-scan: <command>   # leaked credential scan
      sast:        <command>   # static security analysis

Cost policy per mode:
    --mode slice   : audit-block ONLY when a dependency manifest changed. Cheap.
    --mode verify  : slice plus sast.
    --mode ship    : everything, full scope, THE GATE. Missing config also counts as FAIL.

Critical security property: in `ship` mode a missing `audit-block` does NOT pass silently, it
FAILS. Forgetting a security check must not be equivalent to passing it.

Usage:
    python hx_security.py --mode ship [--feature <slug>] [--base origin/main] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hx_common import (
    Report, canary_secret_scan, changed_files, checks_shell, find_section, flow_root,
    has_placeholder, last_int, parse_checks, pattern_to_regex, plugin_data, run_cmd,
    sections, tail,
)


def manifest_touched(changeset: set[str]) -> list[str]:
    data = plugin_data("manifests.json")
    names = set(data["manifests"])
    globs = [pattern_to_regex(g) for g in data.get("manifest_globs", [])]
    hits = []
    for p in changeset:
        norm = p.replace("\\", "/")
        if Path(norm).name in names or any(g.match(norm) for g in globs):
            hits.append(norm)
    return sorted(hits)


def dependency_decision(state_path: Path) -> tuple[bool, str]:
    """Is there a filled-in 'Dependency decision' section in state.md?"""
    if not state_path.is_file():
        return False, "state.md missing"
    secs = sections(state_path.read_text(encoding="utf-8"))
    name, body = find_section(secs, "Dependency decision")
    if name is None:
        return False, "no '## Dependency decision' section"
    content = "\n".join(ln for ln in body.splitlines() if ln.strip())
    if not content or has_placeholder(content):
        return False, "section left empty"
    return True, content.splitlines()[0][:70]


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow security gate")
    ap.add_argument("--mode", choices=["slice", "verify", "ship"], required=True)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--feature", help="slug — needed for the dependency decision check")
    ap.add_argument("--base", help="comparison ref")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--flow")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    is_ship = args.mode == "ship"
    rep = Report(f"hx-security — mode: {args.mode}" + ("  [GATE]" if is_ship else ""))

    root = Path(args.flow) if args.flow else flow_root(repo)
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2

    checks_path = root / "checks.md"
    sec: dict[str, str] = {}
    if checks_path.is_file():
        sec = parse_checks(checks_path.read_text(encoding="utf-8")).get("security", {})
    if not sec and is_ship:
        rep.fail("security configuration",
                 "no 'security' block in checks.md — ship cannot run without a security gate")
        return rep.emit(args.json)

    shell = checks_shell(root)
    added, modified = changed_files(repo, args.base)
    changeset = set(added) | set(modified)
    touched = manifest_touched(changeset)

    # --- 1) Did the dependency surface change? ---
    if touched:
        rep.add("WARN", "dependency surface", ", ".join(touched[:4]))
    else:
        rep.ok("dependency surface", "no manifest changed")

    # --- 2) A new dependency is a decision. It cannot be added silently. ---
    if touched and args.feature:
        ok, detail = dependency_decision(root / "features" / args.feature / "state.md")
        if ok:
            rep.ok("dependency decision", detail)
        else:
            rep.fail("dependency decision",
                     f"manifest changed but no decision recorded ({detail}) — return to discuss")
    elif touched and is_ship:
        rep.fail("dependency decision", "--feature not given, decision could not be verified")

    # --- 3) Vulnerability gate ---
    audit = sec.get("audit-block")
    should_audit = is_ship or args.mode == "verify" or bool(touched)
    if not audit:
        (rep.fail if is_ship else rep.skip)(
            "vulnerability gate (audit-block)",
            "undefined in checks.md" + (" — ship blocked" if is_ship else ""))
    elif not should_audit:
        rep.skip("vulnerability gate (audit-block)", "no manifest change, skipped")
    else:
        rc, out = run_cmd(audit, repo, shell=shell)
        if rc == 0:
            rep.ok("vulnerability gate (audit-block)", "no blocking vulnerability")
        else:
            rep.fail("vulnerability gate (audit-block)", f"exit {rc} — {tail(out)}")

    # --- 4) Vulnerability count ratchet ---
    count_cmd = sec.get("audit-count")
    ratchet_path = root / "ratchet.json"
    if count_cmd and should_audit:
        rc, out = run_cmd(count_cmd, repo, shell=shell)
        current = last_int(out)
        if current is None:
            rep.skip("vulnerability count (ratchet)", f"no number in output — {tail(out)}")
        else:
            baseline = None
            if ratchet_path.is_file():
                try:
                    data = json.loads(ratchet_path.read_text(encoding="utf-8"))
                    baseline = (data.get("metrics", {}).get("vuln-total", {}) or {}).get("baseline")
                except (json.JSONDecodeError, OSError):
                    baseline = None
            if baseline is None:
                rep.skip("vulnerability count (ratchet)", f"no baseline, current: {current}")
            elif current > baseline:
                rep.fail("vulnerability count (ratchet)",
                         f"{baseline} -> {current} rose — new debt is not allowed")
            else:
                rep.ok("vulnerability count (ratchet)", f"{current} <= baseline {baseline}")
    elif count_cmd:
        rep.skip("vulnerability count (ratchet)", "not measured in this mode")

    # --- 5) Secret scan ---
    scan = sec.get("secret-scan")
    if not scan:
        (rep.fail if is_ship else rep.skip)(
            "secret scan", "undefined in checks.md" + (" — ship blocked" if is_ship else ""))
    else:
        rc, out = run_cmd(scan, repo, shell=shell)
        if rc == 0:
            rep.ok("secret scan", "clean")
            if is_ship:
                # A clean result only means something if the scanner can detect anything at all.
                # Checking this at ship — not only in doctor — closes the window where the scanner
                # breaks after setup and every later ship passes on a dead gate.
                status, why = canary_secret_scan(scan, repo, shell)
                rep.add(status, "secret scan effectiveness", why)
        else:
            rep.fail("secret scan", f"exit {rc} — {tail(out)}")

    # --- 6) SAST (verify and ship only) ---
    sast = sec.get("sast")
    if args.mode == "slice":
        rep.skip("static security analysis", "not run in slice mode (cost)")
    elif not sast:
        (rep.add("WARN", "static security analysis", "undefined in checks.md — recommended")
         if is_ship else rep.skip("static security analysis", "undefined"))
    else:
        rc, out = run_cmd(sast, repo, shell=shell)
        if rc == 0:
            rep.ok("static security analysis", "no findings")
        else:
            rep.fail("static security analysis", f"exit {rc} — {tail(out)}")

    code = rep.emit(args.json)
    if code and is_ship and not args.json:
        print("\nSHIP BLOCKED. The security gate must pass before shipping.")
    return code


if __name__ == "__main__":
    sys.exit(main())
