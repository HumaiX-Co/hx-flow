#!/usr/bin/env python3
"""hx-doctor - does THIS machine satisfy what .flow/checks.md declares?

WHY THIS EXISTS. `/hx:map` verifies the commands once, on the machine that ran it. Every developer
who clones the repo afterwards inherits those commands without any guarantee that their machine can
run them: a missing task runner, an uninstalled linter, no node_modules, no database. Without this
check the first symptom is a phase failing halfway through for a reason that has nothing to do with
the code — which is exactly the non-determinism the tool exists to remove.

It reports, per capability, whether the declared command is runnable, and which phase each gap
blocks. It changes nothing.

Probing rule: a command is executed with a fast, side-effect-free variant where one exists
(`--version`, `--help`); otherwise only its executable is resolved. Doctor must never run a test
suite or a build.

Usage:
    python hx_doctor.py [--repo .] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from hx_common import (
    Report, bash_path, canary_secret_scan, checks_shell, flow_root, parse_checks,
    run_cmd, tail,
)

# Which phase stops working when a capability is unavailable.
BLOCKS = {
    "lint": "execute, verify",
    "typecheck": "verify",
    "test-unit": "execute",
    "test-all": "verify",
    "e2e": "verify (pre-ship)",
    "build": "verify",
    "migration": "execute (model slices)",
    "extra": "verify (pre-ship)",
    "audit-block": "ship (HARD BLOCK)",
    "audit-count": "verify, ship (ratchet only)",
    "secret-scan": "ship (HARD BLOCK)",
    "sast": "verify, ship (advisory)",
}
CRITICAL = {"audit-block", "secret-scan"}

# Front-matter metadata in checks.md is not a capability and must not be probed as one.
METADATA_FIELDS = {"platform", "runner", "verified", "shell"}

# Leading shell noise to strip before finding the executable.
PREFIX_RE = re.compile(r"^\s*(?:cd\s+\S+\s*&&\s*)+")


def executable_of(cmd: str) -> str | None:
    """The first real executable token of a declared command."""
    stripped = PREFIX_RE.sub("", cmd).strip()
    token = stripped.split()[0] if stripped.split() else ""
    if not token or token in {"(", "{"}:
        return None
    return token


def probe(cmd: str, repo: Path, shell: str) -> tuple[bool, str]:
    """Can this command run here? Resolve the executable; never run the real workload."""
    exe = executable_of(cmd)
    if exe is None:
        return False, "could not parse a command"

    # A path-like executable is checked on disk; a bare name goes through PATH.
    if "/" in exe or "\\" in exe:
        target = (repo / exe) if not Path(exe).is_absolute() else Path(exe)
        if target.is_file():
            return True, f"{exe} present"
        return False, f"{exe} not found on disk"

    if shutil.which(exe):
        return True, f"{exe} on PATH"

    # Not on PATH directly - it may still be a shell builtin or an alias inside the POSIX shell.
    rc, out = run_cmd(f"command -v {exe}", repo, timeout=20, shell=shell)
    if rc == 0 and out.strip():
        return True, f"{exe} resolved by shell"
    return False, f"{exe} not installed"




def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow environment doctor")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--flow")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = Path(args.flow) if args.flow else flow_root(repo)
    rep = Report("hx-doctor - environment vs. checks.md")
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2

    checks_path = root / "checks.md"
    if not checks_path.is_file():
        rep.fail("checks.md", "missing - /hx:map must run first")
        return rep.emit(args.json)

    shell = checks_shell(root)
    bash = bash_path()
    if bash:
        rep.ok("POSIX shell", f"{bash} (checks.md shell: {shell})")
    elif shell == "bash":
        rep.fail("POSIX shell",
                 "checks.md requests shell: bash but no POSIX shell exists - install Git Bash")
    else:
        rep.add("WARN", "POSIX shell",
                "none found; declared commands using POSIX syntax will misbehave")

    # The declared runner, if any, must actually exist.
    from hx_common import front_fields
    runner_field = front_fields(checks_path.read_text(encoding="utf-8")).get("runner", "")
    runner = runner_field.split()[0].strip().lower() if runner_field else ""
    if runner and runner not in {"none", "-"}:
        if shutil.which(runner):
            rep.ok("declared runner", f"{runner} available")
        else:
            rep.add("WARN", "declared runner",
                    f"{runner} declared but not installed - checks.md must hold the "
                    "underlying commands instead")

    blocks = parse_checks(checks_path.read_text(encoding="utf-8"))
    total = 0
    for scope, caps in sorted(blocks.items()):
        label = "security" if scope == "security" else scope
        for cap, cmd in sorted(caps.items()):
            if scope == "_global" and cap in METADATA_FIELDS:
                continue  # metadata, not a capability
            # A `doctor:` entry is a cheap readiness probe declared by the target repo. Resolving
            # an executable is not enough: `npm` on PATH says nothing about node_modules existing,
            # and "dependencies not installed" is the most common gap on a fresh clone.
            if cap == "doctor":
                rc, out = run_cmd(cmd, repo, timeout=60, shell=shell)
                total += 1
                if rc == 0:
                    rep.ok(f"{label} readiness", "scope ready")
                else:
                    rep.fail(f"{label} readiness",
                             f"exit {rc} - {tail(out) or 'scope not set up'}")
                continue
            total += 1
            ok, detail = probe(cmd, repo, shell)
            name = f"{label} {cap}"
            if ok and cap == "secret-scan":
                # Resolving the executable is not enough for a security gate: it must be shown
                # to actually detect something. See canary_secret_scan.
                rep.ok(name, detail)
                status, why = canary_secret_scan(cmd, repo, shell)
                rep.add(status, "secret-scan effectiveness", why)
            elif ok:
                rep.ok(name, detail)
            elif cap in CRITICAL:
                rep.fail(name, f"{detail} - blocks {BLOCKS.get(cap, 'ship')}")
            else:
                rep.add("WARN", name, f"{detail} - blocks {BLOCKS.get(cap, 'unknown phase')}")

    if total == 0:
        rep.fail("capabilities", "checks.md declares none - /hx:map must be re-run")

    # Capabilities deliberately left empty are a gap too: they are recorded, not solved.
    declared = {cap for scope, caps in blocks.items() for cap in caps}
    for cap in ("lint", "test-all"):
        if cap not in declared:
            rep.add("WARN", f"missing capability: {cap}",
                    f"not declared in any scope - blocks {BLOCKS.get(cap, 'unknown')}")
    if "audit-block" not in declared:
        rep.fail("missing capability: audit-block",
                 "no security gate declared - ship is permanently blocked")

    code = rep.emit(args.json)
    if not args.json:
        crit = [i for i in rep.failures]
        print("\nEvery FAIL blocks a phase on this machine. WARN entries degrade a phase but let "
              "you work." if crit else "\nThis machine satisfies every declared capability.")
    return code


if __name__ == "__main__":
    sys.exit(main())
