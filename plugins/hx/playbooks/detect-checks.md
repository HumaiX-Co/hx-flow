# Detection ladder — how to find the command set

`/hx:map` reads this. **This file contains no language-specific command**, only where to look.
Stack knowledge is written into the target repo's `.flow/checks.md`, which is what keeps the
plugin's size independent of how many languages it supports.

**Try each step in order and stop at the first one that succeeds.**

---

## Step 1 — If a task runner exists, READ it; do not guess

The project has already declared its own commands. Look for:

`justfile` · `Justfile` · `Makefile` · `Taskfile.yml` · `package.json` (scripts) · `nx.json` ·
`moon.yml` · `mise.toml` · `Rakefile` · `magefile.go` · `noxfile.py` · `tox.ini` · `build.cake`

Read the target names and map them to capabilities. Names can mislead — a target called `test`
sometimes also runs end-to-end tests. When in doubt, read the target's body.

## Step 2 — CI files are GROUND TRUTH

`.github/workflows/*.yml` · `.gitlab-ci.yml` · `azure-pipelines.yml` · `.circleci/config.yml` ·
`Jenkinsfile` · `.drone.yml`

What is written here is what **must pass**. If it contradicts step 1, **CI wins**. A CI pipeline's
lint and test jobs are the most reliable source for the `lint` and `test-all` capabilities.

## Step 3 — Infer from the manifest

With no runner and no CI, the package manifest tells you which ecosystem you are in. The file
names live in `${CLAUDE_PLUGIN_ROOT}/data/manifests.json`. **Read** the manifest — script and
target definitions are usually inside it.

Adding a new ecosystem means adding one line to `manifests.json`. No code is added for it.

## Step 4 — Ask the human, ONCE

If it is still ambiguous, ask via `AskUserQuestion` and **write the answer into `checks.md`**.
The same question is never asked twice — this is the part of the tool that learns.

---

## After every step: VERIFY

A declared command is not a working command. Actually run each `lint` and `test-unit` command.

Common breakages:
- A runner target assumes a POSIX shell but the developer is on Windows
- The virtual environment or dependencies are not installed
- The command runs from a subdirectory, not the repository root
- The test command accepts no arguments, which makes slice-level targeted testing impossible

**Never record a command that does not work.** Find the local equivalent and note it on the
`platform:` line. If no equivalent exists, leave the capability empty and say so in your report —
a wrong command is more harmful than a missing one.

## Capability mapping hints

| capability | what you are looking for | watch out |
|---|---|---|
| `lint` | fast style and format checking | do NOT pick the auto-fixing variant |
| `typecheck` | a separate type checking step | in some ecosystems it is part of `build` |
| `test-unit` | a test command that **accepts arguments** | the `{pattern}` placeholder goes here |
| `test-all` | all fast tests | NOT including end-to-end |
| `e2e` | browser or end-to-end suite | `cost: high`, ship-only |
| `build` | production build | |
| `migration` | schema change generation | the `{msg}` placeholder |

## The `security` block — not optional

`audit-block` is **required**: it must exit **non-zero** when a blocking (critical/high)
vulnerability exists. Most audit tools have a severity threshold flag; use it.
If you cannot define it, ask the user — `ship` refuses to run while this is empty, deliberately.

`audit-count` must print a **number** (for the ratchet).

`secret-scan` must scan the **working tree** and exit non-zero on a finding. Do NOT simply wrap a
`PreToolUse` hook: a hook reads a JSON envelope on stdin, and handed nothing it exits 0 without
looking. The ship gate would then pass forever while protecting nothing. `hx_doctor.py` and the ship
gate both plant a canary secret and require the command to catch it, so an ineffective scanner is
reported rather than trusted.

Two traps when writing one:
- **Self-match.** A scanner that greps for its own pattern definitions will always fail. Exclude
  the scanner file and `checks.md`.
- **Always failing is worse than narrow.** A gate that never passes gets disabled by frustration.
  Tune until the clean repository exits 0, keeping the high-confidence patterns repo-wide.
