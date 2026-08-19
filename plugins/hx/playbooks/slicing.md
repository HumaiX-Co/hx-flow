# Cutting slices — rules and counter-examples

`/hx:plan` reads this when needed.

## Definition

A slice satisfies all three of these at once:

1. **One commit** — a meaningful change that can be explained on its own
2. **Provable by one command** — one capability from `checks.md` plus an argument is enough
3. **Independently revertible** — reverting it leaves the system consistent

If any of the three fails, the slice is cut wrong.

## Hard rules

| rule | why |
|---|---|
| Full-stack work is **split in two** (`S<n>-be` / `S<n>-fe`) | different verification command, ratchet metric and owner |
| A slice requiring a migration is **separate** | different revert order; schema and code do not share a commit |
| A slice adding a dependency is **separate** | the security gate and the dependency decision hang off it |
| Work needing a new design token **cannot be a slice** | it is a design decision and returns to `discuss` |
| A slice touches **one scope** | `checks.md` commands are per scope |

## Counter-examples

**Too large — must be split**
```
| S1 | Invoice splitting feature | backend/ frontend/ | test-all | - |
```
Not provable by one command, touches two scopes, and it is unclear what reverting it would mean.

**Too small — must be merged**
```
| S1 | add a split field to InvoiceLine | backend/ | - | - |
| S2 | give the split field a type       | backend/ | - | - |
```
Produces no independently verifiable behaviour, which is why the verification column ends up empty.
An empty verification column is always the sign of a badly cut slice.

**Cut horizontally — should be vertical**
```
| S1 | all models    | ... |
| S2 | all services  | ... |
| S3 | all endpoints |     |
```
Advancing layer by layer satisfies no acceptance criterion until S3. Each slice must make **one
behaviour** work end to end within its own scope.

**Correct**
```
| S1    | InvoiceLine.split() with proportional VAT | backend/  | backend/billing/models.py | test-unit:split_vat   | -     |
| S2-be | POST /invoices/{id}/split endpoint        | backend/  | backend/billing/router.py | test-unit:split_api   | S1    |
| S2-fe | split dialog                             | frontend/ | frontend/components/billing/SplitDialog.tsx | test-unit:SplitDialog | S2-be |
```

## Dependencies and parallelism

Slices with an empty `depends` column can run in parallel — **as long as they do not touch the
same file.** Slices touching the same file must run serially even when no dependency was declared.
Detect this during planning and record it as a dependency; do not leave the conflict to execute.

## Acceptance mapping

Every acceptance criterion must map to at least one slice. A criterion that maps to none is either
out of scope (move it to `OUT`) or reveals a missing slice. `hx-lint` enforces this and it cannot
be left empty.

One slice may satisfy several criteria. But if a criterion is satisfied by **no** slice, the plan
is incomplete.

## Ordering

Order slices so that risk is taken first: the most uncertain slice, the one carrying the most
assumptions, goes **first**. That way a wrong plan is discovered early. Front-loading the easy work
feels like progress but saves the real risk for last.
