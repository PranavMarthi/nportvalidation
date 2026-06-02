# SQL Migration Guide

This document describes how to migrate nport's CSV-based holdings storage into a relational database. The split CSV format was designed with this migration in mind — each CSV file maps directly to a SQL table, and `holdingId` becomes the primary/foreign key.

## Current CSV Structure

Each fund filing lives in `filings/<period>/` and consists of up to three CSV files joined by `holdingId`:

```
filings/2025-12/
    holdings.csv            every holding (base fields)
    debt_securities.csv     bonds only (maturity, coupon, rate)
    derivatives.csv         derivatives only (counterparty, swap legs, options)
```

A holding appears in `holdings.csv` always, plus zero or one satellite files depending on its type. The join is 1:1 — each `holdingId` appears at most once per file.

## Schema

### `holdings`

The base table. Every holding gets a row. Columns match the 20 base fields from `holdings.csv`, plus the 5 conditional fields, plus `fund_id` and `period` to scope holdings to a specific filing.

```sql
CREATE TABLE holdings (
    -- Composite key: which fund, which period, which holding
    fund_id         TEXT    NOT NULL,
    period          TEXT    NOT NULL,   -- e.g. '2025-12'
    holding_id      TEXT    NOT NULL,   -- e.g. 'AAPL29', 'SPX-TRS-JPM'

    -- Identifiers
    name            TEXT    NOT NULL,
    lei             TEXT    NOT NULL,   -- 20-char LEI or 'N/A'
    title           TEXT    NOT NULL,
    cusip           TEXT    NOT NULL,   -- 9-char CUSIP, 'N/A', or '000000000'
    isin            TEXT    NOT NULL DEFAULT '',
    ticker          TEXT    NOT NULL DEFAULT '',

    -- Position
    balance         TEXT    NOT NULL,   -- kept as TEXT to preserve exact decimals
    units           TEXT    NOT NULL,   -- NS (shares), PA (par), NC (notional), OU (other)
    cur_cd          TEXT    NOT NULL,   -- ISO 4217
    val_usd         TEXT    NOT NULL,
    pct_val         TEXT    NOT NULL,
    payoff_profile  TEXT    NOT NULL,   -- Long, Short, N/A

    -- Classification
    asset_cat       TEXT    NOT NULL,   -- EC, DBT, DE, STIV, etc.
    issuer_cat      TEXT    NOT NULL,   -- CORP, UST, RF, etc.
    inv_country     TEXT    NOT NULL,   -- ISO 3166-1 alpha-2

    -- Flags
    is_restricted_sec       TEXT NOT NULL,  -- Y/N
    fair_val_level          TEXT NOT NULL,  -- 1, 2, 3, N/A
    is_cash_collateral      TEXT NOT NULL,  -- Y/N
    is_non_cash_collateral  TEXT NOT NULL,  -- Y/N
    is_loan_by_fund         TEXT NOT NULL,  -- Y/N

    -- Conditional (populated only when relevant)
    issuer_conditional_desc TEXT NOT NULL DEFAULT '',
    asset_conditional_desc  TEXT NOT NULL DEFAULT '',
    other_desc              TEXT NOT NULL DEFAULT '',
    other_value             TEXT NOT NULL DEFAULT '',
    exchange_rt             TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (fund_id, period, holding_id)
);
```

### `debt_securities`

One row per bond holding. Only bonds appear here. References `holdings` via composite FK.

```sql
CREATE TABLE debt_securities (
    fund_id                 TEXT NOT NULL,
    period                  TEXT NOT NULL,
    holding_id              TEXT NOT NULL,

    maturity_dt             TEXT NOT NULL,  -- ISO 8601 date
    coupon_kind             TEXT NOT NULL,  -- Fixed, Floating, Variable, None
    annualized_rt           TEXT NOT NULL,  -- decimal as text
    is_default              TEXT NOT NULL,  -- Y/N
    are_intrst_pmnts_in_arrs TEXT NOT NULL, -- Y/N
    is_paid_kind            TEXT NOT NULL,  -- Y/N

    PRIMARY KEY (fund_id, period, holding_id),
    FOREIGN KEY (fund_id, period, holding_id)
        REFERENCES holdings (fund_id, period, holding_id)
);
```

