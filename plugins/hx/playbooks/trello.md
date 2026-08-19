# Trello: which mechanism for which operation

Two mechanisms exist and neither one covers the workflow alone. This file decides between them so
the phases do not have to.

## The rule

**Prefer the official MCP for anything it supports. Use `hx_trello.py` for the rest.**

At the start of any phase that touches Trello, check whether Trello MCP tools are present in this
session (tool names matching `mcp__*trello*`). If they are, route the covered operations there.
If they are not, every operation goes through the script — no phase ever fails for the lack of an
MCP server.

## The routing table

| hx operation | phase | official MCP | fallback |
|---|---|---|---|
| read a card (title, description, checklists) | `pull` | yes | `hx_trello.py card get <short>` |
| list the board's lists | `pull` | yes | `hx_trello.py board lists <short>` |
| create/update checklist items from the slice table | `plan` | yes | `hx_trello.py checklist sync <short> <plan.md>` |
| tick one slice off | `execute` | yes | `hx_trello.py checklist check <short> <slice-id>` |
| move the card to another list | `ship` | yes | `hx_trello.py card move <short> <list-name>` |
| **comment** the verification report | `ship` | **no** | `hx_trello.py card comment <short> @<file>` |
| **attach** the PR link | `ship` | **no** | `hx_trello.py card attach <short> <url> [name]` |
| **set a custom field** (branch) | `ship` | **no** | `hx_trello.py field set <short> <field> <value>` |

The last three are not a preference. As of this writing the official server lists comments,
attachments and custom fields under "coming soon", so `ship` cannot be completed through MCP
alone. When they ship, move those rows up and delete nothing else.

## Why the plugin declares no MCP server

hx-flow does not put Trello into its own `.mcp.json`, and this is deliberate:

- **Token cost.** Every connected server's tool schemas are an always-on context cost in every
  session, including the sessions that never touch Trello. The plugin's entire always-on budget is
  smaller than one server's schema set. Whoever wants Trello MCP connects it at the user or project
  level, where they also decide the workspace and the OAuth grant.
- **Availability.** An interactively authenticated server can be absent in a headless or scheduled
  run. A `ship` that depends on it would fail there for a reason unrelated to the code.

So the script is the floor and MCP is the upgrade, never the requirement.

## Rules that hold whichever mechanism is used

- **Writes are one-way**: flow -> Trello. The card is never read back to overwrite `state.md`.
  Two-way sync needs conflict handling and would defeat the purpose of a single source of truth.
- **Reads happen once**, at `pull` time. Later phases do not re-read the card.
- The list-name to id mapping is cached in `.flow/trello.json` by `pull`. Later phases spend no
  lookup on it.
- Trello is never a gate. If credentials are missing or the API is down, say so and continue —
  the workflow's own gates are the ones that block.

## Credentials

The script needs `HX_TRELLO_KEY` and `HX_TRELLO_TOKEN` (a Power-Up at trello.com/apps/admin mints
both). The MCP server uses its own OAuth grant and ignores these. Having one does not configure
the other.
