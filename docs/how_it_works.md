# How nport Works

## What This Tool Does

Every quarter, investment funds must file an **N-PORT report** with the SEC. This report lists every security the fund holds — every stock, bond, option, and swap — in a specific XML format.

This tool takes simple text and CSV files you maintain by hand, and produces the SEC-compliant XML filing.

```
Your files (easy to edit)  ──→  nport  ──→  SEC XML filing (ready to submit)
```

---

## The Inputs: 3 Things You Provide

You fill out three things per filing. Think of them as three questions:

### 1. "Who is the fund?" — `fund_config.txt`

Static info about the fund. You set this up once and rarely touch it.

```
regName=Corgi ETF Trust I
seriesName=Corgi Investment Grade Bond ETF
cik=0002078265
seriesId=S000096625
signerName=Emily Yuan
signerTitle=President & PEO
...
```

Contains: EDGAR login credentials, registrant name/address, series and class IDs, who signs the filing.

### 2. "How did the fund perform this month?" — `filing_data.txt`

Monthly numbers. You update this each filing period.

```
submissionType=NPORT-P
repPdEnd=2025-12-31
totAssets=50200000.00
totLiabs=200000.00
netAssets=50000000.00
rtn1=0.35
rtn2=0.42
rtn3=0.28
...
```

Contains: reporting dates, total assets/liabilities, monthly returns, cash flows, risk metrics.

### 3. "What does the fund hold?" — CSV files

The portfolio. One row per security. This is where the most work goes.

**Every fund has `holdings.csv`** — the basics for every position:

| holdingId | name | cusip | balance | valUSD | pctVal | assetCat | ... |
|---|---|---|---|---|---|---|---|
| AAPL29 | Apple Inc | 037833DX9 | 5,000,000 | 4,925,000 | 9.85 | DBT | ... |
| FGXX | First Amer Govt Oblg | 31846V336 | 5,075,000 | 5,075,000 | 10.15 | STIV | ... |

**Bonds also get `debt_securities.csv`** — maturity, coupon, rate:

| holdingId | maturityDt | couponKind | annualizedRt | isDefault |
|---|---|---|---|---|
| AAPL29 | 2029-02-09 | Fixed | 3.25 | N |

**Derivatives also get `derivatives.csv`** — counterparty, terms, legs:

| holdingId | derivCat | counterpartyName | terminationDt | notionalAmt | ... |
|---|---|---|---|---|---|
| SPX-TRS-JPM | SWP | JPMorgan Chase Bank NA | 2026-06-30 | 50,000,000 | ... |

The `holdingId` column links them together. Apple's bond details live in a separate file from its basic info, but `AAPL29` connects them.

**Why split files?** A bond fund doesn't need 40 empty swap columns. A swap fund doesn't need empty bond columns. Each file only has what's relevant.

---

## The Output: SEC XML

The tool produces one XML file that contains everything the SEC expects:

```xml
<edgarSubmission>

  <headerData>                        ←── from fund_config.txt
    <submissionType>NPORT-P</submissionType>
    <filer>
      <issuerCredentials>
        <cik>0002078265</cik>
      </issuerCredentials>
    </filer>
  </headerData>

  <formData>
    <genInfo>                         ←── from fund_config.txt + filing_data.txt
      <regName>Corgi ETF Trust I</regName>
      <seriesName>Corgi Investment Grade Bond ETF</seriesName>
      <repPdEnd>2025-12-31</repPdEnd>
    </genInfo>

    <fundInfo>                        ←── from filing_data.txt
      <totAssets>50200000.00</totAssets>
      <netAssets>50000000.00</netAssets>
      <returnInfo>...</returnInfo>
    </fundInfo>

    <invstOrSecs>                     ←── from holdings CSVs
      <invstOrSec>                    ←── one per holding
        <name>Apple Inc</name>
        <cusip>037833DX9</cusip>
        <valUSD>4925000.00</valUSD>
        <debtSec>                     ←── only for bonds
          <maturityDt>2029-02-09</maturityDt>
          <couponKind>Fixed</couponKind>
        </debtSec>
      </invstOrSec>
      ...
    </invstOrSecs>

    <signature>                       ←── from fund_config.txt
      <signerName>Emily Yuan</signerName>
    </signature>
  </formData>

</edgarSubmission>
```

---

## How It Flows

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR INPUT FILES                        │
│                                                             │
│  fund_config.txt    filing_data.txt    holdings.csv          │
│  (who)              (performance)      (portfolio)           │
│                                        debt_securities.csv   │
│                                        derivatives.csv       │
└──────────┬──────────────┬──────────────────┬────────────────┘
           │              │                  │
           ▼              ▼                  ▼