### `derivatives`

One row per derivative holding. Only derivatives appear here. Contains all derivative subtype columns — options, swaps, forwards, and reference instruments — in a single table. Columns that don't apply to a given derivative type are empty strings.

```sql
CREATE TABLE derivatives (
    fund_id             TEXT NOT NULL,
    period              TEXT NOT NULL,
    holding_id          TEXT NOT NULL,

    -- Common (all derivatives)
    deriv_cat           TEXT NOT NULL,  -- FWD, FUT, SWP, OPT, SWO, WAR, OTH
    counterparty_name   TEXT NOT NULL,
    counterparty_lei    TEXT NOT NULL,
    unrealized_appr     TEXT NOT NULL,

    -- Options (OPT, SWO, WAR)
    put_or_call             TEXT NOT NULL DEFAULT '',
    written_or_pur          TEXT NOT NULL DEFAULT '',
    share_no                TEXT NOT NULL DEFAULT '',
    exercise_price          TEXT NOT NULL DEFAULT '',
    exercise_price_cur_cd   TEXT NOT NULL DEFAULT '',
    exp_dt                  TEXT NOT NULL DEFAULT '',
    delta                   TEXT NOT NULL DEFAULT '',

    -- Reference instrument
    ref_inst_type       TEXT NOT NULL DEFAULT '',
    ref_index_name      TEXT NOT NULL DEFAULT '',
    ref_index_identifier TEXT NOT NULL DEFAULT '',
    ref_issuer_name     TEXT NOT NULL DEFAULT '',
    ref_issue_title     TEXT NOT NULL DEFAULT '',
    ref_cusip           TEXT NOT NULL DEFAULT '',
    ref_isin            TEXT NOT NULL DEFAULT '',
    ref_ticker          TEXT NOT NULL DEFAULT '',

    -- Swaps (SWP)
    swap_flag               TEXT NOT NULL DEFAULT '',
    termination_dt          TEXT NOT NULL DEFAULT '',
    upfront_pmnt            TEXT NOT NULL DEFAULT '',
    pmnt_cur_cd             TEXT NOT NULL DEFAULT '',
    upfront_rcpt            TEXT NOT NULL DEFAULT '',
    rcpt_cur_cd             TEXT NOT NULL DEFAULT '',
    notional_amt            TEXT NOT NULL DEFAULT '',
    swap_cur_cd             TEXT NOT NULL DEFAULT '',
    -- Receive leg
    rec_fixed_or_floating   TEXT NOT NULL DEFAULT '',
    rec_fixed_rt            TEXT NOT NULL DEFAULT '',
    rec_floating_rt_index   TEXT NOT NULL DEFAULT '',
    rec_floating_rt_spread  TEXT NOT NULL DEFAULT '',
    rec_pmnt_amt            TEXT NOT NULL DEFAULT '',
    rec_cur_cd              TEXT NOT NULL DEFAULT '',
    rec_rate_tenor          TEXT NOT NULL DEFAULT '',
    rec_rate_unit           TEXT NOT NULL DEFAULT '',
    rec_reset_dt            TEXT NOT NULL DEFAULT '',
    rec_reset_unit          TEXT NOT NULL DEFAULT '',
    rec_desc                TEXT NOT NULL DEFAULT '',
    -- Pay leg
    pmnt_fixed_or_floating  TEXT NOT NULL DEFAULT '',
    pmnt_fixed_rt           TEXT NOT NULL DEFAULT '',
    pmnt_floating_rt_index  TEXT NOT NULL DEFAULT '',
    pmnt_floating_rt_spread TEXT NOT NULL DEFAULT '',
    pmnt_pmnt_amt           TEXT NOT NULL DEFAULT '',
    pmnt_cur_cd_leg         TEXT NOT NULL DEFAULT '',
    pmnt_rate_tenor         TEXT NOT NULL DEFAULT '',
    pmnt_rate_unit          TEXT NOT NULL DEFAULT '',
    pmnt_reset_dt           TEXT NOT NULL DEFAULT '',
    pmnt_reset_unit         TEXT NOT NULL DEFAULT '',

    -- Forwards / Futures (FWD, FUT)
    payoff_prof_deriv   TEXT NOT NULL DEFAULT '',

    -- Other (OTH)
    other_deriv_desc    TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (fund_id, period, holding_id),
    FOREIGN KEY (fund_id, period, holding_id)
        REFERENCES holdings (fund_id, period, holding_id)
);
```

