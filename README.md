# hx-flow

A Claude Code plugin for a lightweight, **deterministic** feature workflow.

```
discuss → analyze → research → plan → execute → verify → ship
```

It has two goals:

1. **Lightness.** Heavyweight spec-driven toolkits spend thousands of tokens on their own command
   prompts before you type anything. `claude plugin details hx` reports hx-flow's always-on cost as
   **~491 tokens** across 11 skills; a phase body (~600-1.1k tokens) is paid only when you invoke
   it, and expensive exploration runs isolated in a subagent so its noise never reaches your
   conversation.
2. **Determinism.** Different developers use the same entry and exit points, produce documents in
   the same schema, and cannot drift the codebase structure. Templates are fixed and the checks are
   scripts — a model can forget, a script cannot.

**Language and stack agnostic.** The plugin carries no per-language recipes; it detects the target
repo's command set once and caches it in `.flow/checks.md`. Python, .NET, Go, TypeScript — the same
seven phases.

Day-to-day reference: **[CHEATSHEET.md](CHEATSHEET.md)** — the commands, what each phase refuses,
and what to do about it.

## Status

**v0.4.0 — validated against a real repository.** 11 phase skills, 4 playbooks, 6 templates,
8 scripts, 1 hook. 62 regression scenarios, 3 self-check rules and template/schema consistency
all pass.

The `map` phase has been run against a real multi-language monorepo (Python + Next.js). That run
found three defects, all now fixed and covered by tests: POSIX commands were being run through
`cmd.exe` on Windows and producing FAILs that were not real; `ratchet.json` was never validated, so a
malformed regex escape silently disabled drift control; and resolving an executable was mistaken for
a scope being ready to use. The phases themselves have not yet been driven end to end as an
installed plugin.

### Measured cost

```
$ claude plugin details hx
  Always-on:   ~491 tok   added to every session
  per skill:   ~30-60 always-on, ~580-1.1k on invoke
```

Note: this estimator does not appear to model `disable-model-invocation`, so ~491 is the number to
plan around rather than a floor to argue about. What it does confirm is the shape of the design —
the always-on cost is a rounding error next to a phase body, and phase bodies are opt-in.

```bash
python tests/run_tests.py        # 51 scenarios — half of them expect FAIL
python tests/check_self.py       # body budget, stack independence, English-only
python tests/check_templates.py  # template/schema consistency
```

## Install

```
/plugin marketplace add HumaiX-Co/hx-flow
/plugin install hx@humaix
```

This repository is **private**, so the first command clones over your git credentials: you need
HumaiX-Co membership and an authenticated git (`gh auth login`, or an SSH key on the account). A
developer without org access gets a clone failure, not a permission prompt.

From a local checkout, the CLI works too — note the `./` prefix is required:

```
claude plugin marketplace add ./hx-flow
claude plugin install hx@humaix
```

Skills are enumerated at session start, so a freshly installed plugin becomes available in the
**next** session.

Requires Python 3.9+ on PATH. No package installation — the scripts use only the standard library.

Trello is optional and has two mechanisms. Connect the **official Trello MCP**
(`https://mcp.trello.com/v1`, OAuth) at the user or project level and the phases prefer it for
reading cards, syncing checklists and moving the card. It cannot yet write comments, attachments
or custom fields — the three things `/hx:ship` needs to link a card to its PR — so those go
through `hx_trello.py`, which needs two environment variables:

```bash
export HX_TRELLO_KEY=...     # trello.com/apps/admin -> Power-Up -> API Key
export HX_TRELLO_TOKEN=...
```

The routing table is `playbooks/trello.md`. The plugin deliberately declares no MCP server of its
own: a connected server's tool schemas are an always-on cost in every session, including the ones
that never touch Trello, and an interactively authorised server can be missing from a headless
run. The script is the floor; MCP is the upgrade. Without either, every non-Trello phase still
works.

## How it works

| Phase | Where it runs | Produces |
|-------|---------------|----------|
| `/hx:map` | subagent (once per repo) | `repo-map.md` · `checks.md` · `ratchet.json` · `rules.md` · `.gitignore` |
| `/hx:doctor` | main context | a report: can THIS machine run what checks.md declares |
| `/hx:pull` | main context | a `state.md` seed from a Trello card |
| `/hx:discuss` | main context (interactive) | `state.md` |
| `/hx:analyze` | subagent | collisions, precedent, coherence — before any research |
| `/hx:research` | subagent (read-only) | `findings.md` → a short summary returns |
| `/hx:plan` | main context (asks approval) | `plan.md` |
| `/hx:execute S<n>` | one slice per turn | code + updated `state.md` |
| `/hx:verify` | subagent | a PASS/FAIL table + a verification record |
| `/hx:ship` | main context | branch · PR · Trello write-back · archive · repo-map delta |
| `/hx:status` | main context | one-screen status |

