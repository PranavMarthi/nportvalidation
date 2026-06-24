# nport

Generate SEC N-PORT XML filings from your US Bank custodian CSV + Bloomberg.

> Want the full picture (what every file means, the Bloomberg fields, a worked example)?
> Read **[OVERVIEW.md](OVERVIEW.md)**. This page gets you from a blank machine to a filing.

---

## 1. Set up a new machine (once)

You need **Python 3.11+** and **[uv](https://docs.astral.sh/uv/)** (the package manager). Pick your OS.

### macOS

```bash
# 1. install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# (restart the terminal, or run: source $HOME/.local/bin/env)

# 2. get the project + install dependencies
git clone <repo-url> nport
cd nport
uv sync

# 3. (optional) activate the venv so you can type `nport` instead of `uv run nport`
source .venv/bin/activate
```

### Windows (PowerShell)

```powershell
# 1. install uv
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# (close and reopen PowerShell so `uv` is on PATH)

# 2. get the project + install dependencies
git clone <repo-url> nport
cd nport
uv sync

# 3. (optional) activate the venv so you can type `nport` instead of `uv run nport`
.venv\Scripts\Activate.ps1
```

> If you skip step 3, just put `uv run` in front of every command (`uv run nport guide`).

Check it works (same on both OSes):

```bash
uv run pytest        # should report all tests passing
nport guide          # prints the monthly checklist
```

---

## 2. File N-PORT — drop in 2 files, run 3 commands

The period (e.g. `2026-06`) is **optional** everywhere — leave it off and the newest
custodian file is used.

### Drop in your two source files

| Save it here | Where it comes from |
|---|---|
| `data/custodian/2026-06_holdings.csv` | US Bank — the monthly positions export (all funds) |
| `data/orders/2026-06_orders.csv` | your AP order portal — creation/redemption order book *(optional; fills capital flows)* |

The tool finds both by name — you never type the path.

### Step 1 — Build the two workbooks

```bash
nport masters
```

Creates `data/master/security_master.xlsx` (holdings reference data) and
`data/master/filing_master.xlsx` (returns, net assets, flows, risk).

**Then open BOTH on the Bloomberg machine, let the `=BDP()` formulas calculate, and save**
(keep them `.xlsx`). Bloomberg auto-fills stock LEI/ISIN/country, monthly returns, and bond
durations; swap/option counterparties + LEIs are filled automatically. The only cells you
type by hand are option `delta`, swap `notionalAmt`/`unrealizedAppr`, and the fund-accounting
gains — enter those in the workbooks before saving. (See [OVERVIEW.md §3](OVERVIEW.md).)

### Step 2 — Split the workbooks into per-fund files

```bash
nport split
```

Writes every fund's `security_master.csv` and `filing_data.txt` from the two workbooks.
Edit the **workbooks**, not the per-fund files — `split` overwrites them.

### Step 3 — Generate the XML

```bash
nport build            # every fund   → output/<TICKER>_2026-06.xml
nport build fdrs       # just one fund
nport build --dry-run  # validate everything, write nothing
```

### File it

Review the XML in `output/`. When it's right, set `liveTestFlag=LIVE` (in the filing master
before splitting, or in each `filing_data.txt`), run `nport build` again, and upload to EDGAR.

---

## 3. Commands

The three above are all you need monthly. Full list:

| Command | What it does |
|---|---|
| `nport masters [period]` | **Step 1** — build both master workbooks from the custodian (+ AP orders). `--ap-orders PATH` to point at the order file; `--dry-run`. |
| `nport split [period]` | **Step 2** — write every per-fund file from both workbooks. `--dry-run`. |
| `nport build [fund] [period]` | **Step 3** — generate XML. No fund = all funds. `--dry-run`, `--verbose`. |
| `nport validate <fund> [period]` | Validate a fund's inputs without generating. |
| `nport guide` | Print the monthly checklist. |
| `nport pull --ticker <T> --list` | List/download existing EDGAR filings (to compare). |
| `nport --help` | Everything, including `(advanced)` low-level commands. |

**Advanced / power-user** (you normally won't need these — `masters`/`split` wrap them):
`build-master`, `split-master`, `build-filing-master`, `split-filing-master`, `generate`,
`enrich`, `merge`, `new-filing`, `update-masters`, `check-schema`, `schema`.

Defaults that save typing: omit the period → newest custodian file; a bare fund name
(`fdrs`) → `data/funds/fdrs`; the custodian/order paths are derived from the period.

---

## 4. What's where

```
data/custodian/2026-06_holdings.csv   ← you drop in (US Bank, all funds)
data/orders/2026-06_orders.csv        ← you drop in (AP order book, optional)

data/master/security_master.xlsx      ← built by `masters`, you enrich on Bloomberg, read by `split`
data/master/filing_master.xlsx        ← built by `masters`, you enrich on Bloomberg, read by `split`

data/funds/fdrs/
├── fund_config.txt                   ← fund identity (CIK, name, address, signer); set once
├── security_master.csv               ← GENERATED by `split` (don't hand-edit)
└── filings/2026-06/
    ├── filing_data.txt               ← GENERATED by `split` (don't hand-edit)
    ├── holdings.csv                  ← GENERATED by `build`
    ├── debt_securities.csv           ← GENERATED (if the fund holds debt)
    └── derivatives.csv               ← GENERATED (if the fund holds options/swaps)

output/<TICKER>_2026-06.xml           ← the filing, written by `build`
```

- **You edit:** the two `.xlsx` workbooks (on Bloomberg) and `fund_config.txt` (once).
- **The tool generates:** every per-fund file + the final XML. Don't hand-edit generated
  files — change the workbook and re-`split`/`build`.

## Tests

```bash
uv run pytest                    # all tests
uv run pytest -k test_custodian  # one module
```
