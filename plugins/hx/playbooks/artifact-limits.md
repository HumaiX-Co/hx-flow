# Artifact budgets and trimming

`hx-lint` enforces these numbers. When a budget is exceeded, the content is **trimmed** — the
budget is not raised.

## Budgets (meaningful lines; comments and blanks do not count)

| file | budget | why this number |
|---|---|---|
| `state.md` | 60 | Read at the start of every phase. This file *is* the cost of carrying state between phases. |
| `findings.md` | 60 | Only a short summary returns to the main context; the rest stays in the fork. |
| `plan.md` | 80 | Slice table plus mappings. Exceeding 80 means the feature is too large. |
| `repo-map.md` | 120 | Read for every feature and lives for the repository's lifetime. |
| `checks.md` | 25 | Command mapping only. If it grows, the scopes are cut wrong. |
| `rules.md` | 30 | Only detectable rules. |

## Trimming order

When a budget is exceeded, cut in this order, top down:

1. **Prose.** Delete paragraphs where a table or list is expected; move the information into the table.
2. **Repetition.** If the same thing appears in two sections, delete one. Duplication between
   `state.md` and `plan.md` is the most common instance.
3. **Rationale.** "Why" collapses to one line. There is no two-line rationale.
4. **Examples.** Delete the example rows left over from the template.
5. **Scope.** If it still does not fit, the excess is not content but **feature**: return to
   `discuss` and split it in two.

That last step matters: a budget is not a formatting rule, it is a **scope signal**. A feature whose
plan does not fit in 80 lines is not one feature.

## The prose ban

These sections may contain prose: `state.md > Intent` (at most 3 lines) and
`findings.md > Summary for main context`. Every other section is a table or a list.

The `hx-lint` rule: three or more consecutive plain-text lines in a section is a prose leak.
Table rows, bullets, numbered lists, fenced code and `key: value` lines all count as structural.

## Why this is strict

Heavyweight spec-driven toolkits spend a large fixed budget on their own command prompts, and the
artifacts they generate are re-read on every phase. The compounding effect is what makes a single
feature consume most of a context window. hx-flow's whole advantage comes from one thing: the line
budgets being respected.

Raising a budget is easy in the short term and turns the tool into the thing it replaced.
Changing a budget is a design decision and is made in the `SPEC` dictionary of `hx_lint.py`,
together with its rationale.
