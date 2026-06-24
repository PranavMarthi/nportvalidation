"""One-time repair of spreadsheet-corrupted CUSIPs in committed data.

Excel round-trips have mangled CUSIPs in the custodian export and in many
``security_master.csv`` files (dropped leading zeros; embedded-``E`` CUSIPs
turned into scientific notation). This script repairs them in place.

Recovery strategy:
  * leading-zero drops      -> left-pad to 9 (lossless)
  * scientific notation     -> recover from the row's own ISIN, else from a
                               ticker->CUSIP index built across the repo
                               (other masters' valid CUSIPs / ISINs and the
                               RealXMLs reference). Anything still
                               unrecoverable is reported, not guessed.

Run from the repo root:  python scripts/repair_cusips.py [--apply]
Without --apply it's a dry run.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lxml import etree  # noqa: E402

from nport.cusip import (  # noqa: E402
    cusip_from_isin,
    is_valid_cusip,
    normalize_cusip,
)

ROOT = Path(__file__).resolve().parent.parent
FUNDS = ROOT / "data" / "funds"
CUSTODIAN_DIR = ROOT / "data" / "custodian"
XML_DIR = ROOT / "data" / "RealXMLs"
_NS = {"n": "http://www.sec.gov/edgar/nport"}


def build_ticker_index() -> dict[str, str]:
    """ticker -> valid CUSIP, gathered from every clean source in the repo."""
    index: dict[str, str] = {}

    def offer(ticker: str, cusip: str) -> None:
        ticker = (ticker or "").strip().upper()
        if ticker and cusip and is_valid_cusip(cusip):
            index.setdefault(ticker, cusip)

    # Security masters: trust valid CUSIPs and CUSIPs derivable from ISINs.
    for sm in FUNDS.glob("*/security_master.csv"):
        with open(sm, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tkr = row.get("ticker", "")
                offer(tkr, row.get("cusip", "").strip())
                from_isin = cusip_from_isin(row.get("isin", ""))
                if from_isin:
                    offer(tkr, from_isin)

    # RealXMLs reference holdings.
    for xml in XML_DIR.glob("*.xml"):
        tree = etree.parse(str(xml))
        for sec in tree.findall(".//n:invstOrSec", _NS):
            cusip = sec.findtext("n:cusip", "", _NS).strip()
            ids = sec.find("n:identifiers", _NS)
            tkr = ""
            if ids is not None:
                te = ids.find("n:ticker", _NS)
                if te is not None:
                    tkr = te.get("value", "")
            offer(tkr, cusip)

    return index


def repair_value(raw: str, isin: str, ticker: str, index: dict[str, str]) -> tuple[str, str | None]:
    """Return (repaired_cusip, note). note is set only when unrecoverable."""
    fixed, warning = normalize_cusip(raw, isin)
    if warning or (fixed == raw and not is_valid_cusip(fixed) and fixed not in ("", "N/A", "000000000")):
        by_ticker = index.get((ticker or "").strip().upper())
        if by_ticker:
            return by_ticker, None
        if warning:
            return fixed, warning
    return fixed, None


def repair_csv(path: Path, ticker_col: str, cusip_col: str, isin_col: str,
               index: dict[str, str], apply: bool) -> tuple[int, list[str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if cusip_col not in fieldnames:
        return 0, []

    changes = 0
    unrecoverable: list[str] = []
    for row in rows:
        raw = (row.get(cusip_col) or "").strip()
        fixed, note = repair_value(
            raw, row.get(isin_col, ""), row.get(ticker_col, ""), index)
        if note:
            unrecoverable.append(f"  {path.relative_to(ROOT)}: {row.get(ticker_col,'?')} -> {note}")
        if fixed != raw:
            changes += 1
            print(f"  {path.relative_to(ROOT)}: {row.get(ticker_col,'?'):<14} {raw!r:>14} -> {fixed!r}")
            row[cusip_col] = fixed

    if changes and apply:
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except PermissionError:
            _LOCKED.append(str(path.relative_to(ROOT)))
            return 0, unrecoverable
    return changes, unrecoverable


_LOCKED: list[str] = []


def main() -> None:
    apply = "--apply" in sys.argv
    index = build_ticker_index()
    print(f"Recovery index: {len(index)} ticker->CUSIP entries\n")

    total = 0
    problems: list[str] = []

    print("== custodian ==")
    for cust in sorted(CUSTODIAN_DIR.glob("*_holdings.csv")):
        n, probs = repair_csv(cust, "StockTicker", "CUSIP", "_noisin_", index, apply)
        total += n
        problems += probs

    print("\n== security masters ==")
    for sm in sorted(FUNDS.glob("*/security_master.csv")):
        n, probs = repair_csv(sm, "ticker", "cusip", "isin", index, apply)
        total += n
        problems += probs

    print(f"\n{'APPLIED' if apply else 'DRY RUN'}: {total} CUSIP(s) repaired")
    if _LOCKED:
        print(f"\n{len(_LOCKED)} file(s) LOCKED (close them in Excel and rerun):")
        for p in _LOCKED:
            print(f"  {p}")
    if problems:
        print(f"\n{len(problems)} UNRECOVERABLE — need manual entry:")
        for p in problems:
            print(p)


if __name__ == "__main__":
    main()
