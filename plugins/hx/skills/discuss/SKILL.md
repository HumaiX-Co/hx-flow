---
name: discuss
description: Clarifies a feature idea and produces state.md. One of the workflow's two entry points.
disable-model-invocation: true
argument-hint: "<idea> | <slug>"
allowed-tools: Read Write Edit Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

Input: `$ARGUMENTS` — either a new idea, or the slug of a feature to continue.

This phase is **interactive** and runs in the main context; human judgement belongs here.
Do not write code and do not search the codebase.

## 1. Setup
If `.flow/repo-map.md` is missing, STOP: "run `/hx:map` first". Otherwise read its "Scopes" section.
For a new feature, derive a slug (kebab-case, short) and copy
`${CLAUDE_PLUGIN_ROOT}/templates/state.md` to `.flow/features/<slug>/state.md`.

## 2. Ask at most 3 questions
Use `AskUserQuestion`, **at most 3 per round**. Too many questions tire the human; too few
produce wrong assumptions. These must be settled:
- **Scope OUT** — what will NOT be built. It cannot be empty; this is the only cure for scope creep.
- **Module decision** — general or customer-specific, feature flag name, default off or on.
- **Acceptance criteria** — at most 7, each **measurable**. "works", "fast", "user friendly"
  are rejected. Writing rules: `${CLAUDE_PLUGIN_ROOT}/playbooks/acceptance.md`.

Anything that cannot be answered goes to `Open questions` with an owner — never invent an answer.

## 3. Dependency decision
If a new package looks likely, settle it now: name, why, why not the alternative, license.
If none is needed, write "no new dependencies". An empty section blocks `ship`.

## 4. Write and validate
Fill in `state.md` (budget 60 lines, no prose), leave `phase: discuss`, set `updated`.
Write the slug into `.flow/current` (plain text, one line, no path).
Then: `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --feature <slug>`
Fix any FAIL and re-run. Do not finish until it passes.

## 5. Finish
Summarise intent, scope and acceptance criteria for the user, then name the next step:
`/hx:analyze`. Do not move on yourself.
