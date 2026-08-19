---
name: analyze
description: Checks a discussed feature against its siblings, the archive and its own coherence before any research is done. Cheap, and it runs between discuss and research.
disable-model-invocation: true
argument-hint: "[slug]"
context: fork
background: false
allowed-tools: Read Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

Slug: `$1` (if empty, read the slug from `.flow/current`).

Every other check looks at ONE feature in isolation. This one looks outward and backward. Read no
source code: research has not run yet and guessing about the codebase here is worse than silence.

## 1. Gate
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py --feature <slug> --to analyze`

## 2. Mechanical findings
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_analyze.py --feature <slug> --json`

It reports scope coherence, sizing, whether a regression guard exists, collisions with in-flight
features, archive precedent, and unanswered questions. A FAIL means two features plan to touch the
same files, or IN and OUT claim the same subject — both need a human decision, not a workaround.

## 3. Judgement — the part no script can do
Read `state.md` and the state of any feature the script flagged. Then answer, briefly:
- **Ambiguity**: which criterion could two developers implement differently? Name it.
- **Alternatives**: is there a materially cheaper way to satisfy the same criteria? One sentence.
- **Blast radius**: which existing behaviour could regress? This becomes a negative criterion.
- **Hidden dependency**: does this need a decision from someone (data, access, design) not yet
  recorded as an open question?

At most 3 items per heading. This is a filter, not an essay — if nothing is worth saying, say so.

## 4. Write back, do not rewrite
Add what you found to `state.md` as `Open questions` (with an owner) or, when a matter is settled,
as a `Decisions` entry. Add the blast-radius item as a negative acceptance criterion if it fits
under the limit of 7. Do NOT restate intent or scope — `discuss` owns those.
Then `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --feature <slug>` and set `phase: analyze`.

## 5. Route
- collision or scope clash FAIL -> stop, report, the route back is `/hx:discuss`
- otherwise -> `/hx:research`, naming anything research must resolve
