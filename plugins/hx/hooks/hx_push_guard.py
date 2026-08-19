#!/usr/bin/env python3
"""hx-push-guard - a PreToolUse hook that refuses `git push` while a feature is mid-flight.

WHY A HOOK AND NOT ANOTHER CHECK. Every other gate in hx-flow runs because a phase skill invoked
it. That is sufficient while the model follows the workflow and worth exactly nothing the moment
it does not: a bare `git push` during `execute` sends unverified code out and no validator ever
sees it. `ship` is the workflow's only exit, so the exit itself has to be enforced from outside
the phases.

CONTRACT (Claude Code hook protocol):
    stdin  - a JSON envelope: {tool_name, tool_input, cwd}
    exit 0 - allow the tool call
    exit 2 - block it; stderr is shown to the model

Every unexpected condition exits 0: no envelope, no `.flow/`, no active feature, unreadable
state. A guard that misfires gets switched off, and a switched-off guard protects nothing.

Escape hatch: an `HX-Verify-Override: <reason>` trailer in a recent commit. It stays in git
history, which is the entire point - skipping verification should be visible afterwards rather
than silent.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from hx_common import flow_root, front_fields, git  # noqa: E402

# Phases at which code exists but has not been shipped through the gates.
GUARDED_PHASES = {"execute", "verify"}

# Match `git push` as a command, not as a substring: "git pull", "git push --help" in a comment
# and "git log --grep push" must all pass through untouched.
PUSH_RE = re.compile(r"(?:^|[^\w-])git\s+(?:-[^\s]+\s+)*push(?:\s|$)")
# Deleting a remote branch carries no code.
DELETE_RE = re.compile(r"git\s+push[^|;&]*(?:\s--delete\b|\s:[^\s]+)")
OVERRIDE_RE = re.compile(r"^HX-Verify-Override:\s*(.{10,})$", re.M)


def allow() -> int:
    return 0


def block(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def has_override(repo: Path) -> bool:
    """An explicit, auditable waiver in a recent commit body."""
    out, rc = git("log", "--format=%B", "-n", "3", cwd=repo)
    return rc == 0 and bool(OVERRIDE_RE.search(out))


def main() -> int:
    if sys.stdin.isatty():  # invoked by hand rather than by the harness
        return allow()
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (json.JSONDecodeError, ValueError):
        return allow()
    if not isinstance(data, dict) or data.get("tool_name") != "Bash":
        return allow()

    command = (data.get("tool_input") or {}).get("command") or ""
    if not PUSH_RE.search(command) or DELETE_RE.search(command):
        return allow()

    repo = Path(data.get("cwd") or ".").resolve()
    root = flow_root(repo)
    if root is None:                       # not an hx-flow repository
        return allow()
    current = root / "current"
    if not current.is_file():              # no feature in flight
        return allow()

    lines = [ln.strip() for ln in current.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return allow()
    slug = lines[0]
    state = root / "features" / slug / "state.md"
    if not state.is_file():
        return allow()

    try:
        phase = front_fields(state.read_text(encoding="utf-8")).get("phase", "")
    except OSError:
        return allow()
    if phase not in GUARDED_PHASES:
        return allow()
    if has_override(repo):
        return allow()

    return block(
        f"[hx-push-guard] BLOCKED. Feature '{slug}' is at phase '{phase}'.\n"
        "ship is this workflow's only exit; pushing here sends code out that no gate has seen "
        "(security, ratchet and stale-verification checks all run inside /hx:ship).\n"
        "  Next:      /hx:verify   then   /hx:ship\n"
        "  Deliberate exception: commit with an 'HX-Verify-Override: <reason>' trailer, then "
        "push. The waiver stays in git history."
    )


if __name__ == "__main__":
    sys.exit(main())
