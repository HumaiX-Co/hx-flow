<!-- hx-flow state template · BUDGET: 60 lines · no prose, tables and lists only
     Section headings are FIXED. Do not remove, add, or rename them — hx-lint rejects that. -->

# <slug>

phase: discuss        # discuss|analyze|research|plan|execute|verify|ship
trello: <shortLink>   # or: none
branch: <none|feature/...>
updated: <YYYY-MM-DD>

## Intent
<!-- At most 3 lines. What we are building, for whom, why now. -->

## Scope
IN:  <comma-separated, at most 5 items>
OUT: <comma-separated, at most 5 items — OUT must not be empty>

## Module decision
<!-- Customer-specific work enters upstream as a generally available, default-off module. -->
type: <general|customer-specific>
feature-flag: <flag name|none>
default: <off|on>

## Dependency decision
<!-- If NO new package is added, write "no new dependencies".
     Otherwise, for each: name, why, why not the alternative, license, maintenance status.
     hx-security blocks ship if a manifest changed and this section is empty. -->
no new dependencies

## Acceptance criteria
<!-- At most 7. Each must be MEASURABLE. "works", "fast", "user friendly" → hx-lint FAIL. -->
- [ ] AC1 <measurable statement>
- [ ] AC2 <measurable statement>

## Decisions
<!-- Every irreversible or debated choice. Rationale on one line. -->
- D1 <decision> — rationale: <one line>

## Open questions
<!-- Once answered, move to Decisions and delete from here. -->
- Q1 <question> → owner: <name>

## Slice status
<!-- Filled by the plan phase. States: todo|doing|done|blocked -->
<no plan yet>
