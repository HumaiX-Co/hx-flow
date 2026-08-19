---
name: ship
description: Creates the branch, commit and PR; writes back to Trello; archives the feature and delta-updates repo-map. The workflow's only exit.
disable-model-invocation: true
argument-hint: "[slug]"
allowed-tools: Read Write Edit Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*) Bash(git *) Bash(gh pr *)
---

Slug: `$1` (if empty, read the slug from `.flow/current`).

This phase performs **outward-facing actions** (push, PR, Trello). None of them happen until
every gate passes.

## 1. Two gates, both hard
```
python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_gate.py     --feature <slug> --to ship
python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_security.py --mode ship --feature <slug>
```
If either FAILs, **STOP and send nothing.** Report the reason verbatim. There is no shipping with
a vulnerable dependency, a stale verification, or an unrecorded dependency decision.

## 2. Tighten the ratchet
`python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_ratchet.py --check --tighten`
Baselines that fell are lowered permanently — that debt can never come back.

## 3. Branch and commit
- Set `phase: ship` in `state.md` FIRST. The push guard hook reads it; until then push is refused.
- Branch: `feature/<trello-shortLink>-<slug>` (or `feature/<slug>` with no card).
  If you are on the default branch, create the branch FIRST.
- Build the commit message from `state.md`: subject = the one-line intent, body = scope plus
  decisions. If a Trello card exists, add the trailer `Trello: https://trello.com/c/<shortLink>`
- Open the PR with `gh pr create`; build the body from state.md's intent, acceptance criteria
  and scope.

## 4. Write back to Trello (if a card exists)
Mechanism and routing: `${CLAUDE_PLUGIN_ROOT}/playbooks/trello.md`. Attach the PR link, comment
`verify-report.md`, set the `branch` custom field, then move the card. The first three have no MCP
equivalent yet, so they go through the script.
The target list comes from the `.flow/trello.json` mapping. If a human gate is pending (the
"Human gates" table in `rules.md`), move the card to that list instead of Done and say so.

## 5. Close out
- Move `.flow/features/<slug>/` to `.flow/archive/<slug>/`.
- **Delta-update** `.flow/repo-map.md`: any new placement rule, new reference file, new trap.
  Set `last delta`. This step is why the next feature needs less research.
- Delete `.flow/current`.

## 6. Report
Branch, PR link, Trello status, tightened ratchet baselines, pending human gates.
