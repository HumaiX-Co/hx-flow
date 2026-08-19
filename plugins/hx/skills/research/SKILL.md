---
name: research
description: Explores the codebase and produces findings.md. Runs in an isolated subagent so exploration noise never reaches the main context.
disable-model-invocation: true
argument-hint: "[slug]"
context: fork
background: false
allowed-tools: Read Write Grep Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(git status *) Bash(git diff *) Bash(git checkout -- *)
---

Slug: `$1` (if empty, read the slug from `.flow/current`).

This phase runs in an **isolated context**: you may spend tens of thousands of tokens exploring
here, because only a short summary returns to the conversation. So be generous — but **do not
change any code**.

## 1. Gate
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --to research`
If it FAILs, STOP and report why.

## 2. Input
Read only these: `.flow/features/<slug>/state.md`, `.flow/repo-map.md`, `.flow/rules.md`.
The "Reference files" and "Placement rules" sections of repo-map are the most valuable parts.

## 3. Explore
Every row must rest on a **file path or a command output**; never write a guess.
- Files to touch (path + line + why)
- The existing pattern to imitate — this is what prevents structural drift
- Reusable existing code: does this partly exist already?
- Risks (with evidence: file/line) and unknowns

## 4. Write
Produce `.flow/features/<slug>/findings.md` from
`${CLAUDE_PLUGIN_ROOT}/templates/findings.md`. Budget 60 lines, tables required, no prose.
Set `phase: research` in `state.md` and move unknowns into `Open questions`.

## 5. PROVE no code was touched
Run `git status --porcelain -uall`. If anything outside `.flow/` changed, revert it and say so
in your report. Research reads; it does not write.

## 6. Validate and return
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --feature <slug>` — fix any FAIL.
Return **only** the "Summary for main context" section of findings.md (at most 15 lines) plus any
question awaiting an answer. Do not paste the file's contents.
