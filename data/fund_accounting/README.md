# EagleSTAR fund-accounting drop folder

Drop the US Bank **EagleSTAR** export here — either the Google Takeout `.zip` or a
raw `.mbox`. Drop it **once**; the mbox spans every month in range.

```
data/fund_accounting/takeout-*.zip      # or  export.mbox
```

`nport masters` finds it automatically (newest archive wins) and, in the same pass as
the custodian + AP orders, pre-fills the N-PORT fields the custodian and Bloomberg
cannot supply:

- derivative **`unrealizedAppr`** — PVal `Total Unreal G/L Base` (swaps: the `_R` leg) → security master
- monthly **realized / unrealized gains** — Trial Balance month-end deltas → filing master
- real **balance-sheet liabilities** (`amtPayOneYrOther`) — Trial Balance payable accounts → filing master

The entity→ticker bridge is the NAV `NASDAQ` column. Pre-filled cells stay editable;
`delta` (no feed) keeps your manual entry. It's **optional and additive** — with no
archive here, `masters` behaves exactly as before.

`masters` also writes two **traceability** artifacts to `data/master/`:
`provenance_<period>.csv` (every EagleSTAR cell → source + as-of date) and
`reconciliation_<period>.csv` (the cross-checks — netAssets vs NAV, flows vs the order
book, mapped liabilities vs TB `TOTAL LIABILITIES`, derivative coverage). Review the
reconciliation before flipping `liveTestFlag=LIVE`.

Flags `--fund-accounting PATH` (explicit archive) and `--no-fund-accounting` (skip).

Extraction decodes to a git-ignored build cache (`.cache/`) and is idempotent: a
re-run with the same archive is sub-second.

> **Note (2026-06):** the current export ends **06-24**, so June figures are
> preliminary (as-of 06-24, not the 06-30 month-end). Re-run `masters` when the
> 06-30 export arrives. The archives and `.cache/` are git-ignored — client data
> never enters version control.
