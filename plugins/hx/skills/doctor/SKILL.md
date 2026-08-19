---
name: doctor
description: Checks whether this machine can run what .flow/checks.md declares. Run it after cloning, or when a phase fails for a reason unrelated to the code.
disable-model-invocation: true
allowed-tools: Read Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

`/hx:map` verified the commands once, on the machine that ran it. Anyone who clones the repo
afterwards inherits those commands with no guarantee their machine can run them. This skill closes
that gap. It changes nothing.

## 1. Run the check
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_doctor.py --json`

## 2. Report what is blocked, not what is missing

Translate the output into consequences. The developer cares which phase they cannot run:

| finding | consequence to state |
|---------|----------------------|
| `readiness` FAIL for a scope | that scope's dependencies are not installed; lint, tests and build in it will fail |
| `audit-block` or `secret-scan` FAIL | `/hx:ship` is hard blocked until the tool is installed |
| `lint` / `test-unit` WARN | `/hx:execute` cannot verify a slice in that scope |
| declared runner missing | not fatal; `checks.md` already holds the underlying commands |
| no POSIX shell | declared commands use POSIX syntax and will silently misbehave |

## 3. Give the fix, once
For each FAIL, name the concrete action (install the tool, install dependencies, start the
database). Do not run those actions yourself: they change the developer's environment and some are
slow or need credentials. Offer, then stop.

If everything passes, say so in one line and name the next phase command.

## 4. When checks.md is the problem
If a capability is absent rather than broken, the fix is `/hx:map`, not an install. Say which one
applies — confusing a missing tool with a missing declaration sends the developer down the wrong path.