### `fund_configs`

Static fund metadata. One row per fund. Maps from `fund_config.txt`.

```sql
CREATE TABLE fund_configs (
    fund_id             TEXT PRIMARY KEY,
    cik                 TEXT NOT NULL,
    ccc                 TEXT NOT NULL,
    reg_name            TEXT NOT NULL,
    reg_file_number     TEXT NOT NULL,
    reg_cik             TEXT NOT NULL,
    reg_lei             TEXT NOT NULL,
    reg_street1         TEXT NOT NULL,
    reg_street2         TEXT NOT NULL DEFAULT '',
    reg_city            TEXT NOT NULL,
    reg_state           TEXT NOT NULL,
    reg_country         TEXT NOT NULL,
    reg_zip             TEXT NOT NULL,
    reg_phone           TEXT NOT NULL,
    series_name         TEXT NOT NULL,
    series_id           TEXT NOT NULL,
    series_lei          TEXT NOT NULL,
    class_id            TEXT NOT NULL,
    signer_org          TEXT NOT NULL,
    signer_name         TEXT NOT NULL,
    signer_title        TEXT NOT NULL
);
```

### `filings`

Per-period filing data. One row per fund per period. Maps from `filing_data.txt`.

```sql
CREATE TABLE filings (
    fund_id             TEXT NOT NULL,
    period              TEXT NOT NULL,

    submission_type     TEXT NOT NULL,   -- NPORT-P, NPORT-P/A
    live_test_flag      TEXT NOT NULL,   -- LIVE, TEST
    rep_pd_end          TEXT NOT NULL,   -- ISO 8601 date
    rep_pd_date         TEXT NOT NULL,
    is_final_filing     TEXT NOT NULL,   -- Y/N
    date_signed         TEXT NOT NULL,

    -- Financials
    tot_assets          TEXT NOT NULL,
    tot_liabs           TEXT NOT NULL,
    net_assets          TEXT NOT NULL,

    -- Balance sheet
    assets_attr_misc_sec            TEXT NOT NULL,
    assets_invested                 TEXT NOT NULL,
    amt_pay_one_yr_banks_borr       TEXT NOT NULL,
    amt_pay_one_yr_ctrld_comp       TEXT NOT NULL,
    amt_pay_one_yr_oth_affil        TEXT NOT NULL,
    amt_pay_one_yr_other            TEXT NOT NULL,
    amt_pay_aft_one_yr_banks_borr   TEXT NOT NULL,
    amt_pay_aft_one_yr_ctrld_comp   TEXT NOT NULL,
    amt_pay_aft_one_yr_oth_affil    TEXT NOT NULL,
    amt_pay_aft_one_yr_other        TEXT NOT NULL,
    delay_deliv                     TEXT NOT NULL,
    stand_by_commit                 TEXT NOT NULL,
    liquid_pref                     TEXT NOT NULL,
    is_non_cash_collateral          TEXT NOT NULL,

    -- Returns
    rtn1    TEXT NOT NULL,
    rtn2    TEXT NOT NULL,
    rtn3    TEXT NOT NULL,
    net_realized_gain_mon1      TEXT NOT NULL,
    net_unrealized_appr_mon1    TEXT NOT NULL,
    net_realized_gain_mon2      TEXT NOT NULL,
    net_unrealized_appr_mon2    TEXT NOT NULL,
    net_realized_gain_mon3      TEXT NOT NULL,
    net_unrealized_appr_mon3    TEXT NOT NULL,

    -- Flows
    mon1_sales          TEXT NOT NULL,
    mon1_redemption     TEXT NOT NULL,
    mon1_reinvestment   TEXT NOT NULL,
    mon2_sales          TEXT NOT NULL,
    mon2_redemption     TEXT NOT NULL,
    mon2_reinvestment   TEXT NOT NULL,
    mon3_sales          TEXT NOT NULL,
    mon3_redemption     TEXT NOT NULL,
    mon3_reinvestment   TEXT NOT NULL,

    -- Index
    name_designated_index   TEXT NOT NULL,
    index_identifier        TEXT NOT NULL,

    -- Risk metrics (optional, stored as JSON text)
    cur_metrics_json            TEXT NOT NULL DEFAULT '',
    credit_sprd_risk_ig_json    TEXT NOT NULL DEFAULT '',
    credit_sprd_risk_nonig_json TEXT NOT NULL DEFAULT '',

    PRIMARY KEY (fund_id, period),
    FOREIGN KEY (fund_id) REFERENCES fund_configs (fund_id)
);
```

