---
name: map
description: Maps the target repository once and sets up the .flow/ workspace (repo-map, checks, ratchet, rules). Every other phase depends on its output.
disable-model-invocation: true
context: fork
background: false
effort: high
allowed-tools: Read Write Edit Grep Glob Bash
---

Map the target repository and set up the `.flow/` workspace. This runs **once per repository**.
Every later feature reads this output, so a mistake here propagates to all of them. Take your time.

`ultrathink`

## 1. DETECT the command set, do not guess
Read `${CLAUDE_PLUGIN_ROOT}/playbooks/detect-checks.md` and walk the ladder in order.
Stop at the first step that succeeds. If ambiguity remains, ask **once** via `AskUserQuestion`.

## 2. VERIFY every declared command
Actually run each `lint` and `test-unit` command. If it fails (POSIX-only script, missing
virtual environment, platform difference), find the local equivalent and record that instead.
Note it on the `platform:` line. A declared command is not a working command; skipping this
step breaks the tool on first use.

## 3. Produce the files
From the templates in `${CLAUDE_PLUGIN_ROOT}/templates/`, respecting each line budget:
- `.flow/checks.md` — capabilities per scope plus the `security` block. `audit-block` is REQUIRED.
- `.flow/repo-map.md` — the "Placement rules" table is a **contract**: every `requires:<glob>`
  target must itself be defined as an allowed pattern.
- `.flow/ratchet.json` — fill in each metric's `measure` command, then measure baselines:
  `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_ratchet.py --baseline`
- `.flow/rules.md` — only **detectable** rules. If the target repo already has `CLAUDE.md` or
  `AGENTS.md`, do NOT repeat them.
- `.flow/.gitignore` — the sharing model. `repo-map.md`, `checks.md`, `ratchet.json`, `rules.md`,
  `features/` and `archive/` are COMMITTED team knowledge; `current`, `features/*/verify.json` and
  `features/*/verify-report.md` are per-developer and must be ignored. Committing those two breaks other developers.

Set `shell:` in checks.md. Declared commands use POSIX syntax, so `bash` is almost always right;
`platform` runs cmd.exe on Windows where `/dev/null` does not exist and a good command fails
silently. Give every scope a `doctor:` readiness probe as well — resolving an executable proves
nothing about installed dependencies.

## 4. Inventory the existing agent setup
Scan `.claude/skills`, `.claude/agents`, `.claude/commands`, `.claude/hooks`, `AGENTS.md`.
Record what you find in repo-map's "Existing agent setup" table — later phases will **delegate**
to these rather than reimplementing them.

## 5. Validate
Run `python ${CLAUDE_PLUGIN_ROOT}/scripts/hx_lint.py --all`. Fix any FAIL and repeat.

## 6. Report
Return **at most 15 lines** to the main context: detected runner, scopes, rule count, ratchet
baselines, commands that could not be verified, and anything that needs a human answer.