┌──────────────────────────────────────────────────────────────┐
│                        PARSE                                 │
│                                                              │
│  Read each file, translate column names to internal format,  │
│  merge split CSVs by holdingId, fill blanks for fields       │
│  that don't apply (a stock has no maturity date).            │
│                                                              │
│  Result: FundConfig + FilingData + list of Holdings          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                       VALIDATE                               │
│                                                              │
│  Check the data before building XML:                         │
│  - Is every CUSIP 9 characters?                              │
│  - Do percentage weights add up to ~100%?                    │
│  - Does total assets minus liabilities equal net assets?     │
│  - Do derivatives have counterparty names?                   │
│                                                              │
│  Errors → stop. Warnings → continue with notes.              │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      BUILD XML                               │
│                                                              │
│  Walk through each data object and produce XML elements:     │
│                                                              │
│  FundConfig  → <headerData>, <genInfo>, <signature>          │
│  FilingData  → <fundInfo> (assets, returns, flows)           │
│  Holdings[]  → <invstOrSec> for each, with:                  │
│                  bond?       → add <debtSec>                 │
│                  option?     → add <optionDeriv>             │
│                  swap?       → add <swapDeriv>               │
│                  just stock? → base fields only              │
│                                                              │
│  Empty fields are skipped — no empty XML tags.               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    SCHEMA CHECK                              │
│                                                              │
│  Validate the generated XML against the SEC's official       │
│  XSD schema — the formal rules for what a valid N-PORT       │
│  filing looks like. Catches structural errors.               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                       OUTPUT                                 │
│                                                              │
│                    output.xml                                │
│              (ready to submit to SEC)                        │
└──────────────────────────────────────────────────────────────┘
```

---

## File Layout

Each fund is a folder. Each filing period is a subfolder.

```
bond_fund/
│
├── fund_config.txt                 ← set up once
├── security_master.csv             ← optional reference data
│
└── filings/
    └── 2025-12/                    ← one folder per period
        ├── filing_data.txt         ← monthly numbers
        ├── holdings.csv            ← every holding
        ├── debt_securities.csv     ← bond details (optional)
        └── derivatives.csv         ← derivative details (optional)
```

To file a new month, copy the period folder, update the numbers, and run the tool.

---

## Running It

Generate a filing:
```
nport generate --fund-dir bond_fund --period 2025-12 --output filing.xml
```

Validate without generating (check your data):
```
nport validate --fund-dir bond_fund --period 2025-12
```

---

## What Each Holding Type Looks Like

### Stock (simplest)

Only needs `holdings.csv`. 20 base fields: name, CUSIP, value, percentage, country, etc.

```
AAPL,Apple Inc,HWUPKR...,Apple Inc,037833100,...,Long,EC,CORP,US,...
```

### Bond

Needs `holdings.csv` + `debt_securities.csv`. Base fields plus maturity date, coupon type, and interest rate.

```
holdings.csv:          AAPL29, Apple Inc, ..., DBT, CORP, ...
debt_securities.csv:   AAPL29, 2029-02-09, Fixed, 3.25, N, N, N
```

### Option

Needs `holdings.csv` + `derivatives.csv`. Base fields plus put/call, strike price, expiration, delta.

```
holdings.csv:     SPX-C4800, SPX Call 4800, ..., DE, CORP, ...
derivatives.csv:  SPX-C4800, OPT, Goldman Sachs, ..., Call, Purchased, 4800.00, 2026-12-18, 0.72
```

### Swap

Needs `holdings.csv` + `derivatives.csv`. Base fields plus counterparty, termination date, notional amount, receive/pay leg details.

```
holdings.csv:     SPX-TRS-JPM, SPX TRS JPMorgan, ..., DE, CORP, ...
derivatives.csv:  SPX-TRS-JPM, SWP, JPMorgan Chase, ..., 2026-06-30, 50000000, Floating, ...
```

### Money market fund

Only needs `holdings.csv`. No bonds, no derivatives. Just cash-like holdings.

```
FGXX, First Amer Govt Oblg, ..., STIV, RF, ...
```

---

## Summary

| You provide | What it contains | How often it changes |
|---|---|---|
| `fund_config.txt` | Fund identity, EDGAR credentials, signer | Rarely |
| `filing_data.txt` | Assets, returns, flows, dates | Every filing period |
| `holdings.csv` | Every position (name, value, %) | Every filing period |
| `debt_securities.csv` | Bond details (maturity, coupon) | Every filing period (if fund holds bonds) |
| `derivatives.csv` | Derivative details (counterparty, terms) | Every filing period (if fund holds derivatives) |

| You get back | What it is |
|---|---|
| `output.xml` | Complete SEC N-PORT filing, ready to submit to EDGAR |