## CSV to SQL Column Mapping

The CSV files use camelCase headers. The SQL tables use snake_case. This table shows the correspondence for each file:

### `holdings.csv` -> `holdings`

| CSV Header | SQL Column | Type | Notes |
|---|---|---|---|
| `holdingId` | `holding_id` | TEXT PK | Part of composite PK |
| `name` | `name` | TEXT | |
| `lei` | `lei` | TEXT | 20-char or `N/A` |
| `title` | `title` | TEXT | |
| `cusip` | `cusip` | TEXT | 9-char, `N/A`, or `000000000` |
| `isin` | `isin` | TEXT | Optional, may be empty |
| `ticker` | `ticker` | TEXT | Optional, may be empty |
| `balance` | `balance` | TEXT | Decimal as text |
| `units` | `units` | TEXT | `NS`, `PA`, `NC`, `OU` |
| `curCd` | `cur_cd` | TEXT | ISO 4217 |
| `valUSD` | `val_usd` | TEXT | Decimal as text |
| `pctVal` | `pct_val` | TEXT | Decimal as text |
| `payoffProfile` | `payoff_profile` | TEXT | `Long`, `Short`, `N/A` |
| `assetCat` | `asset_cat` | TEXT | `EC`, `DBT`, `DE`, `STIV`, etc. |
| `issuerCat` | `issuer_cat` | TEXT | `CORP`, `UST`, `RF`, etc. |
| `invCountry` | `inv_country` | TEXT | ISO 3166-1 alpha-2 |
| `isRestrictedSec` | `is_restricted_sec` | TEXT | `Y`/`N` |
| `fairValLevel` | `fair_val_level` | TEXT | `1`, `2`, `3`, `N/A` |
| `isCashCollateral` | `is_cash_collateral` | TEXT | `Y`/`N` |
| `isNonCashCollateral` | `is_non_cash_collateral` | TEXT | `Y`/`N` |
| `isLoanByFund` | `is_loan_by_fund` | TEXT | `Y`/`N` |
| `otherDesc` | `other_desc` | TEXT | Only if column present |
| `otherValue` | `other_value` | TEXT | Only if column present |
| `issuerConditionalDesc` | `issuer_conditional_desc` | TEXT | Only if column present |
| `assetConditionalDesc` | `asset_conditional_desc` | TEXT | Only if column present |
| `exchangeRt` | `exchange_rt` | TEXT | Only if column present |
| *(none)* | `fund_id` | TEXT PK | Added during import |
| *(none)* | `period` | TEXT PK | Added during import |