Phases cannot be skipped: each one reads the `phase:` field in `state.md` and refuses if it is out
of turn.

## Workspace (created in the target repo)

```
.flow/
├─ repo-map.md      # the placement CONTRACT — plan derives from it, verify enforces it
├─ checks.md        # this repo's command set (the key to language independence)
├─ ratchet.json     # drift baselines — adding new debt is forbidden
├─ rules.md         # project-specific, detectable rules
├─ features/<slug>/ # state.md · findings.md · plan.md · verify.json
├─ archive/         # after ship
└─ .gitignore       # the sharing model, see below
```

### What is shared and what is local

This distinction is what makes the workflow work for more than one developer:

| committed | why |
|-----------|-----|
| `repo-map.md`, `checks.md`, `ratchet.json`, `rules.md` | team knowledge; the whole point of the tool |
| `features/<slug>/state.md`, `findings.md`, `plan.md` | so a teammate can pick a feature up mid-flight |
| `archive/` | shipped history |

| local only | why |
|------------|-----|
| `current` | which feature *you* are on |
| `features/*/verify.json` | a fingerprint of *your* machine's code state |

`/hx:map` writes the `.gitignore` that enforces this. Committing the local two breaks other
developers.

### Shell selection is not cosmetic

Declared commands in `checks.md` use POSIX syntax. Python's `shell=True` runs `cmd.exe` on Windows,
where `/dev/null` does not exist — a perfectly good command then fails and the tool records a FAIL
that is not real. A wrong result is worse than a crash, so `checks.md` carries an explicit `shell:`
field and the default prefers a POSIX shell (Git Bash on Windows). `/hx:doctor` reports when none
is available.

## Validators

Python 3.9+, **standard library only**. All support `--json` (the skills read that) and exit 1 on
any FAIL.

| script | what it does | on failure |
|--------|--------------|------------|
| `hx_lint.py` | Document schema: required sections, line budgets, measurable acceptance criteria, prose leaks, AC↔slice mapping, full-stack slice splitting, the `checks.md` contract | the phase does not complete |
| `hx_structure.py` | Placement contract: do new files match an allowed pattern, are `requires:` obligations met | structural drift is reported |
| `hx_gate.py` | Phase order plus **stale verification detection** | the transition is refused |
| `hx_ratchet.py` | Drift metrics: increases forbidden, decreases permanently tightened | ship is blocked |
| `hx_security.py` | Vulnerabilities, secrets, SAST, dependency decision | **ship is blocked** |
| `hx_analyze.py` | Cross-feature collisions, archive precedent, scope coherence, sizing | the route back is `discuss` |
| `hx_doctor.py` | Environment vs. `checks.md`: is every declared command runnable here | names the phase each gap blocks |
| `hx_trello.py` | Trello REST wrapper (comments, attachments, checklists, custom fields) | Trello sync stops |

### Cross-feature collision detection

Every other check looks at one feature alone. `analyze` compares a feature against its siblings:
if two in-flight plans intend to touch the same file, it FAILs and names the file and the other
feature. It also searches `archive/` for shipped work with an overlapping scope, so accumulated
knowledge actually gets consulted. This is the one failure mode that scales with team size, and
nothing else in the workflow can see it.

### Stale verification detection

When `verify` passes, the HEAD sha **and a worktree fingerprint** are recorded. `ship` compares
both: if a single line of code changed after verification, ship is refused. You cannot ship changed
code on the strength of "the tests passed earlier".

### The push guard — the one gate that does not need the model

Every check above runs because a phase skill invoked it. That is enough while the model follows
the workflow and worth nothing the moment it does not: a bare `git push` during `execute` sends
unverified code out and no validator ever sees it.

`hooks/hx_push_guard.py` is a `PreToolUse` hook on `Bash`. It refuses `git push` while the active
feature is at phase `execute` or `verify` — `ship` is the workflow's only exit, so the exit itself
is enforced from outside the phases. Exit 2 blocks the tool call and the reason reaches the model.

It is deliberately narrow, because a guard that misfires gets switched off and a switched-off
guard protects nothing. It exits 0 — allows — on all of: no `.flow/`, no active feature, an
unguarded phase, a branch deletion, `git pull`, a non-`Bash` tool call, an unparsable envelope.

The deliberate exception is auditable rather than silent: an `HX-Verify-Override: <reason>`
trailer in a recent commit releases the push and stays in git history.

Note that sha-level staleness stays with `hx_gate.py`, which runs before the ship commit exists.
The hook answers a cruder question: was this code ever taken through the exit at all.

