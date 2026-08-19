# hx-flow cheatsheet

One screen per section. Everything here is enforced by a script — if the text and a script
disagree, the script is right.

```
     /hx:map  (once per repo)  ->  /hx:doctor  (once per machine)

     /hx:pull <card>     \
                          >-  discuss -> analyze -> research -> plan -> execute -> verify -> ship
     /hx:discuss "idea"  /                                       ^__________|
                                                                 rework, max 2
```

## The commands

| command | runs in | needs | produces |
|---------|---------|-------|----------|
| `/hx:map` | subagent | nothing | `repo-map.md` `checks.md` `ratchet.json` `rules.md` `.gitignore` |
| `/hx:doctor` | main | `checks.md` | a report — can THIS machine run what is declared |
| `/hx:pull <card>` | main | `repo-map.md` + Trello env | `state.md` seed, `phase: discuss` |
| `/hx:discuss "<idea>"` | main, interactive | `repo-map.md` | `state.md` |
| `/hx:analyze [slug]` | subagent | `state.md` | collisions, precedent, coherence |
| `/hx:research [slug]` | subagent, read-only | `state.md` | `findings.md`, ≤15 lines return |
| `/hx:plan [slug]` | main, asks approval | `findings.md` | `plan.md`, slice table |
| `/hx:execute S<n>` | main | `plan.md` | code + slice marked `done` |
| `/hx:verify [slug]` | subagent | `plan.md` | PASS/FAIL table + `verify.json` |
| `/hx:ship [slug]` | main | a fresh passing verify | branch · PR · Trello · archive |
| `/hx:status` | main, reads only | nothing | where you are, one next command |

Slug is optional everywhere: it falls back to `.flow/current`.

## First run in a repository

```
/hx:map                      # detects the command set, verifies it, writes .flow/
git add .flow && git commit  # repo-map, checks, ratchet, rules are TEAM knowledge
```

Anyone who clones afterwards runs `/hx:doctor` — `map` verified the commands on one machine only.

## Per feature

```
/hx:discuss "invoice line splitting"     # or: /hx:pull aB3xYz9
/hx:analyze
/hx:research
/hx:plan                                 # ends by asking for approval
/hx:execute S1                           # one slice per turn, repeat
/hx:execute S2
/hx:verify
/hx:ship
```

Lost? `/hx:status` names the single next command and nothing else.

## What each phase will refuse

| phase | it refuses when | the fix |
|-------|-----------------|---------|
| `discuss` | `Scope OUT` empty, an acceptance criterion is not measurable, >7 criteria | write what will NOT be built; replace "fast"/"works" with a number |
| `analyze` | a sibling feature plans to touch the same file; IN and OUT claim the same subject | a human decision — the route back is `/hx:discuss` |
| `research` | anything outside `.flow/` changed | research reads, it does not write; the change is reverted |
| `plan` | an acceptance criterion maps to no slice; a full-stack slice was not split | split into `S<n>-be` / `S<n>-fe`; add the missing slice |
| `execute` | a `depends` slice is not `done`; a new file matches no allowed pattern | finish the dependency; move the file, or add the rule via `/hx:map` |
| `verify` | a criterion has no command output proving it | mark it FAIL and say what is missing — never "looks good" |
| `ship` | stale verification, vulnerable dependency, empty dependency decision, ratchet rose | re-run `/hx:verify`; fix the finding. There is no override |

## Phase order

| from | legal next |
|------|-----------|
| `discuss` | `analyze` |
| `analyze` | `research`, or back to `discuss` |
| `research` | `plan`, or back to `discuss` |
| `plan` | `execute`, or back to `discuss` |
| `execute` | `verify`, `execute` |
| `verify` | `ship`, `execute` (rework), `discuss` |
| `ship` | `discuss` (next feature) |

Staying in the same phase is always legal. Everything else is refused by `hx_gate.py` — a skipped
phase is not a shortcut, it is a missing artifact.

## The messages that block you

