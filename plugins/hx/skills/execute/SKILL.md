---
name: execute
description: Implements and verifies a single slice. One slice per turn; never strays outside the plan.
disable-model-invocation: true
argument-hint: "<slice-id> [slug]"
allowed-tools: Read Write Edit Grep Glob Bash
---

Slice: `$1` · Slug: `$2` (if empty, read the slug from `.flow/current`). If no slice id is given, take the first
`todo` slice from `Slice status` and say which one you picked.

**One slice per turn.** Never combine slices — that destroys verifiability.

## 1. Gate
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --to execute`
If it FAILs, STOP. Also stop if any slice listed in this slice's `depends` column is not `done`.

## 2. Input — keep it narrow
Only this slice's row from `plan.md`, only the files findings.md lists for it, and the relevant
`scope` block of `.flow/checks.md`. You do not need the whole plan or all findings.

## 3. Implement
- Imitate the file marked as "Pattern to follow" in `findings.md`.
- Touch only the paths in this slice's "touches" cell. Anything more is scope creep.
- In a frontend slice, never use a raw colour literal — use the project's semantic design tokens.
  If a new colour seems necessary, STOP: that is a design decision and returns to `discuss`.
- If the target repo already has a skill for this work, **call it** instead of reimplementing
  (see repo-map's "Existing agent setup" table).

## 4. Verify — all three
Use this scope's commands from `checks.md`:
1. `lint` and this slice's verification capability (`test-unit:<pattern>`)
2. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_structure.py` — the placement contract
3. `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_security.py --mode slice --feature <slug>`

Do NOT run the expensive checks (`e2e`, `extra`) — those belong before ship.
Fix any FAIL and repeat; never mark the slice `done` before everything passes.

## 5. State and Trello
Mark this slice `done` in `state.md` and set `updated`. Touch no other field.
If a Trello card exists, tick this slice off — see `${CLAUDE_PLUGIN_ROOT}/playbooks/trello.md`.
Say whether `todo` slices remain; if none, suggest `/hx:verify`.
