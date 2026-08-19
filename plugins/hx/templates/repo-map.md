<!-- hx-flow repo-map template · BUDGET: 120 lines
     THIS IS NOT A MAP, IT IS A CONTRACT. The plan phase derives file paths from it and
     structure-check enforces compliance.
     No language or framework name appears in THIS TEMPLATE — write whatever the target repo uses.
     Produced by /hx:map, delta-updated by /hx:ship. -->

# repo-map
produced: <YYYY-MM-DD>
last delta: <YYYY-MM-DD>

## Scopes
<!-- One row per scope in a monorepo; a single row otherwise.
     Names must MATCH the scope names in checks.md. -->
| scope | what | entry point |
|-------|------|-------------|
| <path/> | <responsibility> | <file> |

## Layers
| layer | location | responsibility |
|-------|----------|----------------|
| | | |

## Placement rules (allowed patterns) — CONTRACT
<!-- "where does a new X go". structure-check glob-matches against these patterns.
     A NEW file outside every pattern = FAIL. Rule names must be unique.
     Pattern syntax: <name> one segment · ** many segments · * within a segment · {a,b} alternatives
     Writing `requires:<glob>` in the "extra requirement" column means: whenever a file matching
     this rule changes, the changeset MUST also contain a file matching <glob>.
     A requires: target must itself be defined as an allowed pattern. -->
| rule name | new what | allowed pattern | extra requirement |
|-----------|----------|-----------------|-------------------|
| | | | |

## Naming
| what | rule | example |
|------|------|---------|
| | | |

## Test placement
| scope | location | naming | how to run |
|-------|----------|--------|------------|
| | | | |

## Reference files (imitate these)
<!-- Which existing file to use as the example when writing new code. At most 8 rows. -->
| for what | path |
|----------|------|
| | |

## Existing agent setup (call these, do not reimplement)
<!-- Skills, agents, commands, hooks already present in the target repo. -->
| what | location | when to use |
|------|----------|-------------|
| | | |

## Known traps
<!-- Platform differences, POSIX-only scripts, dead utilities, misleading names. -->
- <trap>
