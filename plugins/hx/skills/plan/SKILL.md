---
name: plan
description: Splits a feature into independently verifiable slices and produces plan.md. Asks for approval.
disable-model-invocation: true
argument-hint: "[slug]"
effort: high
allowed-tools: Read Write Edit Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

Slug: `$1` (if empty, read the slug from `.flow/current`).

## 1. Gate
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --to plan`
If it FAILs, STOP. There is no planning before research.

## 2. Input — only these
`state.md`, `findings.md`, and the **"Placement rules"** section of `.flow/repo-map.md`.
Do NOT start scanning the codebase again; research already did that. Read nothing else.

## 3. Split into slices
The rule: **one commit · provable by one command · independently revertible.**
- Full-stack work cannot be one slice → split into `S<n>-be` / `S<n>-fe` (different verification
  command, different ratchet metric, different owner).
- A slice that changes the data model needs a migration; mark it on its own row.
- Edge cases and counter-examples: `${CLAUDE_PLUGIN_ROOT}/playbooks/slicing.md`.

## 4. DERIVE the file paths
Each slice's "touches" cell must be derived from repo-map's allowed patterns, not invented.
Record in "Placement check" which rule each slice satisfies.
Write a **capability reference** in the verification column (`test-unit:<pattern>`), never a raw
command, so the plan survives a change of task runner.

## 5. Write and validate
Produce `plan.md` from `${CLAUDE_PLUGIN_ROOT}/templates/plan.md`. Budget 80 lines.
Every acceptance criterion must map to at least one slice. Put expensive checks (`e2e`, `extra`)
under "Pre-ship one-time checks" — never per slice.
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --feature <slug>` — do not proceed until it passes.

## 6. Get approval
Set `phase: plan` in `state.md` and fill the `Slice status` line (`S1 todo | S2 todo`).
Show the slice table to the user and **finish by asking for approval**. Do not start `execute`.
If a Trello card exists, sync the slice table into its checklist —
mechanism: `${CLAUDE_PLUGIN_ROOT}/playbooks/trello.md`.
