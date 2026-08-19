---
name: status
description: Shows where you are on one screen - phase, slice status, open questions, next step.
disable-model-invocation: true
allowed-tools: Read Glob
---

Report only. Do not write code, change files, or invoke another phase.

## 1. Read the workspace
- `.flow/current` holds the **slug** of the active feature as plain text, one line, no path.
  If `.flow/` or that file is missing, say so and jump to step 3.
- Read `.flow/features/<slug>/state.md`, plus `verify.json` in the same directory if present.
- Read `.flow/rules.md` only if it exists.

Use the Read tool, not shell commands. A read-only status report must behave identically on every
platform and must not depend on a shell being available.

## 2. Summarise in at most 12 lines

| what | source |
|------|--------|
| feature and phase | the front fields of `state.md` |
| slice status | the `Slice status` line (how many done / how many todo) |
| open questions | the `Open questions` section, with owners |
| pending human gates | the "Human gates" table in `rules.md` |
| verification record | the `result` in `verify.json`, or "none" |

Do not judge verification freshness yourself: `hx_gate.py` owns that comparison. Report the
recorded result and note that `ship` re-checks it against the current code.

## 3. Name the single next command

Phase order: `discuss -> analyze -> research -> plan -> execute -> verify -> ship`.

- no `.flow/` at all -> `/hx:map`
- no active feature -> `/hx:pull <card>` or `/hx:discuss "<idea>"`
- otherwise -> the one command that follows the current phase, and nothing else
