"""CLI for N-PORT filing generator."""

import argparse
import copy
import csv
import re
import sys
import tempfile
from pathlib import Path

from nport import eaglestar
from nport.builder import NportBuilder
from nport.config import _HOLDINGS_KEY_MAP, parse_config, parse_filing, parse_holdings
from nport.custodian import (
    filter_by_account,
    generate_filing_template,
    ingest_account,
    parse_custodian_csv,
    update_security_master,
    write_security_master,
)
from nport.data_loader import DataLoader, merge_positions_with_master, validate_after_merge, write_canonical_csv, write_split_csv
from nport.filing_master import (
    build_filing_master_from_custodian,
    split_filing_master,
)
from nport.master_sheet import (
    refresh_master,
    seed_master_from_per_fund,
    split_master,
)
from nport.input_validation import validate_all
from nport.schema_check import (
    CURRENT_SCHEMA_VERSION,
    check_for_schema_update,
    check_schema_files,
)
from nport.security_master import SecurityMaster
from nport.xsd_validator import NportValidator


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    """Add --config/--filing/--holdings and --fund-dir/--period to a subparser."""
    parser.add_argument("--config", default=None, help="fund_config.txt path")
    parser.add_argument("--filing", default=None, help="filing_data.txt path")
    parser.add_argument("--holdings", default=None, help="holdings.csv path")
    parser.add_argument("--fund-dir", default=None, help="Fund directory path")
    parser.add_argument("--period", default=None, help="Filing period (e.g. 2025-12)")