### `debt_securities.csv` -> `debt_securities`

| CSV Header | SQL Column | Type |
|---|---|---|
| `holdingId` | `holding_id` | TEXT PK/FK |
| `maturityDt` | `maturity_dt` | TEXT |
| `couponKind` | `coupon_kind` | TEXT |
| `annualizedRt` | `annualized_rt` | TEXT |
| `isDefault` | `is_default` | TEXT |
| `areIntrstPmntsInArrs` | `are_intrst_pmnts_in_arrs` | TEXT |
| `isPaidKind` | `is_paid_kind` | TEXT |

### `derivatives.csv` -> `derivatives`

The columns present in the CSV vary by fund. The SQL table has all possible columns with defaults. Only those present in the CSV are populated during import.

| CSV Header | SQL Column | Subtype |
|---|---|---|
| `holdingId` | `holding_id` | all |
| `derivCat` | `deriv_cat` | all |
| `counterpartyName` | `counterparty_name` | all |
| `counterpartyLei` | `counterparty_lei` | all |
| `unrealizedAppr` | `unrealized_appr` | all |
| `putOrCall` | `put_or_call` | options |
| `writtenOrPur` | `written_or_pur` | options |
| `shareNo` | `share_no` | options |
| `exercisePrice` | `exercise_price` | options |
| `exercisePriceCurCd` | `exercise_price_cur_cd` | options |
| `expDt` | `exp_dt` | options |
| `delta` | `delta` | options |
| `refInstType` | `ref_inst_type` | options/swaps |
| `refIndexName` | `ref_index_name` | options/swaps |
| `refIndexIdentifier` | `ref_index_identifier` | options/swaps |
| `refIssuerName` | `ref_issuer_name` | options/swaps |
| `refIssueTitle` | `ref_issue_title` | options/swaps |
| `refCusip` | `ref_cusip` | options/swaps |
| `refIsin` | `ref_isin` | options/swaps |
| `refTicker` | `ref_ticker` | options/swaps |
| `swapFlag` | `swap_flag` | swaps |
| `terminationDt` | `termination_dt` | swaps |
| `upfrontPmnt` | `upfront_pmnt` | swaps |
| `pmntCurCd` | `pmnt_cur_cd` | swaps |
| `upfrontRcpt` | `upfront_rcpt` | swaps |
| `rcptCurCd` | `rcpt_cur_cd` | swaps |
| `notionalAmt` | `notional_amt` | swaps |
| `swapCurCd` | `swap_cur_cd` | swaps |
| `recFixedOrFloating` | `rec_fixed_or_floating` | swaps |
| `recFixedRt` | `rec_fixed_rt` | swaps |
| `recFloatingRtIndex` | `rec_floating_rt_index` | swaps |
| `recFloatingRtSpread` | `rec_floating_rt_spread` | swaps |
| `recPmntAmt` | `rec_pmnt_amt` | swaps |
| `recCurCd` | `rec_cur_cd` | swaps |
| `recRateTenor` | `rec_rate_tenor` | swaps |
| `recRateUnit` | `rec_rate_unit` | swaps |
| `recResetDt` | `rec_reset_dt` | swaps |
| `recResetUnit` | `rec_reset_unit` | swaps |
| `recDesc` | `rec_desc` | swaps |
| `pmntFixedOrFloating` | `pmnt_fixed_or_floating` | swaps |
| `pmntFixedRt` | `pmnt_fixed_rt` | swaps |
| `pmntFloatingRtIndex` | `pmnt_floating_rt_index` | swaps |
| `pmntFloatingRtSpread` | `pmnt_floating_rt_spread` | swaps |
| `pmntPmntAmt` | `pmnt_pmnt_amt` | swaps |
| `pmntCurCdLeg` | `pmnt_cur_cd_leg` | swaps |
| `pmntRateTenor` | `pmnt_rate_tenor` | swaps |
| `pmntRateUnit` | `pmnt_rate_unit` | swaps |
| `pmntResetDt` | `pmnt_reset_dt` | swaps |
| `pmntResetUnit` | `pmnt_reset_unit` | swaps |
| `payoffProfDeriv` | `payoff_prof_deriv` | forwards |
| `otherDerivDesc` | `other_deriv_desc` | other |

