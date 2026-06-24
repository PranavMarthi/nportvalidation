# N-PORT Filing — How To Do It

This is your start-to-finish playbook. Read §1–§4 to file. Everything below that is reference.

**What this tool does:** turns the monthly US Bank positions CSV + a little fund metadata into a valid SEC N-PORT XML, ready to upload to EDGAR.

---

## 1. One-time setup (new machine)

Install **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)**, then:

**macOS**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # install uv (then reopen the terminal)
git clone <repo-url> nport && cd nport
uv sync                                              # install dependencies
source .venv/bin/activate                            # so you can type `nport ...` not `uv run nport ...`
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"  # then reopen PowerShell
git clone <repo-url> nport; cd nport
uv sync
.venv\Scripts\Activate.ps1
```

(If you skip the activate line, just put `uv run` in front of every `nport` command.) Verify:
`uv run pytest` then `nport guide`.

Each fund lives in `data/funds/<ticker>/`. The only file you ever set by hand per fund is
`fund_config.txt` (its identity — CIK, name, address, signer; set once). Everything else —
`security_master.csv`, `filing_data.txt`, `holdings.csv` — is **generated** for you. New fund?
Copy `data/funds/fdrs/fund_config.txt` into the new folder and edit the values.

> **All the data lives in two workbooks.** `data/master/security_master.xlsx` (holdings
> reference data) and `data/master/filing_master.xlsx` (returns, net assets, flows, risk). You
> build them, enrich them once on Bloomberg, and split them out to every fund. You never edit
> the per-fund files directly.

---

## 2. The monthly process (drop in 2 files, run 3 commands)

> The period (`2026-06`) is optional — leave it off and the newest custodian file is used.

### Drop in your two source files

```
data/custodian/2026-06_holdings.csv   ← US Bank monthly positions (all funds)
data/orders/2026-06_orders.csv        ← AP creation/redemption order book (optional — fills capital flows)
```

Every command finds these by name; you never type a path.

### Step 1 — Build the two workbooks, enrich them on Bloomberg

```bash
nport masters          # builds BOTH data/master/*.xlsx from the custodian (+ AP orders)
```

`masters` scans the custodian, adds new securities and drops ones no longer held across every
fund, **keeps everything you typed in by hand**, and pre-fills the Bloomberg cells with live
`=BDP()` formulas. (Run `nport masters --dry-run` to preview.)

Then **open BOTH workbooks on the Bloomberg machine, let them calculate, and save** (keep them
`.xlsx`; don't "save as CSV"). This is the Bloomberg step — see §3. Bloomberg fills stock
LEI/ISIN/country, the monthly returns, and bond durations; swap/option counterparties + LEIs
fill automatically. The handful of truly manual cells (option `delta`, swap
`notionalAmt`/`unrealizedAppr`, fund-accounting gains) you type into the workbooks before saving.

### Step 2 — Split the workbooks into per-fund files

```bash
nport split            # writes every fund's security_master.csv + filing_data.txt
```

> Edit the workbooks, **not** the per-fund files — `split` overwrites them every time.

### Step 3 — Build the XML

```bash
nport build --dry-run         # validate every fund, write nothing
nport build                   # write output/<TICKER>_2026-06.xml for every fund
nport build fdrs              # …or just one fund
```

The dry-run tells you if anything's missing before you commit. If it flags a field, fix it in
the workbook, re-`split`, and rebuild.

### File it

Open `output/<TICKER>_2026-06.xml` and sanity-check the fund name, period, holding count, and
net assets. When it looks right:

1. Set `liveTestFlag=LIVE` (in the filing master before splitting, or in each `filing_data.txt`).
2. Rerun `nport build`.
3. Upload the XML to EDGAR.

---

## 3. Bloomberg: exactly what to pull and where to put it

You only need Bloomberg for **securities the custodian file can't fully describe** — mainly the LEI/ISIN on stocks, bond durations (for B.3 risk), and the delta/notional on options and swaps. `nport masters` adds the rows; the workbooks fetch what they can **once, in `data/master/*.xlsx`** — every fund holding that security is covered at the same time. (`masters` builds both workbooks; `build-master`/`build-filing-master` build them individually if you ever need to.)

**The workbook has two sheets.** Sheet **`custodian`** is the US Bank CSV in Excel, verbatim — you never touch it. Sheet **`master`** has one row per custodian row (same order, 1:1) and is where everything is assembled. Because the two sheets are row-aligned, each `cusip` cell is a direct reference into sheet 1 — `=custodian!D5` — so the CUSIP is **copied from the custodian, never fetched**. (The N/A-for-foreign rule is applied later by the build, so the master mirrors the custodian as-is; a foreign CINS shows its raw value here.)

**The Bloomberg fields fetch themselves.** For every **equity** row, `build-master` writes a live `=BDP(...)` formula into `isin`, `lei`, and `invCountry`, each referencing the row's `bbgid` helper cell (`<ticker> US Equity`). `name`/`title`/`ticker` come straight from the custodian. Example LEI formula (row 2, `bbgid` in column B):

```
=IFERROR(IF(BDP($B2,"LEGAL_ENTITY_IDENTIFIER")="","N/A",BDP($B2,"LEGAL_ENTITY_IDENTIFIER")),"N/A")
```

The identifier is the Excel add-in form `<ticker> US Equity` (`AAPL US Equity`, `AER US Equity`) — **not** the `/cusip/…` override syntax, which the desktop API accepts but the Excel BDP add-in rejects as "Invalid Security". One universal form covers US and international: `ID_ISIN` gives the foreign identifier, `LEGAL_ENTITY_IDENTIFIER` the LEI, and `CNTRY_OF_DOMICILE` the issuer's home country (`NL`, `BR`, `AU`; verified against real filings — domicile, not incorporation). Each cell falls back to a schema-valid default (`N/A` / `""` / `US`) when Bloomberg is empty, so the filing stays valid even before the workbook is opened on a terminal. *(Equities only for now — money-market, treasuries, options and swaps are a later pass.)*

So the workflow is: open **both** `data/master/*.xlsx` on the **Bloomberg machine**, let the formulas calculate, and **save** (keep `.xlsx`; don't "save as CSV"). Equity LEI/ISIN/country, the filing master's monthly returns, and the bond-duration `risk` sheet all populate automatically. Then run `nport split`.

**Counterparties are now automatic.** Each swap's counterparty is read from the custodian ticker code (`CANT`→Cantor Fitzgerald, `CLST`/`CS`→Clear Street, `MREX`→Marex) and mapped to its legal name + GLEIF LEI; options use the OCC central counterparty. You no longer type these.

What you still fill by hand (no per-security feed exists): the **option `delta`** and the **swap `notionalAmt`/`unrealizedAppr`** — from your trade confirms / fund accounting (see the table below). Option OCC symbols don't resolve on the terminal, so delta can't be auto-fetched. Type those into the workbook, then split.

Flags: `nport masters` always inserts the BDP formulas. For finer control, `build-master --no-formulas` skips the injection and `--all-formulas` re-inserts even over already-provided values (use it to refresh everything from Bloomberg, e.g. to correct a stale hardcoded country).

### What to pull from Bloomberg, by security type

| Security type | CSV column to fill | What it is | Bloomberg field (mnemonic) |
|---|---|---|---|
| **Stock / ETF** (auto) | `name` | Issuer name (truncated to 30) | from custodian (literal) |
| | `cusip` | CUSIP | `=custodian!…` reference (copied, not fetched) |
| | `lei` | Issuer Legal Entity Identifier | `LEGAL_ENTITY_IDENTIFIER` |
| | `isin` | ISIN identifier | `ID_ISIN` |
| | `invCountry` | Issuer home country / domicile (2-letter) | `CNTRY_OF_DOMICILE` |
| **Bond** (auto) | `lei`/`isin`/coupon/maturity | debt reference data | `=BDP()` on `<cusip> Govt/Corp` |
| **Option** | `counterpartyName`/`counterpartyLei` | OCC central counterparty | **auto** (constant) |
| | `delta` | Option delta (OCC symbol won't resolve) | **manual** — fund accounting / risk system |
| **Swap (TRS)** | `counterpartyName`/`counterpartyLei` | Cantor / Clear Street / Marex | **auto** (custodian code → GLEIF LEI) |
| | `valUSD` / `pctVal` | swap value / % of net assets | from custodian |
| | `notionalAmt` | Notional amount of the swap | **manual** — swap confirm / `SWPM` |
| | `unrealizedAppr` | Mark-to-market unrealized gain/loss (USD) | **manual** — `SWPM` / fund accounting |

Notes:
- For **stocks/bonds**, `masters` writes `=BDP()` formulas, so opening the workbook on the Bloomberg terminal fills them automatically. `name`/`title`/`ticker` and `cusip` come from the custodian (cusip is a live `=custodian!…` reference); `assetCat`/`issuerCat` are set by the tool. Just open, let it calc, save, split.
- For **options**, the strike, expiry, and put/call are parsed automatically from the position name, and the counterparty is the OCC — you only add `delta`.
- A **TRS** is a total-return swap (custodian ticker contains `-TRS-`). Counterparty + LEI are resolved from the ticker code; only `notionalAmt`/`unrealizedAppr` are manual.

### The filing master (`data/master/filing_master.xlsx`) — mostly automatic now

`masters` builds this second workbook so the per-period numbers fill themselves:

| Key | Source |
|---|---|
| `totAssets`, `totLiabs`, `netAssets` | **custodian** (computed) |
| `rtn1`, `rtn2`, `rtn3` (monthly total returns) | **Bloomberg** `=BDP()` (calc on the terminal) |
| `mon1..3Sales` / `Redemption` | **AP order book** (`data/orders/<period>_orders.csv`) |
| B.3 risk metrics (debt funds) | **Bloomberg** bond durations (the `risk` sheet) |
| `netRealizedGainMon1..3`, `netUnrealizedApprMon1..3` | **manual** — fund accounting (cost basis) |
| `mon1..3Reinvestment` | **manual** — reinvested distributions |
| `dateSigned` | **manual** — date you sign (`YYYY-MM-DD`) |

Balance-sheet lines (`amtPay*`, `delayDeliv`, etc.) are normally `0` for ETFs and the workbook already sets them. Type the few manual numbers into the filing master before saving, then `nport split`.

---

## 4. Command reference

**The three you use every month:**

| Do this | Command | Notes |
|---|---|---|
| **1.** Build both workbooks | `nport masters [period]` | From the custodian (+ `data/orders/<period>_orders.csv`). `--ap-orders PATH`, `--dry-run`. |
| **2.** Split → per-fund files | `nport split [period]` | Writes every `security_master.csv` + `filing_data.txt`. `--dry-run`. |
| **3.** Build the XML | `nport build [fund] [period]` | No fund = all funds. `--dry-run`, `--verbose`. |

**Also handy:**

| Do this | Command |
|---|---|
| Print the checklist | `nport guide` |
| Check one fund's inputs (no XML) | `nport validate <fund> [period]` |
| See an existing EDGAR filing | `nport pull --ticker <TICK> --list` |
| Everything (incl. advanced) | `nport --help` |

**Defaults that save typing:**
- Leave off the period → uses the newest `data/custodian/*_holdings.csv`.
- A bare fund name (`fdrs`) → resolves to `data/funds/fdrs`.
- The custodian and order-book paths are derived from the period — you never type them.

**Advanced / power-user** (wrapped by `masters`/`split` — use only if you need finer control):
`build-master`/`split-master` (security workbook only), `build-filing-master`/`split-filing-master`
(filing workbook only), `generate`, `enrich`, `merge`, `new-filing`, `update-masters`,
`check-schema`, `schema`. Run `nport <cmd> --help` for flags. First time on a brand-new repo,
`nport build-master --seed` migrates any existing per-fund CSVs into the workbook.

---

## 5. Reference: what each file is

```
data/custodian/2026-06_holdings.csv     ← you drop this in (US Bank export, all funds)
data/orders/2026-06_orders.csv          ← you drop this in (AP order book, optional → flows)

data/master/security_master.xlsx        ← holdings reference data; covers every fund
data/master/filing_master.xlsx          ← returns / net assets / flows / B.3 risk; every fund
                                           (both built by `masters`, enriched by you on Bloomberg, read by `split`)

data/funds/fdrs/
├── fund_config.txt                     ← fund identity, set once
├── security_master.csv                 ← GENERATED by `split` (don't hand-edit)
└── filings/2026-06/
    ├── filing_data.txt                 ← GENERATED by `split` (don't hand-edit)
    ├── holdings.csv                    ← GENERATED by `build` (don't edit)
    ├── debt_securities.csv             ← GENERATED (only if fund holds debt)
    └── derivatives.csv                 ← GENERATED (only if fund holds options/swaps)
```

- **You edit:** `fund_config.txt` (once) and the two `data/master/*.xlsx` workbooks (the Bloomberg cells + the few manual numbers, for all funds at once).
- **The tool generates:** every per-fund `security_master.csv` + `filing_data.txt` (via `split`), `holdings.csv` + satellites, and the final XML in `output/`. Never hand-edit the generated files — change the workbook and re-`split`/`build`.

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

- **What you supply each month:** the US Bank CSV + the AP order book (drop-ins), then on Bloomberg the few manual cells in the two workbooks (option `delta`, swap `notionalAmt`/`unrealizedAppr`, fund-accounting gains). Everything else is automatic.
- **The workbooks only fill blanks.** They never overwrite a value you typed, so your manual deltas/notionals/gains survive every `nport masters` run.
- **Edit the workbooks, then split.** After touching either `data/master/*.xlsx`, always run `nport split` — the build reads the per-fund files, not the workbooks.
- **Don't edit generated files.** The per-fund `security_master.csv` + `filing_data.txt` (rebuilt by `split`) and `holdings.csv`/`debt_securities.csv`/`derivatives.csv` (rebuilt by `build`) are all generated. Fix the source — the workbook — instead.
- **Close the workbooks before splitting.** If Excel still has a `.xlsx` (or a target per-fund file) open, the write fails — close it first.
- **Always TEST before LIVE.** Review the XML, then flip `liveTestFlag=LIVE` and rebuild for the real upload.
- **A fund needs `fund_config.txt`, `security_master.csv`, and `filing_data.txt`** to be filed (the last two come from `nport split`).
