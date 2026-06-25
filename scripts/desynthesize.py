"""Replace fabricated/synthetic values in the per-fund source files with honest ones.

Nothing is made up. For every field with no real data source we write either a
schema-valid "N/A" (where the XSD permits it) or leave it blank (where it doesn't,
so the fund honestly fails validation until real data arrives). Real and derivable
values are preserved/repaired:

  filing_data.txt  gains, reinvestment, sales/redemption  -> N/A  (no feed)
  security_master  swap counterpartyName/Lei              -> real legal name + GLEIF LEI
                   option counterpartyName/Lei            -> OCC + GLEIF LEI
                   option delta                           -> N/A  (no feed; XSD allows N/A)
                   swap/option unrealizedAppr             -> blank (no feed; XSD forbids N/A here)
                   swap notionalAmt                       -> kept (real: shares x price)
  fund_config.txt  fabricated seriesId (not S000######)   -> blank (needs EDGAR)

Run: uv run python scripts/desynthesize.py [--dry-run]
"""
import csv
import re
import sys
from pathlib import Path

from nport.custodian import _OCC_LEI, _OCC_NAME, _SWAP_COUNTERPARTIES

FUNDS = Path("data/funds")

_NA_FILING_KEYS = [
    "rtn1", "rtn2", "rtn3",   # Bloomberg total returns — N/A until calculated on the terminal
    "netRealizedGainMon1", "netUnrealizedApprMon1", "netRealizedGainMon2",
    "netUnrealizedApprMon2", "netRealizedGainMon3", "netUnrealizedApprMon3",
    "mon1Reinvestment", "mon2Reinvestment", "mon3Reinvestment",
    "mon1Sales", "mon1Redemption", "mon2Sales", "mon2Redemption",
    "mon3Sales", "mon3Redemption",
]
_REAL_SERIES_ID = re.compile(r"^S000\d{6}$")   # genuine EDGAR series-id format


def _fix_filing(path: Path, dry: bool) -> int:
    text = path.read_text(encoding="utf-8")
    n = 0
    for key in _NA_FILING_KEYS:
        new, c = re.subn(rf"(?m)^({key}=).*$", rf"\g<1>N/A", text)
        text, n = new, n + c
    if c_total := n:
        if not dry:
            path.write_text(text, encoding="utf-8")
    return c_total


def _fix_security_master(path: Path, dry: bool) -> dict:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        rows = list(reader)
    counts = {"swap": 0, "option": 0}
    for r in rows:
        cat = (r.get("derivCat") or "").strip()
        if cat == "SWP":
            code = (r.get("counterpartyName") or "").strip().upper()
            if code in _SWAP_COUNTERPARTIES:
                r["counterpartyName"], r["counterpartyLei"] = _SWAP_COUNTERPARTIES[code]
            if "unrealizedAppr" in r:
                r["unrealizedAppr"] = ""          # no feed; XSD forbids N/A on swaps
            counts["swap"] += 1
        elif cat == "OPT":
            r["counterpartyName"], r["counterpartyLei"] = _OCC_NAME, _OCC_LEI
            if "delta" in r:
                r["delta"] = "N/A"                # no feed (FLEX won't price); XSD allows N/A
            if "unrealizedAppr" in r:
                r["unrealizedAppr"] = ""           # no feed; XSD forbids N/A → honest blank
            counts["option"] += 1
    if (counts["swap"] or counts["option"]) and not dry:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
    return counts


def _fix_config(path: Path, dry: bool) -> str | None:
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?m)^seriesId=(.*)$", text)
    if not m:
        return None
    val = m.group(1).strip()
    if val and not _REAL_SERIES_ID.match(val):
        if not dry:
            path.write_text(re.sub(r"(?m)^seriesId=.*$", "seriesId=", text), encoding="utf-8")
        return val
    return None


def main() -> None:
    dry = "--dry-run" in sys.argv
    funds = sorted(d for d in FUNDS.iterdir() if (d / "fund_config.txt").is_file())
    tot = {"filing": 0, "swap": 0, "option": 0}
    blanked_series = []
    for d in funds:
        for fp in d.glob("filings/*/filing_data.txt"):
            if fp.parent.name == "2025-12":
                continue   # real reference/example filings — never synthetic
            tot["filing"] += _fix_filing(fp, dry)
        sm = d / "security_master.csv"
        if sm.is_file():
            c = _fix_security_master(sm, dry)
            tot["swap"] += c["swap"]
            tot["option"] += c["option"]
        old = _fix_config(d / "fund_config.txt", dry)
        if old:
            blanked_series.append((d.name, old))
    verb = "WOULD change" if dry else "changed"
    print(f"{verb}:")
    print(f"  filing_data fields -> N/A:      {tot['filing']}")
    print(f"  swap rows repaired (LEI/MTM):   {tot['swap']}")
    print(f"  option rows repaired (OCC/delta): {tot['option']}")
    print(f"  fabricated seriesId blanked:    {len(blanked_series)} funds")
    if blanked_series:
        print("    " + ", ".join(f"{n}({v})" for n, v in blanked_series[:8])
              + (" ..." if len(blanked_series) > 8 else ""))
    print("\nBlocked until real data (won't pass XSD): seriesId (EDGAR), swap unrealizedAppr (fund accounting).")


if __name__ == "__main__":
    main()