def main(argv: list[str] | None = None) -> None:
    # Windows consoles default to cp1252 and crash on the —/←/→ in help & guide text.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass  # already UTF-8, or a non-reconfigurable stream (e.g. pytest capture)

    parser = argparse.ArgumentParser(prog="nport", description="Generate SEC N-PORT XML filings")
    sub = parser.add_subparsers(dest="command")

    # ── The 3 commands you use every month ───────────────────────
    ms = sub.add_parser("masters", help="STEP 1: build BOTH master workbooks from the custodian (+ AP orders)")
    ms.add_argument("pos", nargs="*", help="[period] — defaults to the latest custodian file")
    ms.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    ms.add_argument("--custodian", default=None, help="Custodian CSV (default: data/custodian/<period>_holdings.csv)")
    ms.add_argument("--ap-orders", default=None, help="AP order book CSV (default: data/orders/<period>_orders.csv)")
    ms.add_argument("--fund-accounting", default=None, help="EagleSTAR export .zip/.mbox (default: newest in data/fund_accounting/)")
    ms.add_argument("--no-fund-accounting", action="store_true", help="Skip EagleSTAR fund-accounting pre-fill")
    ms.add_argument("--dry-run", action="store_true", help="Show what would be built")

    sp = sub.add_parser("split", help="STEP 2: write every per-fund file from BOTH workbooks")
    sp.add_argument("pos", nargs="*", help="[period] — defaults to the latest custodian file")
    sp.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    sp.add_argument("--dry-run", action="store_true", help="Report targets without writing")
    # STEP 3 is `build` (defined as `ingest` below) — `nport build` for all funds, `nport build <fund>` for one.

    gen = sub.add_parser("generate", help="(advanced) Generate N-PORT XML from explicit input files")
    _add_input_args(gen)
    gen.add_argument("--output", required=True, help="Output XML path")
    gen.add_argument("--schema-dir", default=None, help="XSD schema directory")
    gen.add_argument("--skip-validation", action="store_true")
    gen.add_argument("--skip-schema-check", action="store_true")
    gen.add_argument("--verbose", action="store_true")
    gen.add_argument("--strict", action="store_true", help="Treat warnings as errors")

    val = sub.add_parser("validate", help="Validate a fund's inputs: `nport validate fdrs [2026-06]`")
    val.add_argument("pos", nargs="*", help="<fund> [period] — what to validate")
    _add_input_args(val)
    val.add_argument("--schema-dir", default=None)

    cs = sub.add_parser("check-schema", help="Check schema files and version")
    cs.add_argument("--schema-dir", default=None)
    cs.add_argument("--force", action="store_true", help="Skip cache")

    en = sub.add_parser("enrich", help="Enrich minimal CSV with Bloomberg data")
    en.add_argument("--input", required=True, help="Minimal 4-column CSV path")
    en.add_argument("--output", required=True, help="Output canonical holdings CSV path")
    en.add_argument("--batch-size", type=int, default=50, help="Bloomberg batch size")
    en.add_argument("--host", default="localhost", help="Bloomberg host")
    en.add_argument("--port", type=int, default=8194, help="Bloomberg port")

    mg = sub.add_parser("merge", help="Merge positions CSV with a security master")
    mg.add_argument("--positions", required=True, help="Positions CSV path")
    mg.add_argument("--security-master", required=True, help="Security master CSV path")
    mg.add_argument("--output", required=True, help="Output canonical holdings CSV path (or directory with --split)")
    mg.add_argument("--split", action="store_true", help="Write split CSVs (base + debt + derivatives) instead of one flat file")

    ig = sub.add_parser("ingest", aliases=["build"], help="STEP 3: generate N-PORT XML — `nport build` (all funds) or `nport build fdrs`")
    ig.add_argument("pos", nargs="*", help="[fund] [period] — no fund = every fund for the period")
    ig.add_argument("--custodian", default=None, help="Custodian CSV (default: data/custodian/<period>_holdings.csv)")
    ig.add_argument("--fund-dir", default=None, help="Fund directory (default: data/funds/<fund>)")
    ig.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    ig.add_argument("--account", default=None, help="Account ticker override")
    ig.add_argument("--output", default=None, help="Output XML path (default: output/<ACCOUNT>_<PERIOD>.xml)")
    ig.add_argument("--schema-dir", default=None, help="XSD schema directory")
    ig.add_argument("--skip-validation", action="store_true", help="Skip XSD validation")
    ig.add_argument("--verbose", action="store_true")
    ig.add_argument("--dry-run", action="store_true", help="Transform and validate only, do not write XML")

    sub.add_parser("schema", help="Print the holdings data schema")

    pl = sub.add_parser("pull", help="Download N-PORT filings from EDGAR")
    pl_group = pl.add_mutually_exclusive_group(required=True)
    pl_group.add_argument("--cik", default=None, help="10-digit CIK")
    pl_group.add_argument("--ticker", default=None, help="Fund ticker symbol")
    pl.add_argument("--output", default=None, help="Save XML to file")
    pl.add_argument("--list", action="store_true", dest="list_filings", help="List recent filings")
    pl.add_argument("--count", type=int, default=5, help="Number of filings to list (default: 5)")

    um = sub.add_parser("update-masters", help="(advanced/legacy) Update per-fund security_master.csv directly from custodian + reference XMLs")
    um.add_argument("pos", nargs="*", help="[period] [fund] — period defaults to latest, fund defaults to all")
    um.add_argument("--custodian", default=None, help="Custodian CSV (default: data/custodian/<period>_holdings.csv)")
    um.add_argument("--fund-dir", default="data/funds", help="Fund directory (default: data/funds)")
    um.add_argument("--account", default=None, help="Account ticker to update (default: all accounts)")
    um.add_argument("--all", action="store_true", dest="all_accounts", help="Update all accounts found in custodian")
    um.add_argument("--xml-dir", default="data/RealXMLs", help="Directory with reference N-PORT XMLs")
    um.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    bm = sub.add_parser("build-master", aliases=["master-build"], help="(advanced) Build only the security master workbook (`masters` builds both)")
    bm.add_argument("pos", nargs="*", help="[period] [account] — period defaults to latest, account defaults to all")
    bm.add_argument("--custodian", default=None, help="Custodian CSV (default: data/custodian/<period>_holdings.csv)")
    bm.add_argument("--master", default="data/master/security_master.xlsx", help="Master workbook path")
    bm.add_argument("--account", default=None, help="Account to refresh (default: all accounts)")
    bm.add_argument("--all", action="store_true", dest="all_accounts", help="Refresh all accounts found in custodian")
    bm.add_argument("--xml-dir", default="data/RealXMLs", help="Directory with reference N-PORT XMLs")
    bm.add_argument("--seed", action="store_true", help="One-time: seed the master from existing per-fund CSVs")
    bm.add_argument("--fund-dir", default="data/funds", help="Fund directory (default: data/funds)")
    bm.add_argument("--no-formulas", action="store_true", help="Don't insert live Bloomberg =BDP() formulas into blank cells")
    bm.add_argument("--all-formulas", action="store_true", help="Re-insert BDP formulas even over already-populated Bloomberg cells")
    bm.add_argument("--dry-run", action="store_true", help="Show changes without writing")

    sm = sub.add_parser("split-master", aliases=["master-split"], help="(advanced) Split only the security master (`split` does both)")
    sm.add_argument("pos", nargs="*", help="[account] — defaults to all accounts in the master")
    sm.add_argument("--master", default="data/master/security_master.xlsx", help="Master workbook path")
    sm.add_argument("--fund-dir", default="data/funds", help="Fund directory (default: data/funds)")
    sm.add_argument("--account", default=None, help="Account to split (default: all)")
    sm.add_argument("--all", action="store_true", dest="all_accounts", help="Split all accounts in the master")
    sm.add_argument("--dry-run", action="store_true", help="Report per-fund row counts without writing")

    bf = sub.add_parser("build-filing-master", aliases=["filing-master-build"], help="(advanced) Build only the filing master workbook (`masters` builds both)")
    bf.add_argument("pos", nargs="*", help="[period] — defaults to latest custodian file")
    bf.add_argument("--custodian", default=None, help="Custodian CSV (default: data/custodian/<period>_holdings.csv)")
    bf.add_argument("--master", default="data/master/filing_master.xlsx", help="Filing master workbook path")
    bf.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    bf.add_argument("--ap-orders", default=None, help="AP order book CSV → monthly Sales/Redemption flows")
    bf.add_argument("--dry-run", action="store_true", help="Show what would be written")

    sf = sub.add_parser("split-filing-master", aliases=["filing-master-split"], help="(advanced) Split only the filing master (`split` does both)")
    sf.add_argument("pos", nargs="*", help="[account] — defaults to all funds in the master")
    sf.add_argument("--master", default="data/master/filing_master.xlsx", help="Filing master workbook path")
    sf.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    sf.add_argument("--fund-dir", default="data/funds", help="Fund directory (default: data/funds)")
    sf.add_argument("--account", default=None, help="Account to split (default: all)")
    sf.add_argument("--dry-run", action="store_true", help="Report targets without writing")

    nf = sub.add_parser("new-filing", aliases=["filing"], help="(advanced) Create blank filing_data.txt templates (`masters`+`split` already produce these)")
    nf.add_argument("pos", nargs="*", help="[period] [fund] — period defaults to latest, fund defaults to all")
    nf.add_argument("--period", default=None, help="Filing period (default: latest custodian file)")
    nf.add_argument("--fund-dir", default="data/funds", help="Fund directory (default: data/funds)")
    nf.add_argument("--account", default=None, help="Account ticker (default: all fund subdirs)")
    nf.add_argument("--all", action="store_true", dest="all_accounts", help="Process all fund subdirs")

    sub.add_parser("guide", help="Print step-by-step N-PORT filing guide")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "masters": _masters,
        "split": _split,
        "generate": _generate,
        "validate": _validate,
        "check-schema": _check_schema,
        "enrich": _enrich,
        "merge": _merge,
        "ingest": _ingest,
        "build": _ingest,          # alias
        "schema": _schema,
        "pull": _pull,
        "update-masters": _update_masters,
        "build-master": _build_master,
        "master-build": _build_master,  # alias
        "split-master": _split_master,
        "master-split": _split_master,  # alias
        "build-filing-master": _build_filing_master,
        "filing-master-build": _build_filing_master,  # alias
        "split-filing-master": _split_filing_master,
        "filing-master-split": _split_filing_master,  # alias
        "new-filing": _new_filing,
        "filing": _new_filing,       # alias
        "guide": _guide,
    }
    dispatch[args.command](args)


_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _validate_period(period: str) -> None:
    """Validate period is YYYY-MM with valid month, exit on bad input."""
    if not _PERIOD_RE.match(period):
        print(f"ERROR: Invalid period '{period}'. Expected YYYY-MM (e.g. 2026-06).", file=sys.stderr)
        sys.exit(1)


_DEFAULT_FUNDS_DIR = Path("data/funds")
_DEFAULT_CUSTODIAN_DIR = Path("data/custodian")


def _split_positionals(pos: list[str] | None) -> tuple[str | None, str | None]:
    """Split positional args into (account, period). A YYYY-MM token is the period."""
    account = period = None
    for tok in pos or []:
        if _PERIOD_RE.match(tok):
            period = tok
        else:
            account = tok
    return account, period


_CUSTODIAN_HEADER_KEYS = {"Date", "Account", "CUSIP", "SecurityName"}