## The security gate

You cannot ship with a vulnerable dependency. Security is not a phase but a **gate**: it runs
between phases and cannot be skipped.

`hx_security.py` is a **policy engine, not a scanner** — the scan commands live in the `security`
block of `.flow/checks.md`, owned by the target repo. That is how every ecosystem's audit tool
works through one engine while the plugin knows none of them.

| severity | policy |
|---|---|
| critical / high | **absolute zero** — `audit-block` exits non-zero → ship impossible |
| moderate / low | **must not rise** — `ratchet.json: vuln-total` |

Three design decisions:

- **Cost:** `audit-block` runs when the **dependency manifest changes**, not on every slice.
- **Missing config is not safe:** in `ship` mode an undefined `audit-block` does not pass silently,
  it FAILs. In `slice` mode it is merely skipped, so a developer is never blocked mid-task.
  Strictness at ship, flexibility while building.
- **A new dependency is a decision:** if a manifest changed, a filled-in `## Dependency decision`
  section in `state.md` is required. Otherwise ship is blocked and the flow returns to `discuss`.

### Hardcoded secrets, and proving the gate is alive

`secret-scan` runs on every slice and again at ship, so a key committed in config or code blocks
the ship. But a secret gate has a failure mode that matters more than a missed pattern: **`exit 0`
means either "nothing found" or "I never looked"**, and the two are indistinguishable. A
`PreToolUse` hook wrapped as a check reads a JSON envelope on stdin; handed nothing it exits 0. A
scanner whose dependency is missing often exits 0 too. Either way the gate passes forever while
protecting nothing.

So the gate proves itself. `hx_doctor.py` and `hx_security.py --mode ship` plant an obviously fake
credential in the working tree, run the declared command, and require it to fail. If the planted
secret is not detected, the report says the gate is not effective as configured instead of showing
a green tick. The planted file is removed in a `finally` block.

This was not hypothetical: the first repository hx-flow was configured against had its
`secret-scan` pointed at a `PreToolUse` hook, and the canary is what exposed that ship would have
passed unconditionally.

## Permission surface

Skills pre-approve tools via `allowed-tools`, and the grant lasts only for the turn that invoked
them. Three phases need broad `Bash` because they run the commands the target repo itself declared
in `.flow/checks.md` — that set cannot be known in advance:

| phase | shell access | why |
|-------|--------------|-----|
| `map`, `execute`, `verify` | full `Bash` | run project-declared lint/test/audit commands |
| `discuss`, `plan`, `pull` | only `python <plugin>/scripts/*` | they call this plugin's own validators |
| `research` | plugin scripts + read-only `git status`/`git diff` | proves it changed no code |
| `ship` | plugin scripts + `git *` + `gh pr *` | branch, commit, PR |
| `status` | none | reads files only |

Review this table before installing the plugin in a repository you care about. A skill checked into
a repository can grant itself tool access, so `allowed-tools` is worth reading in any plugin.

The plugin also registers one hook — `PreToolUse` on `Bash`, `hooks/hx_push_guard.py`. A hook sees
every matching tool call, so it deserves the same scrutiny: this one reads `.flow/` and `git log`,
writes nothing, and its only effect is exit 0 or exit 2.

## Design principles

1. Minimal baseline — ~491 tokens always-on, measured; phase bodies load only when invoked
2. Phase body ≤ 40 lines; detail lives in `playbooks/` and is read only when needed
3. One source of truth: `state.md`
4. Expensive work runs isolated in a subagent
5. No prose, tables required, line budgets enforced
6. Codebase knowledge accumulates; it is not rediscovered per feature
7. Verification is deterministic — the model cannot say "looks good"
8. No language or framework name in an executed command

## Contributing

This repository has to stay lighter than what it replaces. `tests/check_self.py` enforces three
rules on Linux and Windows in CI:

- **Phase body ≤ 40 lines.** Detail moves into `playbooks/` and is read only when needed.
- **No stack-specific tool name in an executed command.** Stack knowledge belongs in the target
  repo's `.flow/checks.md`. Tool names may appear as explanation, never inside a command that runs.
  Exempt: `git`, `gh` (the git host decision), `python` (the scripts' own language).
- **English-only.** Skill bodies and descriptions are prompts the model reads, and this plugin is
  meant to outlive one team — it may be published, and a prompt written in one team's language is
  one the next maintainer cannot review. Vocabulary specific to your team's language belongs in
  `data/criteria-language.json`, never in code. Typographic symbols are allowed; letters are not.

When adding a capability, write its test first — especially the test that expects **FAIL**.
A validator that only ever passes proves nothing.

## License

MIT
