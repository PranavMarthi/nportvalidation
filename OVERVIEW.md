# N-PORT Filing — How To Do It

This is your start-to-finish playbook. Read §1–§4 to file. Everything below that is reference.

**What this tool does:** turns the monthly US Bank positions CSV + a little fund metadata into a valid SEC N-PORT XML, ready to upload to EDGAR.

---

## 1. One-time setup

```bash
cd /Users/Marthi/Documents/nport
uv sync                      # install dependencies
source .venv/bin/activate    # so you can type `nport ...` instead of `uv run nport ...`
nport guide                  # prints this checklist anytime
```

(If you skip `source .venv/bin/activate`, just put `uv run` in front of every `nport` command.)

Each fund lives in `data/funds/<ticker>/`. A fund is ready to file once it has **both** of these:
- `fund_config.txt` — the fund's identity (CIK, name, address, signer). Set once; rarely changes.
- `security_master.csv` — reference data for each security it holds.

> Most fund folders today only have `security_master.csv`. Those funds can't be filed until you add a `fund_config.txt` (copy one from `data/funds/fdrs/fund_config.txt` and edit the values).

---

## 2. The monthly process (5 steps)

> All commands assume you've run `source .venv/bin/activate`. The period (`2026-06`) is optional — if you leave it off, the tool uses the newest custodian file automatically.

### Step 1 — Drop in the custodian CSV

Download the monthly positions file from **US Bank** and save it exactly as:

```
data/custodian/2026-06_holdings.csv
```

The `2026-06` part is the reporting month. Every command below finds this file on its own — you never type the path.

### Step 2 — Update the security masters

```bash
nport masters 2026-06
```

This scans the custodian file, adds any **new** securities to each fund's `security_master.csv`, removes ones no longer held, and **keeps everything you typed in by hand** last time. Run `nport masters 2026-06 --dry-run` first if you want to preview the adds/removes.

Now you fill in the blanks for new derivatives → **this is the Bloomberg step, see §3.**

### Step 3 — Create this month's filing templates

```bash
nport filing 2026-06
```

This creates `data/funds/<ticker>/filings/2026-06/filing_data.txt` for each fund (copied from last month with dates bumped and returns/flows zeroed). Open each one and fill in the numbers **from fund accounting** (see §3, second table). Leave `liveTestFlag=TEST` for now.

### Step 4 — Build the XML for a fund

```bash
nport build fdrs 2026-06 --dry-run    # check: transforms + validates, writes nothing
nport build fdrs 2026-06              # for real: writes output/FDRS_2026-06.xml
```

`fdrs` is the fund's folder name. The dry-run tells you if anything is missing before you commit. Repeat per fund.

If it complains a field is missing, fix it in that fund's `security_master.csv` (security data) or `filing_data.txt` (fund numbers), then rerun.

### Step 5 — Review and file

Open `output/FDRS_2026-06.xml` and sanity-check the fund name, period, holding count, and net assets. When it looks right:

1. Set `liveTestFlag=LIVE` in that fund's `filing_data.txt`.
2. Rerun `nport build fdrs 2026-06`.
3. Upload the resulting XML to EDGAR.

---

## 3. Bloomberg: exactly what to pull and where to put it

You only need Bloomberg for **securities the custodian file can't fully describe** — mainly the LEI/ISIN on stocks, and the counterparty/delta/notional on options and swaps. `nport masters` adds the rows; you fill the blank cells.

**Fastest way to do it:** open the fund's `security_master.csv` in Excel with the Bloomberg add-in, and use `BDP` formulas to pull each field, e.g.

```
=BDP("AAPL US Equity", "ID_LEI")
=BDP("AAPL US Equity", "ID_ISIN")
```

Then paste the values in and save as CSV. (Or just look each up on the terminal and type it in.)

### What to pull from Bloomberg, by security type

| Security type | CSV column to fill | What it is | Bloomberg field (mnemonic) |
|---|---|---|---|
| **Stock / ETF** | `lei` | Issuer Legal Entity Identifier | `ID_LEI` |
| | `isin` | ISIN identifier | `ID_ISIN` |
| | `cusip` | CUSIP (usually already in custodian file) | `ID_CUSIP` |
| | `invCountry` | Country of domicile (2-letter, e.g. `US`) | `CNTRY_OF_DOMICILE` |
| **Option** | `counterpartyName` | Dealer/bank on the other side | (your trade record / OTC confirm) |
| | `counterpartyLei` | That dealer's LEI | `ID_LEI` on the counterparty |
| | `delta` | Option delta | `DELTA_MID_RT` |
| **Swap (TRS)** | `counterpartyName` | Swap dealer | (swap confirm) |
| | `counterpartyLei` | That dealer's LEI | `ID_LEI` on the counterparty |
| | `notionalAmt` | Notional amount of the swap | swap confirm / `SWPM` screen |
| | `unrealizedAppr` | Mark-to-market unrealized gain/loss (USD) | `SWPM` / fund accounting |
| | `valUSD` | Current USD value of the swap | `SWPM` / fund accounting |
| | `pctVal` | `valUSD ÷ netAssets × 100` | compute from the two numbers |