def _custodian_period(path: Path) -> str | None:
    """The reporting period (YYYY-MM) read from a custodian CSV's first Date value.

    Returns None if the file isn't a custodian export. Lets any filename work — the
    period comes from the data, not the name.
    """
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            if not _CUSTODIAN_HEADER_KEYS <= set(header):
                return None
            di = header.index("Date")
            row = next(reader, None)
            if not row or di >= len(row):
                return None
            mo, _da, yr = row[di].split("/")
            return f"{int(yr):04d}-{int(mo):02d}"
    except (OSError, ValueError, StopIteration):
        return None


def _discover_custodians() -> list[tuple[Path, str]]:
    """Every custodian-format CSV in data/custodian/ paired with its detected period."""
    if not _DEFAULT_CUSTODIAN_DIR.is_dir():
        return []
    out = []
    for p in sorted(_DEFAULT_CUSTODIAN_DIR.glob("*.csv")):
        per = _custodian_period(p)
        if per:
            out.append((p, per))
    return out


def _latest_period() -> str | None:
    """The newest period among the custodian CSVs (by their Date column, any filename)."""
    periods = [per for _, per in _discover_custodians()]
    return max(periods) if periods else None


def _resolve_period(period: str | None) -> str:
    """Validate an explicit period, or auto-detect the latest custodian file."""
    if period:
        _validate_period(period)
        return period
    latest = _latest_period()
    if not latest:
        print("ERROR: No period given and none found in data/custodian/. "
              "Pass one, e.g. `2026-06`.", file=sys.stderr)
        sys.exit(1)
    print(f"Using latest period: {latest}")
    return latest


def _resolve_custodian(custodian: str | None, period: str) -> Path:
    """The custodian CSV for a period: an explicit path, the <period>_holdings.csv
    convention, or — failing that — any custodian-format CSV in data/custodian/ whose
    Date column matches the period (so the file's name doesn't matter)."""
    if custodian:
        path = Path(custodian)
    else:
        path = _DEFAULT_CUSTODIAN_DIR / f"{period}_holdings.csv"
        if not path.is_file():
            matches = [p for p, per in _discover_custodians() if per == period]
            if matches:
                path = max(matches, key=lambda p: p.stat().st_mtime)
    if not path.is_file():
        print(f"ERROR: Custodian CSV not found for {period} in {_DEFAULT_CUSTODIAN_DIR}/", file=sys.stderr)
        sys.exit(1)
    return path


def _log_issues(errors: list[str], warnings: list[str], label: str = "") -> None:
    prefix = f"{label} " if label else ""
    for e in errors:
        print(f"  {prefix}ERROR: {e}", file=sys.stderr)
    for w in warnings:
        print(f"  {prefix}WARNING: {w}", file=sys.stderr)


def _parse_inputs(args):
    """Parse all three input files, exit on failure.

    Supports two modes:
    - --fund-dir + --period: load from structured fund directory
    - --config + --filing + --holdings: load from individual file paths
    """
    if getattr(args, "fund_dir", None):
        if not getattr(args, "period", None):
            print("ERROR: --period is required when using --fund-dir.", file=sys.stderr)
            sys.exit(1)
        try:
            loader = DataLoader(args.fund_dir)
            return loader.load_all(args.period)
        except FileNotFoundError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"ERROR: parse error: {e}", file=sys.stderr)
            sys.exit(1)

    # Individual file mode — require all three
    for flag in ("config", "filing", "holdings"):
        if not getattr(args, flag, None):
            print(f"ERROR: --{flag} is required (or use --fund-dir + --period).", file=sys.stderr)
            sys.exit(1)

    parsers = [
        ("config", args.config, parse_config),
        ("filing", args.filing, parse_filing),
        ("holdings", args.holdings, parse_holdings),
    ]
    results = []
    for name, path, fn in parsers:
        try:
            results.append(fn(path))
        except FileNotFoundError:
            print(f"ERROR: {name} file not found: {path}", file=sys.stderr)
            sys.exit(1)
        except ValueError as e:
            print(f"ERROR: {name} parse error: {e}", file=sys.stderr)
            sys.exit(1)
    return results[0], results[1], results[2]


