<!-- hx-flow plan template · BUDGET: 80 lines · no prose
     Slice rule: one commit · provable by one command · independently revertible.
     Full-stack work cannot be a single slice → split into S<n>-be / S<n>-fe. -->

# <slug> — plan

## Slice table
<!-- scope: a scope name from checks.md. verification: capability:argument (not a raw command).
     Capabilities: lint typecheck test-unit test-integration e2e build migration -->

| id | goal | scope | touches | verification | depends |
|----|------|-------|---------|--------------|---------|
| S1 | <one sentence> | <scope> | <path> | test-unit:<pattern> | - |
| S2 | <one sentence> | <scope> | <path> | test-unit:<pattern> | S1 |

## Placement check
<!-- Which allowed pattern in repo-map.md does each "touches" path satisfy? -->
| slice | rule satisfied |
|-------|----------------|
| S1 | <repo-map rule name> |

## Slices requiring migration
<!-- Every slice that changes the data model. If none: none -->
<none>

## Acceptance mapping
<!-- Every AC must be covered by at least one slice. An uncovered AC → hx-lint FAIL. -->
| AC | covered by |
|----|------------|
| AC1 | S1 |

## Pre-ship one-time checks
<!-- The expensive ones. NEVER run per slice. -->
- <e2e | build | test-all — whatever is marked cost:high in checks.md>

## Risks
- <risk> → mitigation: <one line>
