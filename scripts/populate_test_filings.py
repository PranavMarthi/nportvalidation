"""Populate REALISTIC SYNTHETIC test data so every custodian fund is XML-ready.

Scope (explicitly operator-authorized, test-only): fund_config.txt, filing_data.txt,
and the derivative economics that exist in neither the custodian nor Bloomberg
(counterpartyLei / notionalAmt / unrealizedAppr / option delta). The master
security data is NEVER touched here.

Determinism: every value is a pure function of the fund ticker and the custodian
numbers, so this is reproducible and traceable. Grounded fields (netAssets,
totAssets, totLiabs) come straight from the custodian; the rest are synthetic but
format-valid and internally consistent. liveTestFlag stays TEST throughout.
"""
import csv
import hashlib
import string
from collections import defaultdict
from pathlib import Path

from nport.custodian import parse_custodian_csv

CUST = Path("data/custodian/2026-06_holdings.csv")
FUNDS = Path("data/funds")
PERIOD = "2026-06"
END = "2026-06-30"
SIGNED = "2026-07-30"
SKIP_CONFIG = {"fdrs", "bond_fund", "buffered_etf", "leveraged_etf"}  # real/synthetic, leave alone

_ALNUM = string.digits + string.ascii_uppercase


def _h(seed: str) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16)


def lei(seed: str) -> str:
    """A deterministic, XSD-valid synthetic LEI: 18 × [0-9A-Z] + 2 check digits
    (the N-PORT pattern is [0-9A-Z]{18}[0-9]{2})."""
    d = hashlib.sha256(seed.encode()).digest()
    body = "".join(_ALNUM[b % 36] for b in d[:18])
    chk = "".join(str(b % 10) for b in d[18:20])
    return body + chk


def digits(seed: str, n: int) -> str:
    return str(_h(seed) % (10 ** n)).zfill(n)


def span(seed: str, lo: float, hi: float) -> float:
    return round(lo + (_h(seed) % 10_000) / 10_000 * (hi - lo), 2)