def _generate(args) -> None:
    all_warnings = []

    # Schema files
    schema_errors, schema_warnings = check_schema_files(args.schema_dir)
    all_warnings.extend(schema_warnings)
    if schema_errors:
        _log_issues(schema_errors, [])
        sys.exit(1)

    # Schema version check
    if not args.skip_schema_check:
        _, w = check_for_schema_update()
        all_warnings.extend(w)

    # Parse
    config, filing, holdings = _parse_inputs(args)
    if args.verbose:
        print(f"Parsed: {config.reg_name} / {config.series_name} / "
              f"{filing.submission_type} {filing.rep_pd_end} / {len(holdings)} holdings")

    # Input validation
    input_errors, input_warnings = validate_all(config, filing, holdings)
    all_warnings.extend(input_warnings)
    if input_errors:
        _log_issues(input_errors, [], "INPUT")
        sys.exit(1)

    # Build XML
    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
    if args.verbose:
        print(f"Generated: {len(xml_bytes)} bytes")

    # XSD validation
    if not args.skip_validation:
        xsd_errors = NportValidator(schema_dir=args.schema_dir).validate_xsd(xml_bytes)
        if xsd_errors:
            _log_issues(xsd_errors, [], "XSD")
            sys.exit(1)
        elif args.verbose:
            print("XSD validation passed")

    # Warnings
    _log_issues([], all_warnings)
    if args.strict and all_warnings:
        print("--strict: warnings treated as errors.", file=sys.stderr)
        sys.exit(1)

    # Write (atomic)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with open(fd, "wb") as f:
            f.write(xml_bytes)
        Path(tmp).replace(output_path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    print(f"Written: {output_path} ({len(xml_bytes)} bytes)")


def _validate(args) -> None:
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    if pos_account and not args.fund_dir:
        args.fund_dir = str(_DEFAULT_FUNDS_DIR / pos_account.lower())
    if pos_period and not args.period:
        args.period = pos_period
    if args.fund_dir and not args.period:
        args.period = _resolve_period(None)
    print("Validating input files...")
    schema_errors, _ = check_schema_files(args.schema_dir)
    if schema_errors:
        _log_issues(schema_errors, [])

    config, filing, holdings = _parse_inputs(args)
    print(f"  Parsed: {config.reg_name} / {filing.submission_type} {filing.rep_pd_end} / {len(holdings)} holdings")

    errors, warnings = validate_all(config, filing, holdings)
    _log_issues(errors, warnings)
    if errors:
        print(f"\nFAILED ({len(errors)} error(s)).")
        sys.exit(1)
    print(f"\nPASSED ({len(warnings)} warning(s)).")


def _enrich(args) -> None:
    from nport.bloomberg import enrich_holdings
    enrich_holdings(
        input_path=Path(args.input),
        output_path=Path(args.output),
        host=args.host,
        port=args.port,
        batch_size=args.batch_size,
    )


def _merge(args) -> None:
    """Merge positions CSV with a security master."""
    # Read positions CSV, mapping camelCase headers to snake_case
    positions = []
    with open(args.positions, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapped = {}
            for csv_key, value in row.items():
                field = _HOLDINGS_KEY_MAP.get(csv_key, csv_key)
                mapped[field] = value
            positions.append(mapped)

    master = SecurityMaster(args.security_master)
    enriched, warnings = merge_positions_with_master(positions, master)

    merge_errors = validate_after_merge(enriched)
    for e in merge_errors:
        print(f"  ERROR: {e}", file=sys.stderr)

    if merge_errors:
        sys.exit(1)

    if args.split:
        output_dir = Path(args.output)
        written = write_split_csv(enriched, output_dir)
        for w in warnings:
            print(f"  WARNING: {w}", file=sys.stderr)
        print(f"Written {len(written)} file(s) to {output_dir} ({len(enriched)} holdings)")
    else:
        output_path = Path(args.output)
        write_canonical_csv(enriched, output_path)
        for w in warnings:
            print(f"  WARNING: {w}", file=sys.stderr)
        print(f"Written: {output_path} ({len(enriched)} holdings)")


def _resolve_fund_dir(fund_dir: str, account: str | None) -> tuple[Path, str]:
    """Resolve fund directory and account name.

    If fund_dir contains fund_config.txt, use it directly.
    Otherwise look for fund_dir/<account_lower>/.
    Returns (resolved_fund_dir, account_name).
    """
    p = Path(fund_dir)
    if (p / "fund_config.txt").is_file():
        acct = (account or p.name).upper()
        return p, acct

    if not account:
        print("ERROR: --account is required when --fund-dir is a parent directory.", file=sys.stderr)
        sys.exit(1)

    child = p / account.lower()
    if not child.is_dir():
        print(f"ERROR: Fund directory not found: {child}", file=sys.stderr)
        sys.exit(1)
    return child, account.upper()


def _fund_accounts_for_period(period: str) -> list[str]:
    """Every fund subdir that has both fund_config.txt and this period's filing_data.txt."""
    if not _DEFAULT_FUNDS_DIR.is_dir():
        return []
    out = []
    for d in sorted(_DEFAULT_FUNDS_DIR.iterdir()):
        if (d.is_dir() and (d / "fund_config.txt").is_file()
                and (d / "filings" / period / "filing_data.txt").is_file()):
            out.append(d.name.upper())
    return out


def _ingest(args) -> None:
    """STEP 3 dispatcher: one fund (`nport build fdrs`) or every fund (`nport build`)."""
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    period = _resolve_period(pos_period or args.period)
    account = pos_account or args.account

    if account or args.fund_dir:
        _ingest_one(args)
        return

    # No fund named → build every fund that has this period's filing.
    accounts = _fund_accounts_for_period(period)
    if not accounts:
        print(f"ERROR: no funds have filings/{period}/filing_data.txt — run `nport masters` then `nport split` first.",
              file=sys.stderr)
        sys.exit(1)
    ok, failed = [], []
    for acct in accounts:
        sub = copy.copy(args)
        sub.pos, sub.account, sub.fund_dir, sub.output = [acct, period], None, None, None
        try:
            _ingest_one(sub)
            ok.append(acct)
        except SystemExit:
            failed.append(acct)
    print(f"\n  Built {len(ok)}/{len(accounts)} funds for {period}.")
    if failed:
        print(f"  Failed ({len(failed)}): {', '.join(failed)}\n"
              f"  Re-run e.g. `nport build {failed[0].lower()} {period} --verbose` to see why.", file=sys.stderr)
        sys.exit(1)


def _ingest_one(args) -> None:
    """Ingest custodian CSV → enriched holdings → N-PORT XML for ONE fund."""
    # 0. Resolve shorthand: `nport build <fund> [period]`
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    args.period = _resolve_period(pos_period or args.period)
    args.account = pos_account or args.account
    if not args.fund_dir and args.account:
        args.fund_dir = str(_DEFAULT_FUNDS_DIR / args.account.lower())
    if not args.fund_dir:
        print("ERROR: specify which fund, e.g. `nport build fdrs`.", file=sys.stderr)
        sys.exit(1)

    # 1. Parse custodian CSV (auto-located from period if not given)
    all_rows = parse_custodian_csv(_resolve_custodian(args.custodian, args.period))

    # 2. Resolve fund dir and account
    fund_dir, account = _resolve_fund_dir(args.fund_dir, args.account)

    # 3. Filter rows to this account
    grouped = filter_by_account(all_rows, account)
    account_rows = grouped.get(account, [])
    if not account_rows:
        available = sorted({r.account for r in all_rows})
        print(f"ERROR: No rows for account '{account}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Account {account}: {len(account_rows)} custodian rows")

    # 4. Transform + merge + validate
    enriched, messages = ingest_account(account_rows, fund_dir, args.period)

    # Log messages
    errors = [m for m in messages if "missing required field" in m]
    warnings = [m for m in messages if m not in errors]
    if args.verbose or errors:
        _log_issues(errors, warnings, "INGEST")

    if not enriched:
        print("ERROR: No holdings after transformation.", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Transformed: {len(enriched)} holdings")

    if args.dry_run:
        print(f"DRY RUN: {len(enriched)} holdings transformed for {account} ({args.period})")
        if errors:
            print(f"  {len(errors)} validation error(s) — see above.", file=sys.stderr)
        return

    # 5. Write split CSVs to filing period dir
    period_dir = fund_dir / "filings" / args.period
    written = write_split_csv(enriched, period_dir)
    if args.verbose:
        for wp in written:
            print(f"  Written: {wp}")

    # 6. Load back via standard pipeline
    try:
        loader = DataLoader(fund_dir)
        config = loader.load_config()
        filing = loader.load_filing(args.period)
        holdings = loader.load_holdings(args.period)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: parse error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"Loaded: {config.series_name} / {filing.submission_type} {filing.rep_pd_end} / {len(holdings)} holdings")

    # 7. Input validation
    input_errors, input_warnings = validate_all(config, filing, holdings)
    if input_errors:
        _log_issues(input_errors, [], "INPUT")
        sys.exit(1)

    # 8. Build XML
    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
    if args.verbose:
        print(f"Generated: {len(xml_bytes)} bytes")

    # 9. XSD validation
    if not args.skip_validation:
        xsd_errors = NportValidator(schema_dir=args.schema_dir).validate_xsd(xml_bytes)
        if xsd_errors:
            _log_issues(xsd_errors, [], "XSD")
            sys.exit(1)
        elif args.verbose:
            print("XSD validation passed")

    # 10. Write XML
    output_path = Path(args.output) if args.output else Path("output") / f"{account}_{args.period}.xml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with open(fd, "wb") as f:
            f.write(xml_bytes)
        Path(tmp).replace(output_path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise

    _log_issues([], input_warnings)
    print(f"Written: {output_path} ({len(xml_bytes)} bytes)")


def _schema(args) -> None:
    from nport.schema import print_schema
    print_schema()


def _pull(args) -> None:
    from nport.edgar import EdgarClient, extract_filing_summary

    client = EdgarClient("Corgi ETF Trust nport-tool@example.com")

    # Resolve CIK
    if args.ticker:
        cik = client.resolve_ticker_to_cik(args.ticker)
        if not cik:
            print(f"ERROR: Could not resolve ticker '{args.ticker}' to CIK.", file=sys.stderr)
            sys.exit(1)
        print(f"Resolved {args.ticker} -> CIK {cik}")
    else:
        cik = args.cik.zfill(10)

    if args.list_filings:
        filings = client.get_nport_filings(cik, count=args.count)
        if not filings:
            print("No N-PORT filings found.")
            return
        print(f"Recent N-PORT filings for CIK {cik}:")
        for f in filings:
            print(f"  {f.filing_date}  {f.form_type:<12}  {f.accession_number}  {f.primary_document}")
        return

    # Download latest
    xml_bytes, filing = client.download_latest_nport(cik)
    summary = extract_filing_summary(xml_bytes)
    print(f"Filing: {filing.form_type} {filing.filing_date} ({filing.accession_number})")
    print(f"  Fund: {summary['reg_name']} / {summary['series_name']}")
    print(f"  Period: {summary['rep_pd_end']}")
    print(f"  Holdings: {summary['holdings_count']}")
    print(f"  Net Assets: {summary['net_assets']}")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(xml_bytes)
        print(f"  Written: {output_path} ({len(xml_bytes)} bytes)")


def _update_masters(args) -> None:
    """Incrementally update security masters from custodian CSV."""
    # 0. Resolve shorthand: `nport masters [period] [fund]`
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    args.account = pos_account or args.account

    # 1. Parse custodian CSV (auto-located from period if not given)
    if args.custodian:
        custodian = Path(args.custodian)
        if not custodian.is_file():
            print(f"ERROR: Custodian CSV not found: {custodian}", file=sys.stderr)
            sys.exit(1)
    else:
        custodian = _resolve_custodian(None, _resolve_period(pos_period or getattr(args, "period", None)))
    all_rows = parse_custodian_csv(custodian)

    xml_dir = Path(args.xml_dir)
    fund_dir = Path(args.fund_dir)

    # 2. Determine which accounts to process
    grouped = filter_by_account(all_rows)
    if args.account:
        accounts = [args.account.upper()]
    elif args.all_accounts:
        accounts = sorted(grouped.keys())
    elif (fund_dir / "security_master.csv").is_file() or (fund_dir / "fund_config.txt").is_file():
        # Single fund dir — infer account from dir name
        accounts = [fund_dir.name.upper()]
    else:
        # Parent directory with no --account → default to all
        accounts = sorted(grouped.keys())

    # 3. Process each account
    for account in accounts:
        account_rows = grouped.get(account, [])
        if not account_rows:
            print(f"  {account}: no custodian rows, skipping")
            continue

        # Resolve fund dir
        if fund_dir.name.upper() == account:
            resolved_dir = fund_dir
        else:
            resolved_dir = fund_dir / account.lower()

        sm_path = resolved_dir / "security_master.csv"

        entries, headers, stats = update_security_master(account_rows, sm_path, xml_dir)

        label = f"{account}: Added {stats['added']}, removed {stats['removed']}, kept {stats['kept']}"

        if args.dry_run:
            print(f"  DRY RUN {label}")
        else:
            write_security_master(entries, headers, sm_path)
            print(f"  {label} -> {sm_path}")


_SECURITY_MASTER_PATH = Path("data/master/security_master.xlsx")
_FILING_MASTER_PATH = Path("data/master/filing_master.xlsx")


def _resolve_ap_orders(explicit: str | None, period: str) -> Path | None:
    """The AP order book CSV: explicit path, else any AP-order-format CSV in data/orders/
    (detected by header — the filename doesn't matter). None if there isn't one."""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            print(f"ERROR: AP order book CSV not found: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    orders_dir = Path("data/orders")
    auto = orders_dir / f"{period}_orders.csv"
    if auto.is_file():
        return auto
    if orders_dir.is_dir():
        for p in sorted(orders_dir.glob("*.csv")):
            try:
                with open(p, newline="", encoding="utf-8-sig") as f:
                    header = set(next(csv.reader(f), []))
                if {"Ticker", "Side", "Trade Date", "Notional"} <= header:
                    return p
            except (OSError, StopIteration):
                continue
    return None


_FUND_ACCOUNTING_DIR = Path("data/fund_accounting")
_MASTER_DIR = Path("data/master")


def _fnum(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _write_provenance_and_reconciliation(period, custodian_rows, ap_orders, eag) -> None:
    """Emit the traceability artifacts: a provenance manifest (every EagleSTAR-sourced
    cell -> source + as-of) and a reconciliation report (the cross-checks that must tie
    out before LIVE). Mirrors the source-of-truth matrix: each field has one writer; a
    second source only validates here, it never writes the filing."""
    from nport.ap_orders import flows_from_csv
    from nport.master_sheet import HoldingType, classify_holding

    _MASTER_DIR.mkdir(parents=True, exist_ok=True)
    pval_as_of = eag.as_of.get("pval", "")
    tb_as_of = (eag.as_of.get("realized_unreal_monthends") or [""])[-1]

    # ── Provenance manifest ──
    prov = _MASTER_DIR / f"provenance_{period}.csv"
    with open(prov, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["fund", "field", "source", "as_of", "value"])
        for (ticker, asset_id), fields in sorted(eag.derivatives.items()):
            for k, v in fields.items():
                w.writerow([ticker, f"{k}[{asset_id}]", "EagleSTAR PVal", pval_as_of, v])
        for ticker, fields in sorted(eag.filing.items()):
            for k, v in fields.items():
                w.writerow([ticker, k, "EagleSTAR TrialBalance", tb_as_of, v])

    # ── Reconciliation (X-CHECKs; never overwrites a filed cell) ──
    cust_net = {}
    cust_deriv = set()
    for r in custodian_rows:
        acct = r.account.upper()
        cust_net.setdefault(acct, _fnum(r.net_assets))
        if classify_holding(r) in (HoldingType.OPTION, HoldingType.SWAP):
            cust_deriv.add((acct, (r.stock_ticker or "").strip()))

    ap_flows = flows_from_csv(ap_orders, period) if ap_orders else {}
    recon = _MASTER_DIR / f"reconciliation_{period}.csv"
    flags = {"netAssets": 0, "flows": 0, "liabilities": 0, "deriv_unmatched": 0, "entity": 0}
    with open(recon, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["check", "fund", "source_a", "value_a", "source_b", "value_b", "diff", "flag"])

        # netAssets: custodian (writer) vs NAV (x-check). As-of differs (NAV ~06-24 vs period-end).
        for acct, cn in sorted(cust_net.items()):
            nav = eag.nav_net_assets.get(acct)
            if nav is None:
                continue
            diff = cn - nav
            flag = "REVIEW" if abs(diff) > max(1.0, 0.01 * abs(cn)) else ""
            if flag:
                flags["netAssets"] += 1
            w.writerow(["netAssets", acct, "custodian", f"{cn:.2f}", f"NAV@{pval_as_of}", f"{nav:.2f}", f"{diff:.2f}", flag])

        # flows: AP order book (writer) vs EagleSTAR TB (x-check).
        for acct in sorted(set(ap_flows) | set(eag.flows)):
            for mon in ("mon1", "mon2", "mon3"):
                for side in ("Sales", "Redemption"):
                    a = _fnum(ap_flows.get(acct, {}).get(f"{mon}{side}"))
                    b = _fnum(eag.flows.get(acct, {}).get(f"{mon}{side}"))
                    diff = a - b
                    flag = "REVIEW" if abs(diff) > max(1.0, 0.05 * max(abs(a), abs(b))) else ""
                    if flag:
                        flags["flows"] += 1
                    w.writerow([f"flow:{mon}{side}", acct, "AP_orders", f"{a:.2f}",
                                f"TB@{tb_as_of}", f"{b:.2f}", f"{diff:.2f}", flag])

        # liabilities: mapped amtPayOneYrOther vs TB TOTAL LIABILITIES.
        for ticker, total in sorted(eag.tb_total_liabs.items()):
            mapped = _fnum(eag.filing.get(ticker, {}).get("amtPayOneYrOther"))
            diff = mapped - total
            flag = "REVIEW" if abs(diff) > max(1.0, 0.01 * abs(total)) else ""
            if flag:
                flags["liabilities"] += 1
            w.writerow(["liabilities", ticker, "mapped_amtPay", f"{mapped:.2f}",
                        f"TB_total@{tb_as_of}", f"{total:.2f}", f"{diff:.2f}", flag])

        # derivative coverage: every custodian deriv has a PVal value, and vice versa.
        for acct, aid in sorted(cust_deriv - set(eag.derivatives)):
            flags["deriv_unmatched"] += 1
            w.writerow(["deriv_no_pval", acct, "custodian", aid, "EagleSTAR_PVal", "MISSING", "", "REVIEW"])
        for acct, aid in sorted(set(eag.derivatives) - cust_deriv):
            flags["deriv_unmatched"] += 1
            w.writerow(["pval_no_custodian", acct, "EagleSTAR_PVal", aid, "custodian", "MISSING", "", "REVIEW"])

        # entity->ticker: every custodian fund resolves through NAV.
        resolved = set(eag.entity_ticker.values())
        for acct in sorted(cust_net):
            if acct not in resolved:
                flags["entity"] += 1
                w.writerow(["entity_unresolved", acct, "custodian", acct, "NAV_NASDAQ", "MISSING", "", "REVIEW"])

    print(f"      provenance -> {prov.name}; reconciliation -> {recon.name}")
    summary = ", ".join(f"{k}={v}" for k, v in flags.items() if v)
    if summary:
        print(f"      ! reconciliation flags: {summary} (see {recon.name}; netAssets/flows gaps "
              f"include the {pval_as_of} vs period-end as-of difference)")
    else:
        print("      reconciliation clean.")


def _resolve_fund_accounting(explicit: str | None) -> Path | None:
    """The EagleSTAR export (.zip/.mbox): explicit path, else newest in
    data/fund_accounting/. None if there isn't one."""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            print(f"ERROR: fund-accounting export not found: {p}", file=sys.stderr)
            sys.exit(1)
        return p
    return eaglestar.resolve_export(_FUND_ACCOUNTING_DIR)


def _masters(args) -> None:
    """STEP 1: build BOTH master workbooks (security + filing) from the custodian."""
    _, pos_period = _split_positionals(getattr(args, "pos", None))
    period = _resolve_period(pos_period or getattr(args, "period", None))
    custodian = _resolve_custodian(args.custodian, period)
    if not custodian.is_file():
        print(f"ERROR: Custodian CSV not found: {custodian}", file=sys.stderr)
        sys.exit(1)
    ap_orders = _resolve_ap_orders(args.ap_orders, period)
    export = None if getattr(args, "no_fund_accounting", False) else \
        _resolve_fund_accounting(getattr(args, "fund_accounting", None))

    if args.dry_run:
        flows = f" + {ap_orders}" if ap_orders else " (no AP orders file)"
        eag = f" + EagleSTAR {export.name}" if export else " (no fund-accounting export)"
        print(f"  DRY RUN masters {period}:")
        print(f"    [1/2] security master  <- {custodian}{eag} -> {_SECURITY_MASTER_PATH}")
        print(f"    [2/2] filing master    <- {custodian}{flows}{eag} -> {_FILING_MASTER_PATH}")
        return

    eag = None
    if export:
        print(f"  Extracting EagleSTAR fund accounting from {export.name} (as-of {period}) ...")
        eag = eaglestar.load(export, period)
        as_of = eag.as_of.get("pval")
        print(f"      {len(eag.derivatives)} derivative unrealizedAppr, {len(eag.filing)} funds' "
              f"gains/liabilities (PVal/TB as-of {as_of}).")

    rows = parse_custodian_csv(custodian)
    try:
        stats = refresh_master(rows, _SECURITY_MASTER_PATH, Path("data/RealXMLs"), None,
                               formulas=True, overwrite_formulas=False,
                               deriv_values=eag.derivatives if eag else None)
    except PermissionError:
        print(f"ERROR: can't write {_SECURITY_MASTER_PATH} — close it in Excel and retry.", file=sys.stderr)
        sys.exit(1)
    print(f"  [1/2] security master: added {stats['added']}, removed {stats['removed']}, "
          f"kept {stats['kept']}, {stats['formulas']} Bloomberg formulas -> {_SECURITY_MASTER_PATH}")

    try:
        n = build_filing_master_from_custodian(custodian, period, _FILING_MASTER_PATH, ap_orders,
                                               fund_acct=eag.filing if eag else None)
    except PermissionError:
        print(f"ERROR: can't write {_FILING_MASTER_PATH} — close it in Excel and retry.", file=sys.stderr)
        sys.exit(1)
    flow_note = f"flows from {ap_orders.name}" if ap_orders else "no AP orders file — flows left 0"
    eag_note = " + EagleSTAR gains/liabilities" if eag else ""
    print(f"  [2/2] filing master: {n} funds ({flow_note}{eag_note}) -> {_FILING_MASTER_PATH}")

    if eag:
        _write_provenance_and_reconciliation(period, rows, ap_orders, eag)

    print("\n  Next: open BOTH workbooks on the Bloomberg machine, let them calculate, SAVE"
          " (keep .xlsx), then run `nport split`.")


def _split(args) -> None:
    """STEP 2: write every per-fund file from BOTH master workbooks."""
    _, pos_period = _split_positionals(getattr(args, "pos", None))
    period = _resolve_period(pos_period or getattr(args, "period", None))
    fund_dir = _DEFAULT_FUNDS_DIR
    verb = "DRY RUN" if args.dry_run else "Wrote"
    did = False

    if _SECURITY_MASTER_PATH.is_file():
        try:
            res = split_master(_SECURITY_MASTER_PATH, fund_dir, None, dry_run=args.dry_run)
        except PermissionError as e:
            print(f"ERROR: can't write a per-fund CSV — close it in Excel and retry ({e.filename}).", file=sys.stderr)
            sys.exit(1)
        print(f"  [1/2] security master: {verb} {len(res)} funds' security_master.csv")
        did = True
    else:
        print(f"  [1/2] security master: skipped — {_SECURITY_MASTER_PATH} not found (run `nport masters` first)")

    if _FILING_MASTER_PATH.is_file():
        try:
            res = split_filing_master(_FILING_MASTER_PATH, fund_dir, period, None, dry_run=args.dry_run)
        except PermissionError as e:
            print(f"ERROR: can't write a filing_data.txt — close it and retry ({e.filename}).", file=sys.stderr)
            sys.exit(1)
        print(f"  [2/2] filing master: {verb} {len(res)} funds' filing_data.txt ({period})")
        did = True
    else:
        print(f"  [2/2] filing master: skipped — {_FILING_MASTER_PATH} not found")

    if not did:
        sys.exit(1)
    if not args.dry_run:
        print("\n  Next: `nport build` (all funds) or `nport build <fund>` to generate the XML.")


def _build_master(args) -> None:
    """Refresh the one global master spreadsheet from the custodian CSV."""
    master_path = Path(args.master)
    fund_dir = Path(args.fund_dir)

    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    args.account = pos_account or args.account

    # One-time migration: seed the master from existing per-fund CSVs.
    if args.seed:
        custodian = Path(args.custodian) if args.custodian else (
            _resolve_custodian(None, _resolve_period(pos_period or getattr(args, "period", None)))
        )
        if args.dry_run:
            print(f"  DRY RUN seed master from {fund_dir}/*/security_master.csv -> {master_path}")
            return
        try:
            stats = seed_master_from_per_fund(fund_dir, custodian, master_path, formulas=not args.no_formulas)
        except PermissionError:
            print(f"ERROR: can't write {master_path} — close it in Excel and retry.", file=sys.stderr)
            sys.exit(1)
        print(f"  Seeded {stats['rows']} custodian rows ({stats.get('holdings', stats['rows'])} "
              f"holdings) from {stats['funds']} funds "
              f"({stats['formulas']} Bloomberg formulas) -> {master_path}")
        if stats.get("skipped"):
            print(f"  Skipped {len(stats['skipped'])} fund(s) not in the custodian: "
                  f"{', '.join(stats['skipped'])}")
        return

    if args.custodian:
        custodian = Path(args.custodian)
        if not custodian.is_file():
            print(f"ERROR: Custodian CSV not found: {custodian}", file=sys.stderr)
            sys.exit(1)
    else:
        custodian = _resolve_custodian(None, _resolve_period(pos_period or getattr(args, "period", None)))
    all_rows = parse_custodian_csv(custodian)

    accounts = None
    if args.account:
        accounts = [args.account.upper()]
    # --all and the default both mean "every account in the custodian"

    if args.dry_run:
        grouped = filter_by_account(all_rows)
        target = accounts or sorted(grouped)
        total = sum(len(grouped.get(a, [])) for a in target)
        print(f"  DRY RUN build-master: {len(target)} account(s), {total} custodian rows -> {master_path}")
        return

    try:
        stats = refresh_master(
            all_rows, master_path, Path(args.xml_dir), accounts,
            formulas=not args.no_formulas, overwrite_formulas=args.all_formulas,
        )
    except PermissionError:
        print(f"ERROR: can't write {master_path} — close it in Excel and retry.", file=sys.stderr)
        sys.exit(1)
    print(f"  Added {stats['added']}, removed {stats['removed']}, kept {stats['kept']}, "
          f"{stats['formulas']} Bloomberg formulas -> {master_path}")


def _split_master(args) -> None:
    """Regenerate per-fund security_master.csv files from the master workbook."""
    master_path = Path(args.master)
    if not master_path.is_file():
        print(f"ERROR: Master workbook not found: {master_path}", file=sys.stderr)
        sys.exit(1)
    fund_dir = Path(args.fund_dir)

    pos_account, _ = _split_positionals(getattr(args, "pos", None))
    account = pos_account or args.account

    accounts = [account.upper()] if account else None
    try:
        results = split_master(master_path, fund_dir, accounts, dry_run=args.dry_run)
    except PermissionError as e:
        print(f"ERROR: can't write a per-fund CSV — close it in Excel and retry ({e.filename}).", file=sys.stderr)
        sys.exit(1)
    if not results:
        print("  No matching accounts in master.")
        return
    verb = "DRY RUN" if args.dry_run else "Wrote"
    for acct, path, n in results:
        print(f"  {verb} {acct}: {n} rows -> {path}")


def _build_filing_master(args) -> None:
    """Build the per-period filing-returns workbook from the custodian + Bloomberg formulas."""
    master_path = Path(args.master)
    _, pos_period = _split_positionals(getattr(args, "pos", None))
    period = _resolve_period(pos_period or getattr(args, "period", None))
    custodian = Path(args.custodian) if args.custodian else _resolve_custodian(None, period)
    if not custodian.is_file():
        print(f"ERROR: Custodian CSV not found: {custodian}", file=sys.stderr)
        sys.exit(1)
    ap_orders = Path(args.ap_orders) if getattr(args, "ap_orders", None) else None
    if ap_orders and not ap_orders.is_file():
        print(f"ERROR: AP order book CSV not found: {ap_orders}", file=sys.stderr)
        sys.exit(1)
    if args.dry_run:
        flows_note = f", flows from {ap_orders}" if ap_orders else ""
        print(f"  DRY RUN build-filing-master {period}: from {custodian}{flows_note} -> {master_path}")
        return
    try:
        n = build_filing_master_from_custodian(custodian, period, master_path, ap_orders)
    except PermissionError:
        print(f"ERROR: can't write {master_path} — close it in Excel and retry.", file=sys.stderr)
        sys.exit(1)
    print(f"  Built filing master for {n} funds ({period}) -> {master_path}")
    print("  Open it on a Bloomberg terminal so rtn1-3 calculate, save, then `nport split-filing-master`.")


def _split_filing_master(args) -> None:
    """Write each fund's filing_data.txt from the filing master workbook."""
    master_path = Path(args.master)
    if not master_path.is_file():
        print(f"ERROR: Filing master not found: {master_path}", file=sys.stderr)
        sys.exit(1)
    fund_dir = Path(args.fund_dir)
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    period = _resolve_period(pos_period or getattr(args, "period", None))
    account = pos_account or args.account
    accounts = [account.upper()] if account else None
    try:
        results = split_filing_master(master_path, fund_dir, period, accounts, dry_run=args.dry_run)
    except PermissionError as e:
        print(f"ERROR: can't write a filing_data.txt — close it and retry ({e.filename}).", file=sys.stderr)
        sys.exit(1)
    if not results:
        print("  No matching funds in the filing master.")
        return
    verb = "DRY RUN" if args.dry_run else "Wrote"
    print(f"  {verb} {len(results)} filing_data.txt files ({period}).")


def _new_filing(args) -> None:
    """Create filing_data.txt template(s) for a new period."""
    # Resolve shorthand: `nport filing [period] [fund]`
    pos_account, pos_period = _split_positionals(getattr(args, "pos", None))
    args.account = pos_account or args.account
    period = _resolve_period(pos_period or args.period)
    fund_dir = Path(args.fund_dir)

    if not fund_dir.is_dir():
        print(f"ERROR: Fund directory not found: {fund_dir}", file=sys.stderr)
        sys.exit(1)

    # Determine which fund dirs to process
    if args.account:
        dirs = [fund_dir / args.account.lower()]
    elif (fund_dir / "fund_config.txt").is_file() or (fund_dir / "security_master.csv").is_file():
        # fund_dir is itself a fund directory
        dirs = [fund_dir]
    else:
        # Parent directory — process all subdirs that look like fund dirs
        dirs = sorted(
            d for d in fund_dir.iterdir()
            if d.is_dir() and (
                (d / "fund_config.txt").is_file()
                or (d / "security_master.csv").is_file()
            )
        )

    if not dirs:
        print(f"ERROR: No fund directories found in {fund_dir}", file=sys.stderr)
        sys.exit(1)

    for d in dirs:
        if not d.is_dir():
            print(f"  {d.name}: directory not found, skipping", file=sys.stderr)
            continue

        target = d / "filings" / period / "filing_data.txt"
        if target.exists():
            print(f"  {d.name}: filing_data.txt already exists for {period}, skipping")
            continue

        path = generate_filing_template(d, period)
        print(f"  {d.name}: created {path}")
        print("    -> Edit this file with totAssets, netAssets, returns, flows")


def _guide(args) -> None:
    """Print the step-by-step N-PORT filing guide."""
    print("""\
N-PORT Monthly Filing — 3 commands
==================================

Drop two files in, run three commands. (Period like 2026-06 is optional — the tool
uses the newest custodian file if you leave it off.)

DROP IN  (from US Bank / your AP order portal):
  data/custodian/2026-06_holdings.csv      ← US Bank monthly positions (all funds)
  data/orders/2026-06_orders.csv           ← AP creation/redemption order book (optional, for flows)

STEP 1 — Build the two master workbooks
  $ nport masters
  Builds data/master/security_master.xlsx (holdings reference data) and
         data/master/filing_master.xlsx   (returns, net assets, flows, B.3 risk).
  Then OPEN BOTH on the Bloomberg machine, let the =BDP() formulas calculate, and SAVE
  (keep them .xlsx). Bloomberg fills: stock LEI/ISIN/country, monthly returns, bond
  durations. Counterparties + LEIs on swaps/options are filled automatically.
  Only truly manual cells: option `delta`, swap `notionalAmt`/`unrealizedAppr`,
  and fund-accounting gains — type those into the workbooks before saving.

STEP 2 — Split the workbooks into per-fund files
  $ nport split
  Writes every fund's security_master.csv and filing_data.txt from the two workbooks.
  (Edit the workbooks, NOT the per-fund files — split overwrites them.)

STEP 3 — Generate the XML
  $ nport build            # every fund  ->  output/<TICKER>_2026-06.xml
  $ nport build fdrs       # just one fund
  Add --dry-run to validate without writing. Fix any reported field in the workbook,
  re-split, rebuild.

FILE IT
  Review the XML in output/. When it's right, set liveTestFlag=LIVE in each
  filing_data.txt (or the filing master before splitting) and run `nport build` again,
  then upload to EDGAR.

TIP: activate the venv once so you can drop the `uv run` prefix:
     macOS/Linux:  source .venv/bin/activate
     Windows:      .venv\\Scripts\\Activate.ps1
TIP: `nport guide` reprints this. `nport --help` lists every command (advanced ones too).\
""")


def _check_schema(args) -> None:
    print("Checking schema files...")
    errors, warnings = check_schema_files(args.schema_dir)
    if errors:
        _log_issues(errors, [])
    else:
        print("  All schema files present.")

    print("Checking for updates...")
    newer, w = check_for_schema_update(force=args.force)
    warnings.extend(w)
    print(f"  {'NEW VERSION: v' + newer if newer else f'v{CURRENT_SCHEMA_VERSION} is current.'}")
    _log_issues([], warnings)
