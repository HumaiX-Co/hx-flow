---
name: verify
description: Verifies a feature deterministically and produces a PASS/FAIL table. Records the result against the exact code that was checked.
disable-model-invocation: true
argument-hint: "[slug]"
context: fork
background: false
allowed-tools: Read Write Edit Grep Glob Bash
---

Slug: `$1` (if empty, read the slug from `.flow/current`).

This phase is **deterministic**. You may not say "looks good" — every row rests on a command's
output. Do not fix code here; report findings, fixing is `execute`'s job.

## 1. Gate
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --to verify`

## 2. Run every check
Using the relevant scopes' commands from `.flow/checks.md`, in this order:
1. `lint` · `typecheck` (if present) · `test-all`
2. The expensive, once-before-ship ones: `e2e`, `extra`.
   If the frontend was touched, make sure **both light and dark** states are covered.
3. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_structure.py`
4. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_ratchet.py --check`
5. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --feature <slug>`
6. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_security.py --mode verify --feature <slug>`

## 3. Map the acceptance criteria
For each criterion in `state.md`: which command output **proves** it?
A criterion without proof cannot be PASS — mark it FAIL and say what is missing.

## 4. Record the result
If everything passed:
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --record-verify --result pass`
Otherwise use `--result fail`.

This record stores the HEAD sha and a worktree fingerprint; `ship` compares both and refuses a
**stale verification**. In other words, one line of code changed after verify blocks ship.

## 5. State and report
On FAIL, increment the `rework` counter in `state.md` (write `1` if absent) — after 2 rounds the
gate closes the route back to `execute` and the scope returns to `discuss`.
Write the PASS/FAIL table to `.flow/features/<slug>/verify-report.md` so `ship` can post it
without re-running anything. It is local like `verify.json`, not shared.
If a Trello card exists, post it as a card comment — there is no MCP equivalent yet, so use
`hx_trello.py card comment <shortLink> @.flow/features/<slug>/verify-report.md`

Return the **PASS/FAIL table** to the main context (at most 20 lines) — never paste command output.