Notes:
- For **stocks**, `nport masters` already auto-fills `name`, `assetCat`, `issuerCat`, and often `lei`/`isin`/`country` from the reference XMLs in `data/RealXMLs/`. Only fill what's blank or looks wrong.
- For **options**, the strike, expiry, and put/call are parsed automatically from the position name — you do **not** re-enter those. You only add `counterpartyName`, `counterpartyLei`, `delta`.
- A **TRS** is a total-return swap (custodian ticker contains `-TRS-`). Its valuation numbers come from the swap confirm or fund accounting, not the custodian file.

### What to get from fund accounting (NOT Bloomberg) — goes in `filing_data.txt`

| Key | Meaning |
|---|---|
| `totAssets`, `totLiabs`, `netAssets` | Total assets, total liabilities, net assets |
| `rtn1`, `rtn2`, `rtn3` | The fund's monthly total returns (the 3 months in the period) |
| `netRealizedGainMon1..3` | Realized gain per month |
| `netUnrealizedApprMon1..3` | Change in unrealized appreciation per month |
| `mon1..3Sales` / `Redemption` / `Reinvestment` | Capital flows (creations / redemptions / reinvested distributions) per month |
| `dateSigned` | Date you sign (`YYYY-MM-DD`) |

Balance-sheet lines (`amtPay*`, `delayDeliv`, etc.) are normally `0` for ETFs and the template already sets them.

---

## 4. Command reference

| Do this | Command | Notes |
|---|---|---|
| Print the checklist | `nport guide` | |
| Update security masters | `nport masters [period] [fund]` | All funds by default; add a ticker for just one. |
| Make filing templates | `nport filing [period] [fund]` | One `filing_data.txt` per fund. |
| Build a fund's XML | `nport build <fund> [period]` | Add `--dry-run` to check without writing. |
| Check inputs only | `nport validate <fund> [period]` | Parses + validates, generates nothing. |
| See an existing EDGAR filing | `nport pull --ticker <TICK> --list` | Compare against what you're filing. |
| Check the SEC schema version | `nport check-schema` | |

**Defaults that save typing:**
- Leave off the period → uses the newest `data/custodian/*_holdings.csv`.
- A bare fund name (`fdrs`) → resolves to `data/funds/fdrs`.
- The custodian CSV path is always derived from the period — you never type it.

`masters`, `filing`, and `build` are short aliases for the older `update-masters`, `new-filing`, and `ingest`. The long forms with explicit `--custodian`/`--fund-dir`/`--period` flags still work if you ever need them.

---

## 5. Reference: what each file is

```
data/custodian/2026-06_holdings.csv     ← you drop this in (US Bank export, all funds)

data/funds/fdrs/
├── fund_config.txt                     ← fund identity, set once
├── security_master.csv                 ← per-security data; updated by `masters`, then you fill blanks
└── filings/2026-06/
    ├── filing_data.txt                 ← fund numbers for the month; you fill these in
    ├── holdings.csv                    ← GENERATED by `build` (don't edit)
    ├── debt_securities.csv             ← GENERATED (only if fund holds debt)
    └── derivatives.csv                 ← GENERATED (only if fund holds options/swaps)
```

- **You edit:** `fund_config.txt` (once), `security_master.csv` (Bloomberg blanks), `filing_data.txt` (fund-accounting numbers).
- **The tool generates:** `holdings.csv` + satellites, and the final XML in `output/`. Never hand-edit the generated files — change the source and rebuild.

### Codes you'll see in the CSVs

- **assetCat** (asset type): `EC` equity · `DBT` debt · `DE` derivative · `STIV` money-market.
- **issuerCat** (issuer type): `CORP` corporate · `UST` US Treasury · `RF` registered fund · `OTHER`.
- **derivCat**: `OPT` option · `SWP` swap.
- **units**: `NS` shares · `PA` principal amount · `NC` contracts.
- **liveTestFlag**: `TEST` while drafting, `LIVE` for the real filing.

### How `build` works under the hood (for debugging)

custodian CSV → classify each row (equity/option/swap/treasury/money-market/cash) → derive what it can → **merge in your `security_master.csv` values (blanks only — your entries always win)** → validate required fields → write `holdings.csv` → build XML → validate against SEC schema → write to `output/`. `--dry-run` stops right before writing the XML.

Source layout, dataclasses, and the full field list live in `docs/how_it_works.md` and `src/nport/`.

---

## 6. Gotchas

- **Three things you supply each month:** the US Bank CSV (Step 1), the Bloomberg blanks in `security_master.csv` (Step 2/§3), and the fund numbers in `filing_data.txt` (Step 3). Everything else is automatic.
- **The security master only fills blanks.** It never overwrites a value you typed, so your counterparties/deltas/notionals survive every `masters` and `build` run.
- **Don't edit generated files.** `holdings.csv`/`debt_securities.csv`/`derivatives.csv` are rebuilt every `build`. Fix the source (`security_master.csv`) instead.
- **Always TEST before LIVE.** Review the XML, then flip the flag and rebuild for the real upload.
- **A fund needs both `fund_config.txt` and `security_master.csv`** to be filed.
