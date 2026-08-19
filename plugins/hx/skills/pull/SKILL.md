---
name: pull
description: Seeds a feature from a Trello card (title, description, checklist -> state.md). One of the workflow's two entry points.
disable-model-invocation: true
argument-hint: "<card-url or shortLink>"
allowed-tools: Read Write Edit Glob Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)
---

Input: `$1` — a Trello card URL (`https://trello.com/c/aB3xYz9/...`) or a shortLink (`aB3xYz9`).

Given a URL, extract the shortLink between `/c/` and the next `/`.

## 1. Preconditions
If `.flow/repo-map.md` is missing, STOP: "run `/hx:map` first".
If this session has no Trello MCP tools AND `HX_TRELLO_KEY` / `HX_TRELLO_TOKEN` are unset, STOP:
either connect the official Trello MCP, or mint a key and token from a Power-Up at
trello.com/apps/admin.

## 2. Read the card
Which mechanism to use: `${CLAUDE_PLUGIN_ROOT}/playbooks/trello.md`. Read the card, then the
board's lists — the list-name to id mapping is cached in `.flow/trello.json`, so later phases
spend no lookup on it.

## 3. Seed
Derive the slug from the card title (kebab-case, short). Copy
`${CLAUDE_PLUGIN_ROOT}/templates/state.md` to `.flow/features/<slug>/state.md` and fill in
**only what the card actually says**:
- card title → `Intent` (at most 3 lines)
- card description → candidate `Scope IN` items
- checklist items → **candidate** acceptance criteria (they may not be measurable yet)
- `trello: <shortLink>`

**Do not invent the gaps.** Anything the card does not say becomes an entry under
`Open questions`. Trello cards are usually incomplete; completing them is `discuss`'s job, not this
phase's.

## 4. Hand off
Leave `phase: discuss` and write the slug into `.flow/current` (plain text, one line, no path).
Show the user what the card provided and what is still missing, then suggest `/hx:discuss`.
Do not run `hx_lint` — state.md is deliberately still incomplete at this point.