def fnum(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


# Trust-level identity: reuse fdrs's real "Corgi ETF Trust I" (one trust, many series).
TRUST = dict(
    cik="0002078265", ccc="C0rgi#26", regName="Corgi ETF Trust I",
    regFileNumber="811-24117", regCik="0002078265", regLei="529900HSQC73ZP7RGT16",
    regStreet1="425 Bush St.", regStreet2="Suite 500", regCity="San Francisco",
    regState="US-CA", regCountry="US", regZip="94104", regPhone="855-552-6744",
    signerOrg="Corgi ETF Trust I", signerName="Emily Yuan", signerTitle="President & PEO",
)

CONFIG = """# {T} — SYNTHETIC TEST configuration (deterministic; liveTestFlag stays TEST)
# Trust-level fields reuse Corgi ETF Trust I (fdrs). Series/Class are per-fund test IDs.

# EDGAR Credentials
cik={cik}
ccc={ccc}

# Registrant Information
regName={regName}
regFileNumber={regFileNumber}
regCik={regCik}
regLei={regLei}
regStreet1={regStreet1}
regStreet2={regStreet2}
regCity={regCity}
regState={regState}
regCountry={regCountry}
regZipOrPostalCode={regZip}
regPhone={regPhone}

# Series / Class (per-fund synthetic test IDs)
seriesName={seriesName}
seriesId={seriesId}
seriesLei={seriesLei}
classId={classId}

# Signature Block
signerOrg={signerOrg}
signerName={signerName}
signerTitle={signerTitle}
"""

FILING = """# {T} {PERIOD} — SYNTHETIC TEST filing data (deterministic). liveTestFlag=TEST.
# netAssets/totAssets/totLiabs are GROUNDED from the custodian; returns/gains/flows
# are synthetic but format-valid and internally consistent.

submissionType=NPORT-P
liveTestFlag=TEST
repPdEnd={END}
repPdDate={END}
isFinalFiling=N
dateSigned={SIGNED}

# Fund Financials (totAssets/totLiabs/netAssets reconcile: totAssets - totLiabs = netAssets)
totAssets={totAssets:.2f}
totLiabs={totLiabs:.2f}
netAssets={netAssets:.2f}

# Balance Sheet Items
assetsAttrMiscSec=0
assetsInvested=0
amtPayOneYrBanksBorr=0
amtPayOneYrCtrldComp=0
amtPayOneYrOthAffil=0
amtPayOneYrOther=0
amtPayAftOneYrBanksBorr=0
amtPayAftOneYrCtrldComp=0
amtPayAftOneYrOthAffil=0
amtPayAftOneYrOther=0
delayDeliv=0
standByCommit=0
liquidPref=0
isNonCashCollateral=N

# Returns (monthly total returns, %)
rtn1={rtn1}
rtn2={rtn2}
rtn3={rtn3}
netRealizedGainMon1={rg1:.2f}
netUnrealizedApprMon1={ua1:.2f}
netRealizedGainMon2={rg2:.2f}
netUnrealizedApprMon2={ua2:.2f}
netRealizedGainMon3={rg3:.2f}
netUnrealizedApprMon3={ua3:.2f}

# Flows
mon1Sales={s1:.2f}
mon1Redemption={d1:.2f}
mon1Reinvestment={i1:.2f}
mon2Sales={s2:.2f}
mon2Redemption={d2:.2f}
mon2Reinvestment={i2:.2f}
mon3Sales={s3:.2f}
mon3Redemption={d3:.2f}
mon3Reinvestment={i3:.2f}

# Designated Index
nameDesignatedIndex=N/A
indexIdentifier=N/A
"""

# Known counterparty dealer codes → synthetic but stable LEIs.
CP_LEI = {c: lei("counterparty:" + c) for c in ("CANT", "CLST", "MREX", "CS")}


def main():
    cust = parse_custodian_csv(CUST)
    by_acct = defaultdict(list)
    for r in cust:
        by_acct[r.account.upper()] = by_acct[r.account.upper()]
        by_acct[r.account.upper()].append(r)

    n_cfg = n_fil = n_deriv_funds = n_deriv_rows = 0
    for acct, rows in by_acct.items():
        fund = acct.lower()
        fdir = FUNDS / fund
        if not fdir.is_dir():
            continue

        # ── Grounded financials from the custodian ──
        net = fnum(rows[0].net_assets)
        liabs = sum(-fnum(r.market_value) for r in rows if fnum(r.market_value) < 0)
        tot = net + liabs

        # ── fund_config.txt (skip funds that already have a real one) ──
        if fund not in SKIP_CONFIG:
            cfg = CONFIG.format(
                T=acct, seriesName=f"{acct} ETF",
                seriesId="S" + digits("series:" + acct, 9),
                seriesLei=lei("series:" + acct),
                classId="C" + digits("class:" + acct, 9),
                **TRUST,
            )
            (fdir / "fund_config.txt").write_text(cfg, encoding="utf-8")
            n_cfg += 1

        # ── filing_data.txt (synthetic numbers; skip fdrs — already filled) ──
        if fund != "fdrs":
            fdir.joinpath("filings", PERIOD).mkdir(parents=True, exist_ok=True)
            vals = dict(
                T=acct, PERIOD=PERIOD, END=END, SIGNED=SIGNED,
                totAssets=tot, totLiabs=liabs, netAssets=net,
                rtn1=span("r1" + acct, -2.5, 3.0), rtn2=span("r2" + acct, -2.5, 3.0),
                rtn3=span("r3" + acct, -2.5, 3.0),
                rg1=net * span("rg1" + acct, -0.004, 0.006), ua1=net * span("ua1" + acct, -0.006, 0.008),
                rg2=net * span("rg2" + acct, -0.004, 0.006), ua2=net * span("ua2" + acct, -0.006, 0.008),
                rg3=net * span("rg3" + acct, -0.004, 0.006), ua3=net * span("ua3" + acct, -0.006, 0.008),
                s1=net * span("s1" + acct, 0, 0.05), d1=net * span("d1" + acct, 0, 0.04), i1=net * span("i1" + acct, 0, 0.002),
                s2=net * span("s2" + acct, 0, 0.05), d2=net * span("d2" + acct, 0, 0.04), i2=net * span("i2" + acct, 0, 0.002),
                s3=net * span("s3" + acct, 0, 0.05), d3=net * span("d3" + acct, 0, 0.04), i3=net * span("i3" + acct, 0, 0.002),
            )
            fdir.joinpath("filings", PERIOD, "filing_data.txt").write_text(FILING.format(**vals), encoding="utf-8")
            n_fil += 1

        # ── Derivative economics in the per-fund security_master.csv ──
        sm = fdir / "security_master.csv"
        if not sm.is_file():
            continue
        with open(sm, newline="", encoding="utf-8") as f:
            hdr = next(csv.reader(f))
        srows = list(csv.DictReader(open(sm, newline="", encoding="utf-8")))
        touched = False
        for r in srows:
            dc = r.get("derivCat", "")
            if dc not in ("OPT", "SWP"):
                continue
            touched = True
            n_deriv_rows += 1
            val = abs(fnum(r.get("valUSD")))
            seed = acct + (r.get("ticker") or r.get("rawTicker") or "")
            if dc == "SWP":
                cp = r.get("counterpartyName") or "CANT"
                r["counterpartyLei"] = CP_LEI.get(cp, lei("cp:" + cp))
                r["notionalAmt"] = f"{val:.2f}"
                r["unrealizedAppr"] = f"{val * span('ua' + seed, -0.03, 0.03):.2f}"
                # TRS legs: receive the total return of the reference (Other),
                # pay a floating financing rate (SOFR + spread).
                ref = r.get("refIssuerName") or r.get("refTicker") or r.get("title") or "Reference"
                r["recFixedOrFloating"] = "Other"
                r["recDesc"] = f"Total return of {ref}"
                r["pmntFixedOrFloating"] = "Floating"
                r["pmntFloatingRtIndex"] = "USD-SOFR"
                r["pmntFloatingRtSpread"] = f"{span('spr' + seed, 0.10, 0.90):.2f}"
                r["pmntCurCdLeg"] = "USD"
                r["pmntPmntAmt"] = f"{val:.2f}"
                r["pmntRateTenor"] = "Month"      # period enum (Day/Month/Year)
                r["pmntRateUnit"] = "3"           # integer count → 3-month reset
            else:  # OPT — listed/cleared: counterparty is the clearing house
                r["counterpartyName"] = "Options Clearing Corp"
                r["counterpartyLei"] = lei("counterparty:OCC")
                r["unrealizedAppr"] = f"{val * span('uo' + seed, -0.05, 0.05):.2f}"
                pc = (r.get("putOrCall") or "Call").lower()
                base = span("delta" + seed, 0.25, 0.75)
                r["delta"] = f"{base if pc == 'call' else -base:.4f}"
        if touched:
            n_deriv_funds += 1
            with open(sm, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=hdr)
                w.writeheader()
                w.writerows({c: r.get(c, "") for c in hdr} for r in srows)

    print(f"fund_config written: {n_cfg}")
    print(f"filing_data written: {n_fil}")
    print(f"derivative funds updated: {n_deriv_funds} ({n_deriv_rows} rows)")


if __name__ == "__main__":
    main()