## Import Script

Load one fund's filing period into the database:

```python
import csv
import sqlite3
from pathlib import Path

def import_filing(db: sqlite3.Connection, fund_id: str, period: str, filing_dir: Path):
    """Import a single filing period from split CSVs into the database."""

    # holdings.csv (always present)
    with open(filing_dir / "holdings.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hid = row.pop("holdingId")
            cols = ["fund_id", "period", "holding_id"] + list(row.keys())
            vals = [fund_id, period, hid] + list(row.values())
            placeholders = ", ".join("?" * len(vals))
            col_names = ", ".join(cols)
            db.execute(f"INSERT INTO holdings ({col_names}) VALUES ({placeholders})", vals)

    # debt_securities.csv (optional)
    debt_path = filing_dir / "debt_securities.csv"
    if debt_path.exists():
        with open(debt_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hid = row.pop("holdingId")
                cols = ["fund_id", "period", "holding_id"] + list(row.keys())
                vals = [fund_id, period, hid] + list(row.values())
                placeholders = ", ".join("?" * len(vals))
                col_names = ", ".join(cols)
                db.execute(
                    f"INSERT INTO debt_securities ({col_names}) VALUES ({placeholders})", vals
                )

    # derivatives.csv (optional, variable columns)
    deriv_path = filing_dir / "derivatives.csv"
    if deriv_path.exists():
        with open(deriv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hid = row.pop("holdingId")
                cols = ["fund_id", "period", "holding_id"] + list(row.keys())
                vals = [fund_id, period, hid] + list(row.values())
                placeholders = ", ".join("?" * len(vals))
                col_names = ", ".join(cols)
                db.execute(
                    f"INSERT INTO derivatives ({col_names}) VALUES ({placeholders})", vals
                )

    db.commit()
```

The import script needs the camelCase-to-snake_case column name mapping. The `_HOLDINGS_KEY_MAP` in `config.py` is the source of truth. A production import would use it to translate CSV headers to SQL column names:

```python
from nport.config import _HOLDINGS_KEY_MAP

def csv_to_sql_col(csv_header: str) -> str:
    return _HOLDINGS_KEY_MAP.get(csv_header, csv_header)
```

## Example Queries

### Reconstruct a full holding (equivalent to the in-memory Holding object)

```sql
SELECT
    h.*,
    d.maturity_dt, d.coupon_kind, d.annualized_rt,
    d.is_default, d.are_intrst_pmnts_in_arrs, d.is_paid_kind,
    v.deriv_cat, v.counterparty_name, v.counterparty_lei,
    v.unrealized_appr, v.put_or_call, v.exercise_price,
    v.termination_dt, v.notional_amt
    -- ... (add remaining derivative columns as needed)
FROM holdings h
LEFT JOIN debt_securities d USING (fund_id, period, holding_id)
LEFT JOIN derivatives v USING (fund_id, period, holding_id)
WHERE h.fund_id = 'leveraged_etf'
  AND h.period = '2025-12';
```

This produces one row per holding with NULLs where the satellite row doesn't exist — the same shape as the flat CSV, but constructed on demand.

### All bonds across all funds

