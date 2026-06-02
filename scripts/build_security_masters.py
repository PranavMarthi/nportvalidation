#!/usr/bin/env python3
"""Build security master CSVs for all funds from reference data + custodian CSV.

Usage:
    uv run python scripts/build_security_masters.py \
        --custodian ~/Downloads/Corgi_Adv*.csv \
        --output data/funds
"""

import argparse
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nport.custodian import (
    CustodianRow,
    HoldingType,
    classify_holding,
    filter_by_account,
    load_xml_reference,
    parse_custodian_csv,
    build_equity_entry,
    build_mm_entry,
    build_option_entry,
    build_swap_entry,
    build_treasury_entry,
    write_security_master,
    EQUITY_HEADERS,
    OPTION_HEADERS,
    SWAP_HEADERS,
)


def build_all(custodian_path: Path, output_dir: Path, xml_dir: Path) -> None:
    # 1. Load reference data from real XMLs
    ref = load_xml_reference(xml_dir)
    print(f"Reference data: {len(ref)} entries from XMLs")

    # 2. Parse custodian CSV
    all_rows = parse_custodian_csv(custodian_path)
    accounts = filter_by_account(all_rows)
    print(f"Custodian: {len(all_rows)} rows, {len(accounts)} accounts")

    # 3. Build per-fund security masters
    for account, rows in sorted(accounts.items()):
        # Classify holdings
        types: dict[HoldingType, list[CustodianRow]] = {}
        for r in rows:
            ht = classify_holding(r)
            types.setdefault(ht, []).append(r)

        has_options = HoldingType.OPTION in types
        has_swaps = HoldingType.SWAP in types
        has_equities = HoldingType.EQUITY in types
        has_mm = HoldingType.MONEY_MARKET in types

        # Skip cash-only funds
        non_cash = [ht for ht in types if ht != HoldingType.CASH]
        if not non_cash:
            print(f"\n{account}: cash-only, skipping")
            continue

        fund_dir = output_dir / account.lower()
        entries: list[dict[str, str]] = []

        print(f"\n{account}: {', '.join(f'{len(v)} {k.value}' for k, v in sorted(types.items(), key=lambda x: x[0].value))}")

        # Equities
        if has_equities:
            seen_cusips: set[str] = set()
            for r in types[HoldingType.EQUITY]:
                if r.cusip in seen_cusips:
                    continue
                seen_cusips.add(r.cusip)
                entries.append(build_equity_entry(r.stock_ticker, r.security_name, r.cusip, ref))

        # Money market
        if has_mm:
            entries.append(build_mm_entry(ref))

        # Determine headers based on fund type
        if has_options or has_swaps:
            headers = list(dict.fromkeys(
                EQUITY_HEADERS + (OPTION_HEADERS if has_options else []) + (SWAP_HEADERS if has_swaps else [])
            ))
        else:
            headers = list(EQUITY_HEADERS)

        # Options
        if has_options:
            for r in types[HoldingType.OPTION]:
                entries.append(build_option_entry(r))

        # Treasury
        if HoldingType.TREASURY in types:
            for r in types[HoldingType.TREASURY]:
                entries.append(build_treasury_entry(r))

        # Swaps
        if has_swaps:
            for r in types[HoldingType.SWAP]:
                entries.append(build_swap_entry(r))

        sm_path = fund_dir / "security_master.csv"
        write_security_master(entries, headers, sm_path)
        print(f"  Written: {sm_path} ({len(entries)} entries)")


def main():
    parser = argparse.ArgumentParser(description="Build security masters from custodian CSV + reference XMLs")
    parser.add_argument("--custodian", required=True, help="Custodian CSV path")
    parser.add_argument("--output", default="data/funds", help="Output fund directory root")
    parser.add_argument("--xml-dir", default="data/RealXMLs", help="Directory with reference N-PORT XMLs")
    args = parser.parse_args()

    build_all(Path(args.custodian), Path(args.output), Path(args.xml_dir))


if __name__ == "__main__":
    main()