| message | what happened | what to do |
|---------|---------------|------------|
| `transition X -> Y FORBIDDEN` | a phase was skipped | run the phase in between |
| `prerequisite: findings.md missing` | `plan` before `research` | `/hx:research` |
| `prerequisite: repo-map.md missing` | no workspace | `/hx:map` |
| `stale verification` | code changed after verify passed | `/hx:verify` again |
| `verification record missing` | ship without verify | `/hx:verify` |
| `rework rounds 2/2` | two failed verify rounds | the scope is wrong — `/hx:discuss` |
| `a planted secret was NOT detected` | `secret-scan` never looks | fix the command in `checks.md`, not the gate |
| `audit-block is not defined` (ship) | missing config is not safe | declare the audit command in `checks.md` |
| `manifest changed` + empty dependency decision | a new package slipped in undecided | fill `## Dependency decision` in `state.md` |
| `[hx-push-guard] BLOCKED` | `git push` at phase `execute`/`verify` | `/hx:verify` then `/hx:ship` |

## The push guard

`ship` is the only exit, enforced by a `PreToolUse` hook rather than by the model remembering.
`git push` is refused while the active feature is at phase `execute` or `verify`.

It allows everything else: no `.flow/`, no active feature, another phase, `git pull`, a branch
deletion, a non-`Bash` tool call, an unparsable envelope.

Deliberate exception — auditable, stays in git history:

```
git commit -m "wip

HX-Verify-Override: hotfix, verified out of band by <name>"
```

## Workspace

```
.flow/
├─ repo-map.md      # the placement CONTRACT      committed
├─ checks.md        # this repo's command set     committed
├─ ratchet.json     # drift baselines             committed
├─ rules.md         # detectable project rules    committed
├─ features/<slug>/
│   ├─ state.md     # the single source of truth  committed
│   ├─ findings.md  #                             committed
│   ├─ plan.md      #                             committed
│   ├─ verify.json         # your machine's fingerprint   LOCAL
│   └─ verify-report.md    #                              LOCAL
├─ archive/         # shipped features            committed
└─ current          # the feature YOU are on      LOCAL
```

Committing the local ones breaks other developers. `/hx:map` writes the `.gitignore` that prevents it.

## Running a validator by hand

All take `--json` and exit 1 on any FAIL.

```
python <plugin>/scripts/hx_lint.py      --feature <slug>     # or --all
python <plugin>/scripts/hx_gate.py      --feature <slug> --to ship
python <plugin>/scripts/hx_structure.py                      # placement contract
python <plugin>/scripts/hx_ratchet.py   --check              # --baseline, --tighten
python <plugin>/scripts/hx_security.py  --mode ship --feature <slug>   # slice|verify|ship
python <plugin>/scripts/hx_analyze.py   --feature <slug>
python <plugin>/scripts/hx_doctor.py                         # environment vs checks.md
```

`<plugin>` is `${CLAUDE_PLUGIN_ROOT}` inside a skill.

## Trello

Optional, and two mechanisms. Routing table: `playbooks/trello.md`.

| operation | official MCP | script |
|---|---|---|
| read card, list lists, sync checklist, move card | ✅ preferred | fallback |
| comment, attachment, custom field | ❌ not yet | `hx_trello.py` only |

```
# official MCP: connect https://mcp.trello.com/v1 (OAuth) at user or project level
export HX_TRELLO_KEY=...      # trello.com/apps/admin -> Power-Up -> API Key
export HX_TRELLO_TOKEN=...
```

Neither configured means only Trello sync stops; every phase still works. `/hx:pull` caches the
board's list-name to id mapping in `.flow/trello.json`, so later phases spend no lookup on it.
Writes are one-way: flow -> Trello, never back.

## Working on hx-flow itself

```
python tests/run_tests.py        # 68 scenarios — 36 of them expect a refusal
python tests/check_self.py       # body budget ≤40, stack independence, English-only
python tests/check_templates.py  # templates match their schema
```

Write the failing test first. A validator that only ever passes proves nothing.