```sql
SELECT h.fund_id, h.name, h.val_usd,
       d.maturity_dt, d.coupon_kind, d.annualized_rt
FROM holdings h
JOIN debt_securities d USING (fund_id, period, holding_id)
WHERE h.period = '2025-12'
ORDER BY d.maturity_dt;
```

### Derivative exposure by counterparty

```sql
SELECT v.counterparty_name,
       COUNT(*) AS positions,
       SUM(CAST(v.notional_amt AS REAL)) AS total_notional,
       SUM(CAST(v.unrealized_appr AS REAL)) AS total_pnl
FROM derivatives v
WHERE v.period = '2025-12'
  AND v.deriv_cat = 'SWP'
GROUP BY v.counterparty_name;
```

### Portfolio breakdown by asset type

```sql
SELECT h.fund_id, h.asset_cat,
       COUNT(*) AS count,
       SUM(CAST(h.val_usd AS REAL)) AS total_value,
       SUM(CAST(h.pct_val AS REAL)) AS total_pct
FROM holdings h
WHERE h.period = '2025-12'
GROUP BY h.fund_id, h.asset_cat;
```

### Options expiring within 30 days

```sql
SELECT h.fund_id, h.name,
       v.put_or_call, v.written_or_pur,
       v.exercise_price, v.exp_dt, v.delta
FROM derivatives v
JOIN holdings h USING (fund_id, period, holding_id)
WHERE v.deriv_cat = 'OPT'
  AND v.exp_dt <= DATE('now', '+30 days')
  AND v.exp_dt >= DATE('now');
```

## Data Type Considerations

All values are stored as TEXT in the current system. A future migration could introduce typed columns:

| Current | Typed | Columns |
|---|---|---|
| TEXT | REAL | balance, val_usd, pct_val, annualized_rt, exercise_price, notional_amt, unrealized_appr, delta, exchange_rt |
| TEXT | DATE | maturity_dt, termination_dt, exp_dt, rep_pd_end, date_signed |
| TEXT | BOOLEAN | is_default, is_restricted_sec, is_cash_collateral, is_non_cash_collateral, is_loan_by_fund, are_intrst_pmnts_in_arrs, is_paid_kind (`Y`/`N` -> 1/0) |

The TEXT-everywhere approach is intentional for now: it matches what the SEC XML spec expects (string values), avoids floating-point precision issues with financial amounts, and preserves exact formatting (e.g. `4925000.00` vs `4925000.0`).

## Migration Strategy

### Phase 1: Dual-write (CSV + SQLite)

Keep CSV files as the source of truth. After loading CSVs, also write to a local SQLite database. Use the database for queries and analysis. The CSV files remain the input for XML generation.

```python
# In DataLoader.load_holdings():
holdings = parse_holdings(csv_path)
import_filing(db, fund_id, period, csv_path.parent)  # also write to DB
return holdings
```

### Phase 2: Database as source of truth

Replace `parse_holdings()` with a database reader. The `Holding` dataclass stays the same — only the storage layer changes.

```python
def load_holdings_from_db(db, fund_id, period) -> list[Holding]:
    rows = db.execute("""
        SELECT h.*, d.*, v.*
        FROM holdings h
        LEFT JOIN debt_securities d USING (fund_id, period, holding_id)
        LEFT JOIN derivatives v USING (fund_id, period, holding_id)
        WHERE h.fund_id = ? AND h.period = ?
    """, (fund_id, period)).fetchall()

    return [Holding(**row_to_holding_kwargs(row)) for row in rows]
```

### Phase 3: Drop CSV files

Once the database is stable, CSV files become an export format rather than the primary storage. The `write_split_csv()` function can export from the database for portability or review.

## What Stays the Same

The `Holding` dataclass, `NportBuilder`, `input_validation`, and `NportValidator` are unchanged in all phases. They consume `list[Holding]` and don't know or care whether it came from CSV files, SQLite, or PostgreSQL. The split CSV design isolates the storage layer so that swapping it requires no changes to the XML generation pipeline.
