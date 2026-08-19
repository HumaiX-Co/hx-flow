# Writing acceptance criteria

`/hx:discuss` reads this when needed. `hx-lint` enforces the rule below **mechanically**.

## One rule

> An acceptance criterion must be written so that it is obvious **which command proves it**.

If you cannot imagine the command that proves it, the criterion is unmeasurable and gets rejected.

## Unmeasurable wording (rejected)

`works` · `works properly` · `seamless` · `fast` · `performant` · `nice` · `better` ·
`user friendly` · `clean` · `optimised` · `stable` · `easy` · `robust`

These words are not banned outright — they are accepted when a **measurable trace** sits beside
them. A measurable trace is: a number, a ratio, a comparison operator, a code span (`` `...` ``),
a path or endpoint, an HTTP status code, or a unit (`ms`, `sec`, `rows`, `records`).

## Conversion examples

| ❌ rejected | ✅ accepted |
|---|---|
| Splitting works properly | Split line VAT totals match the original within `0.01` |
| The endpoint is fast | `POST /invoices/{id}/split` p95 latency is under `300 ms` |
| The screen is user friendly | The split dialog is completable by keyboard; `Tab` order covers 4 fields |
| Error handling is good | An invalid ratio returns `HTTP 422` with a `detail` field |
| Translations are done | Missing key count in `messages/de.json` is `0` |
| The code is clean | *(not an acceptance criterion — this is a ratchet metric, it belongs in `rules.md`)* |

That last row matters: code quality is not an acceptance criterion, it is a **drift metric**.
Acceptance criteria describe behaviour; quality is governed by `ratchet.json`. Mixing the two
weakens both.

## The limit of 7

More than 7 criteria means the feature is too large — split it during `discuss`.
This is not a formatting rule: above 7 criteria the `plan` phase cannot map slices accurately and
`verify` loses track of which command proves what.

## Negative criteria are valuable

Some of the best criteria state what must **not** happen:

- The existing `POST /invoices` response schema does not change (contract test passes)
- While the feature flag is `off`, no new endpoint is reachable
- No new raw colour literal is added (the `raw-color-literals` ratchet does not rise)

These are the criteria that catch regressions, and they are usually forgotten. Ask for at least
one during `discuss`.

## Relationship to Scope OUT

If you want to write a criterion for something this feature will not do, it is not a criterion —
it is an `OUT` item. `OUT` cannot be empty; writing down what will not be built is the only cure
for scope creep.
