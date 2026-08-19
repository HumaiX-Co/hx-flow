#!/usr/bin/env python3
"""hx-gate — enforces phase order and detects stale verification.

The load-bearing part of determinism: "phases cannot be skipped" must not be left to the model,
because the model can forget. This script runs on every phase transition and rejects illegal ones.

Two jobs:
  1. TRANSITION CHECK — is current -> target legal, and do the prerequisite artifacts exist.
  2. STALE VERIFICATION DETECTION — `ship` is only allowed on the exact code that was verified.
     On success, verify records the HEAD sha plus a worktree fingerprint; at ship time both must
     still match, otherwise the verification is stale and ship is refused.

Usage:
    python hx_gate.py --feature <slug> --to plan
    python hx_gate.py --feature <slug> --record-verify --result pass
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from hx_common import Report, flow_root, front_fields, git

PHASES = ["discuss", "analyze", "research", "plan", "execute", "verify", "ship"]

# Legal transitions. Staying in the same phase is always allowed (next slice, more discussion).
ALLOWED: dict[str, set[str]] = {
    "discuss": {"analyze"},
    "analyze": {"research", "discuss"},   # discuss: a collision or scope clash was found
    "research": {"plan", "discuss"},
    "plan": {"execute", "discuss"},            # discuss: scope turned out to be wrong
    "execute": {"verify", "execute"},
    "verify": {"ship", "execute", "discuss"},  # execute: rework round
    "ship": {"discuss"},                       # next feature
}

# Artifacts that must exist before entering a phase.
PREREQ: dict[str, list[str]] = {
    "analyze": ["state.md"],
    "research": ["state.md"],
    "plan": ["state.md", "findings.md"],
    "execute": ["state.md", "plan.md"],
    "verify": ["state.md", "plan.md"],
    "ship": ["state.md", "plan.md"],
}
SHARED_PREREQ: dict[str, list[str]] = {
    "plan": ["repo-map.md", "checks.md"],
    "execute": ["repo-map.md", "checks.md"],
    "verify": ["repo-map.md", "checks.md"],
    "ship": ["repo-map.md", "checks.md"],
}
MAX_REWORK = 2


def fingerprint(repo: Path) -> dict:
    """The code's current identity: HEAD sha plus a worktree fingerprint."""
    sha, rc = git("rev-parse", "HEAD", cwd=repo)
    status, _ = git("status", "--porcelain", "-uall", cwd=repo)
    return {
        "sha": sha if rc == 0 and sha else None,
        "worktree": hashlib.sha256(status.encode("utf-8")).hexdigest()[:16],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="hx-flow phase gate")
    ap.add_argument("--feature", required=True)
    ap.add_argument("--to", choices=PHASES, help="the phase being entered")
    ap.add_argument("--record-verify", action="store_true",
                    help="record the verification result and the code fingerprint")
    ap.add_argument("--result", choices=["pass", "fail"], help="with --record-verify")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--flow")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.to and not args.record_verify:
        print("error: --to or --record-verify is required", file=sys.stderr)
        return 2
    if args.record_verify and not args.result:
        print("error: --record-verify requires --result", file=sys.stderr)
        return 2

    repo = Path(args.repo).resolve()
    root = Path(args.flow) if args.flow else flow_root(repo)
    if root is None:
        print("error: no .flow found. Has /hx:map been run?", file=sys.stderr)
        return 2
    fdir = root / "features" / args.feature
    if not fdir.is_dir():
        print(f"error: no such feature: {fdir}", file=sys.stderr)
        return 2

    verify_file = fdir / "verify.json"

    # --- Record the verification result ---
    if args.record_verify:
        rec = {"result": args.result, **fingerprint(repo)}
        verify_file.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        rep = Report("hx-gate — verification record")
        rep.ok("recorded", f"{args.result} · sha={rec['sha'] or 'none'} · wt={rec['worktree']}")
        return rep.emit(args.json)

    # --- Transition check ---
    target = args.to
    rep = Report(f"hx-gate — transition: -> {target}")

    state = fdir / "state.md"
    if not state.is_file():
        rep.fail("state.md", "missing — no phase transition without a single source of truth")
        return rep.emit(args.json)

    fields = front_fields(state.read_text(encoding="utf-8"))
    current = fields.get("phase", "")
    if current not in PHASES:
        rep.fail("current phase", f"invalid '{current}' — fix state.md")
        return rep.emit(args.json)

    if target == current:
        rep.ok("transition", f"staying in {current}")
    elif target in ALLOWED.get(current, set()):
        rep.ok("transition", f"{current} -> {target} is legal")
    else:
        legal = ", ".join(sorted(ALLOWED.get(current, set()))) or "none"
        rep.fail("transition", f"{current} -> {target} FORBIDDEN. Allowed: {legal}")

    for fname in PREREQ.get(target, []):
        exists = (fdir / fname).is_file()
        (rep.ok if exists else rep.fail)(f"prerequisite: {fname}", "present" if exists else "missing")
    for fname in SHARED_PREREQ.get(target, []):
        exists = (root / fname).is_file()
        (rep.ok if exists else rep.fail)(
            f"prerequisite: {fname}", "present" if exists else "missing — /hx:map required")

    # Rework limit: verify -> execute must not become an endless loop.
    if current == "verify" and target == "execute":
        try:
            turns = int(fields.get("rework", "0") or 0)
        except ValueError:
            turns = 0
        if turns >= MAX_REWORK:
            rep.fail("rework rounds",
                     f"{turns} rounds used — the scope is wrong, return to discuss")
        else:
            rep.ok("rework rounds", f"{turns}/{MAX_REWORK}")

    # --- Stale verification detection (ship only) ---
    if target == "ship":
        if not verify_file.is_file():
            rep.fail("verification record", "missing — ship requires a completed verify")
        else:
            try:
                rec = json.loads(verify_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                rec = {}
            if rec.get("result") != "pass":
                rep.fail("verification result", f"'{rec.get('result')}' — ship requires pass")
            else:
                now = fingerprint(repo)
                if rec.get("sha") != now["sha"]:
                    rep.fail("stale verification",
                             f"verified sha={str(rec.get('sha'))[:8]} but HEAD={str(now['sha'])[:8]}"
                             " — re-run verify")
                elif rec.get("worktree") != now["worktree"]:
                    rep.fail("stale verification",
                             "worktree changed after verification — re-run verify")
                else:
                    rep.ok("verification freshness", f"sha={str(now['sha'])[:8]} matches")

    code = rep.emit(args.json)
    if code and target == "ship" and not args.json:
        print("\nSHIP BLOCKED. The phase gate was not satisfied.")
    return code


if __name__ == "__main__":
    sys.exit(main())
