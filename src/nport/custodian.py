"""Custodian CSV parser and transformer for N-PORT filings.

Reads US Bank custodian CSVs, classifies each row by holding type,
parses type-specific string formats (option names, treasury names,
swap tickers), and transforms into snake_case holding dicts compatible
with the existing merge/validate/build pipeline.
"""

import calendar
import csv
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

from lxml import etree

from nport.data_loader import merge_positions_with_master, validate_after_merge
from nport.security_master import SecurityMaster

logger = logging.getLogger(__name__)


# ── Data structures ───────────────────────────────────────────


class HoldingType(Enum):
    EQUITY = "equity"
    OPTION = "option"
    SWAP = "swap"
    TREASURY = "treasury"
    MONEY_MARKET = "money_market"
    CASH = "cash"


@dataclass
class CustodianRow:
    date: str
    account: str
    stock_ticker: str
    cusip: str
    security_name: str
    shares: str
    price: str
    market_value: str
    weightings: str
    net_assets: str
    shares_outstanding: str
    creation_units: str
    money_market_flag: str


@dataclass
class ParsedOption:
    underlying: str
    exp_dt: str  # YYYY-MM-DD
    exercise_price: str
    put_or_call: str  # "Call" or "Put"


@dataclass
class ParsedTreasury:
    annualized_rt: str
    maturity_dt: str  # YYYY-MM-DD
    coupon_kind: str  # "Fixed"


@dataclass
class ParsedSwap:
    ref_cusip: str
    termination_dt: str  # YYYY-MM-DD
    direction: str  # "Long" or "Short"
    counterparty_abbrev: str


# ── Constants ─────────────────────────────────────────────────


_UNDERLYING_INDEX_MAP = {
    "SPY": ("S&P 500 Index", "SPX"),
    "QQQ": ("NASDAQ 100 Index", "NDX"),
    "IWM": ("Russell 2000 Index", "RTY"),
    "EEM": ("MSCI Emerging Markets Index", "MXEF"),
    "EFA": ("MSCI EAFE Index", "MXEA"),
}

_US_TREASURY_LEI = "254900HROIFWPRGM1V77"

_NAME_MAX_LEN = 30  # XSD schema max length for <name>

_TRAILING_DATE_RE = re.compile(r"\s+\d{2}/\d{2}/\d{4}$")

_NS = {"n": "http://www.sec.gov/edgar/nport"}

# Foreign stock country mapping (from SEC filings + public records)
FOREIGN_COUNTRY = {
    # Netherlands
    "AER": "NL", "ASML": "NL", "NBIS": "NL", "NXP": "NL",
    "CMBT": "BE",
    # Israel
    "CAMT": "IL", "CGNT": "IL", "CHKP": "IL", "CLBT": "IL",
    "CYBR": "IL", "GLBE": "IL", "INM": "IL", "INMD": "IL",
    "MNDY": "IL", "RDWR": "IL", "TEVA": "IL", "WIX": "IL",
    # Cayman Islands
    "NU": "KY", "XP": "KY", "SE": "KY", "GRAB": "KY",
    "CANG": "KY", "MNSO": "KY", "ARQQ": "KY", "BTBT": "KY",
    "BLSH": "KY", "BRSL": "KY", "AMBA": "KY", "AS": "KY",
    "DDL": "KY",
    # Bermuda
    "CCL": "BM",
    # Other
    "ASC": "MH", "FLUT": "IE", "RPRX": "GB", "BIRK": "JE",
    "ALC": "CH", "BTDR": "KY", "CDRO": "LU", "SPOT": "LU",
    "SHOP": "CA", "WCN": "CA", "TEAM": "AU",
}

# Security master CSV header sets (camelCase, matching existing files)
EQUITY_HEADERS = [
    "name", "lei", "title", "cusip", "isin", "ticker",
    "invCountry", "assetCat", "issuerCat",
]

OPTION_HEADERS = [
    "name", "lei", "title", "cusip", "isin", "ticker",
    "invCountry", "assetCat", "issuerCat",
    "derivCat", "counterpartyName", "counterpartyLei",
    "putOrCall", "writtenOrPur", "exercisePrice", "exercisePriceCurCd",
    "expDt", "delta",
    "refInstType", "refIndexName", "refIndexIdentifier",
]

SWAP_HEADERS = [
    "name", "lei", "title", "cusip", "isin", "ticker",
    "invCountry", "assetCat", "issuerCat",
    "derivCat", "counterpartyName", "counterpartyLei",
    "swapFlag", "terminationDt", "notionalAmt", "swapCurCd",
    "unrealizedAppr", "valUSD", "pctVal",
    "recFixedOrFloating", "recDesc",
    "pmntFixedOrFloating", "pmntFloatingRtIndex", "pmntFloatingRtSpread",
    "pmntPmntAmt", "pmntCurCdLeg", "pmntRateTenor", "pmntRateUnit",
    "refInstType", "refIssuerName", "refIssueTitle",
    "refCusip", "refIsin", "refTicker",
]


# ── XML reference data ────────────────────────────────────────


def load_xml_reference(xml_dir: Path) -> dict[str, dict[str, str]]:
    """Extract holding reference data from real N-PORT XML files."""
    ref: dict[str, dict[str, str]] = {}

    for xml_path in xml_dir.glob("*.xml"):
        tree = etree.parse(str(xml_path))
        for sec in tree.findall(".//n:invstOrSec", _NS):
            cusip = sec.findtext("n:cusip", "", _NS).strip()
            name = sec.findtext("n:name", "", _NS).strip()
            lei = sec.findtext("n:lei", "", _NS).strip()
            title = sec.findtext("n:title", "", _NS).strip()
            country = sec.findtext("n:invCountry", "", _NS).strip()
            asset_cat = sec.findtext("n:assetCat", "", _NS).strip()
            issuer_cat = sec.findtext("n:issuerCat", "", _NS).strip()

            isin, ticker = "", ""
            ids = sec.find("n:identifiers", _NS)
            if ids is not None:
                ie = ids.find("n:isin", _NS)
                if ie is not None:
                    isin = ie.get("value", "")
                te = ids.find("n:ticker", _NS)
                if te is not None:
                    ticker = te.get("value", "")

            entry = {
                "name": name, "lei": lei, "title": title, "cusip": cusip,
                "isin": isin, "ticker": ticker, "inv_country": country,
                "asset_cat": asset_cat, "issuer_cat": issuer_cat,
            }
            if cusip and cusip != "N/A":
                ref[cusip] = entry
            if ticker:
                ref[f"T:{ticker}"] = entry

    return ref


# ── Security master entry builders ────────────────────────────
# These produce dicts with camelCase keys matching the CSV headers.


def build_equity_entry(
    ticker: str, name: str, cusip: str, ref: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Build a security master entry for an equity."""
    xml_cusip = cusip if cusip[0].isdigit() else "N/A"
    hit = ref.get(cusip) or ref.get(f"T:{ticker}")

    if hit:
        return {
            "name": hit.get("name", name)[:30],
            "lei": hit.get("lei", "N/A"),
            "title": hit.get("title", name),
            "cusip": xml_cusip,
            "isin": hit.get("isin", ""),
            "ticker": ticker,
            "invCountry": hit.get("inv_country", "US"),
            "assetCat": "EC",
            "issuerCat": "CORP",
        }

    if cusip[0].isalpha():
        country = FOREIGN_COUNTRY.get(ticker, "US")
    else:
        country = "US"

    return {
        "name": name[:30],
        "lei": "N/A",
        "title": name,
        "cusip": xml_cusip,
        "isin": "",
        "ticker": ticker,
        "invCountry": country,
        "assetCat": "EC",
        "issuerCat": "CORP",
    }


def build_mm_entry(ref: dict[str, dict[str, str]]) -> dict[str, str]:
    """Build security master entry for FGXXX money market fund."""
    hit = ref.get("31846V336") or ref.get("T:FGXXX")
    return {
        "name": (hit or {}).get("name", "First American Government Obli"),
        "lei": (hit or {}).get("lei", "549300R5MYM6VZF1RM44"),
        "title": "First American Government Obligations Fund",
        "cusip": "31846V336",
        "isin": (hit or {}).get("isin", "US31846V3362"),
        "ticker": "FGXXX",
        "invCountry": "US",
        "assetCat": "STIV",
        "issuerCat": "RF",
    }


def build_option_entry(row: CustodianRow) -> dict[str, str]:
    """Build a security master entry for an option position."""
    opt = parse_option_name(row.security_name)
    option_id = _generate_option_id(opt)
    shares = float(row.shares)
    idx = _UNDERLYING_INDEX_MAP.get(opt.underlying, ("", ""))
    return {
        "name": row.security_name[:30],
        "lei": "N/A",
        "title": row.security_name,
        "cusip": "N/A",
        "isin": "",
        "ticker": option_id,
        "invCountry": "US",
        "assetCat": "DE",
        "issuerCat": "CORP",
        "derivCat": "OPT",
        "counterpartyName": "",
        "counterpartyLei": "",
        "putOrCall": opt.put_or_call,
        "writtenOrPur": "Purchased" if shares >= 0 else "Written",
        "exercisePrice": opt.exercise_price,
        "exercisePriceCurCd": "USD",
        "expDt": opt.exp_dt,
        "delta": "",
        "refInstType": "indexBasket",
        "refIndexName": idx[0],
        "refIndexIdentifier": idx[1],
    }


def build_swap_entry(row: CustodianRow) -> dict[str, str]:
    """Build a security master entry for a swap position."""
    swap = parse_swap_ticker(row.stock_ticker)
    ref_issuer, _ = _parse_swap_security_name(row.security_name)
    return {
        "name": "N/A",
        "lei": "N/A",
        "title": row.security_name,
        "cusip": "N/A",
        "isin": "",
        "ticker": row.stock_ticker,
        "invCountry": "US",
        "assetCat": "DE",
        "issuerCat": "OTHER",
        "derivCat": "SWP",
        "counterpartyName": "",
        "counterpartyLei": "",
        "swapFlag": "Y",
        "terminationDt": swap.termination_dt,
        "notionalAmt": "",
        "swapCurCd": "USD",
        "unrealizedAppr": "",
        "valUSD": "",
        "pctVal": "",
        "recFixedOrFloating": "",
        "recDesc": "",
        "pmntFixedOrFloating": "",
        "pmntFloatingRtIndex": "",
        "pmntFloatingRtSpread": "",
        "pmntPmntAmt": "",
        "pmntCurCdLeg": "",
        "pmntRateTenor": "",
        "pmntRateUnit": "",
        "refInstType": "otherRefInst",
        "refIssuerName": ref_issuer,
        "refIssueTitle": ref_issuer,
        "refCusip": swap.ref_cusip,
        "refIsin": "",
        "refTicker": "",
    }


def build_treasury_entry(row: CustodianRow) -> dict[str, str]:
    """Build a security master entry for a treasury position."""
    return {
        "name": row.security_name[:30],
        "lei": _US_TREASURY_LEI,
        "title": row.security_name,
        "cusip": row.cusip,
        "isin": "",
        "ticker": "",
        "invCountry": "US",
        "assetCat": "DBT",
        "issuerCat": "UST",
    }


# ── Lookup key logic ──────────────────────────────────────────


def _sm_lookup_key(holding_type: HoldingType, row: CustodianRow) -> str | None:
    """Determine the security master lookup key for a custodian row."""
    if holding_type == HoldingType.CASH:
        return None
    if holding_type == HoldingType.OPTION:
        opt = parse_option_name(row.security_name)
        return _generate_option_id(opt)
    if holding_type == HoldingType.SWAP:
        return row.stock_ticker
    if holding_type == HoldingType.EQUITY:
        # CINS (foreign CUSIPs starting with a letter) → use ticker
        if row.cusip and row.cusip[0].isdigit():
            return row.cusip
        return row.stock_ticker
    if holding_type == HoldingType.TREASURY:
        return row.cusip
    if holding_type == HoldingType.MONEY_MARKET:
        return row.cusip
    return None


def _sm_entry_key(entry: dict[str, str]) -> str:
    """Extract the lookup key from an existing security master entry.

    Uses cusip for equities/treasuries/MM, ticker for options/swaps/CINS.
    """
    cusip = entry.get("cusip", "")
    ticker = entry.get("ticker", "")
    asset_cat = entry.get("assetCat", "")
    deriv_cat = entry.get("derivCat", "")

    # Options and swaps are always keyed by ticker
    if deriv_cat in ("OPT", "SWP"):
        return ticker
    # CINS equities (cusip is N/A) — use ticker
    if cusip in ("N/A", ""):
        return ticker
    return cusip


# ── Incremental security master update ────────────────────────


def update_security_master(
    rows: list[CustodianRow],
    sm_path: Path,
    xml_dir: Path,
) -> tuple[list[dict[str, str]], list[str], dict[str, int]]:
    """Incrementally update a security master from custodian rows.

    Existing entries matched by key are never modified (preserves
    counterparty, delta, LEI, swap P&L, etc.). New positions are added
    with auto-populated fields. Positions no longer in the custodian are
    removed.

    Returns (updated_entries, headers, stats) where stats has keys
    ``added``, ``removed``, ``kept``.
    """
    # Load XML reference data for auto-populating new equities
    ref: dict[str, dict[str, str]] = {}
    if xml_dir.is_dir():
        ref = load_xml_reference(xml_dir)

    # Read existing security master
    existing: dict[str, dict[str, str]] = {}  # key → raw CSV row dict
    headers: list[str] = []
    if sm_path.is_file():
        with open(sm_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            for row in reader:
                key = _sm_entry_key(row)
                if key:
                    existing[key] = dict(row)

    # Classify custodian rows and determine expected keys
    wanted: dict[str, dict[str, str]] = {}  # key → new entry (only used if not in existing)
    seen_cusips: set[str] = set()
    has_options = False
    has_swaps = False

    for row in rows:
        ht = classify_holding(row)
        key = _sm_lookup_key(ht, row)
        if key is None:
            continue

        if ht == HoldingType.EQUITY:
            if row.cusip in seen_cusips:
                continue
            seen_cusips.add(row.cusip)
            if key not in wanted:
                wanted[key] = build_equity_entry(row.stock_ticker, row.security_name, row.cusip, ref)
        elif ht == HoldingType.MONEY_MARKET:
            if key not in wanted:
                wanted[key] = build_mm_entry(ref)
        elif ht == HoldingType.OPTION:
            has_options = True
            if key not in wanted:
                wanted[key] = build_option_entry(row)
        elif ht == HoldingType.SWAP:
            has_swaps = True
            if key not in wanted:
                wanted[key] = build_swap_entry(row)
        elif ht == HoldingType.TREASURY:
            if key not in wanted:
                wanted[key] = build_treasury_entry(row)

    # Determine headers — preserve existing, expand if new types appear
    if not headers:
        # No existing file — build from scratch
        headers = list(EQUITY_HEADERS)
    if has_options:
        for h in OPTION_HEADERS:
            if h not in headers:
                headers.append(h)
    if has_swaps:
        for h in SWAP_HEADERS:
            if h not in headers:
                headers.append(h)

    # Build result: keep existing entries that are still wanted, add new ones
    result: list[dict[str, str]] = []
    stats = {"added": 0, "removed": 0, "kept": 0}

    for key in wanted:
        if key in existing:
            result.append(existing[key])
            stats["kept"] += 1
        else:
            result.append(wanted[key])
            stats["added"] += 1

    # Count removed
    for key in existing:
        if key not in wanted:
            stats["removed"] += 1

    return result, headers, stats


def write_security_master(
    entries: list[dict[str, str]], headers: list[str], path: Path,
) -> None:
    """Write security master entries to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry)


# ── CSV parsing ───────────────────────────────────────────────


def parse_custodian_csv(path: Path) -> list[CustodianRow]:
    """Read all rows from a US Bank custodian CSV file."""
    rows: list[CustodianRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(CustodianRow(
                date=row.get("Date", ""),
                account=row.get("Account", ""),
                stock_ticker=row.get("StockTicker", ""),
                cusip=row.get("CUSIP", ""),
                security_name=row.get("SecurityName", ""),
                shares=row.get("Shares", ""),
                price=row.get("Price", ""),
                market_value=row.get("MarketValue", ""),
                weightings=row.get("Weightings", ""),
                net_assets=row.get("NetAssets", ""),
                shares_outstanding=row.get("SharesOutstanding", ""),
                creation_units=row.get("CreationUnits", ""),
                money_market_flag=row.get("MoneyMarketFlag", ""),
            ))
    return rows


def filter_by_account(
    rows: list[CustodianRow], account: str | None = None,
) -> dict[str, list[CustodianRow]]:
    """Group rows by account. If account given, return only that key."""
    grouped: dict[str, list[CustodianRow]] = {}
    for row in rows:
        grouped.setdefault(row.account, []).append(row)
    if account:
        key = account.upper()
        return {key: grouped.get(key, [])}
    return grouped


# ── Classification ────────────────────────────────────────────


def classify_holding(row: CustodianRow) -> HoldingType:
    """Detect holding type from custodian row fields."""
    if row.stock_ticker == "Cash&Other":
        return HoldingType.CASH
    if row.money_market_flag == "Y" and row.stock_ticker != "Cash&Other":
        return HoldingType.MONEY_MARKET
    if "-TRS-" in row.stock_ticker:
        return HoldingType.SWAP
    name = row.security_name.rstrip()
    if name.endswith(" C") or name.endswith(" P"):
        return HoldingType.OPTION
    if "United States Treasury" in row.security_name:
        return HoldingType.TREASURY
    return HoldingType.EQUITY


# ── String parsers ────────────────────────────────────────────


def parse_option_name(security_name: str) -> ParsedOption:
    """Parse option SecurityName.

    Format: ``SPY 04/30/2027 143.73 C``
    Returns ParsedOption with underlying, exp_dt, exercise_price, put_or_call.
    """
    parts = security_name.strip().rsplit(" ", 3)
    if len(parts) != 4:
        raise ValueError(f"Cannot parse option name: '{security_name}'")
    underlying, date_str, price_str, pc = parts
    exp_dt = datetime.strptime(date_str, "%m/%d/%Y").strftime("%Y-%m-%d")
    put_or_call = "Call" if pc == "C" else "Put"
    return ParsedOption(
        underlying=underlying,
        exp_dt=exp_dt,
        exercise_price=price_str,
        put_or_call=put_or_call,
    )


def parse_treasury_name(security_name: str) -> ParsedTreasury:
    """Parse treasury SecurityName.

    Format: ``United States Treasury Note/Bond 0.5% 04/30/2027``
    Returns ParsedTreasury with annualized_rt, maturity_dt, coupon_kind.
    """
    m = re.search(r"(\d+(?:\.\d+)?)%\s+(\d{2}/\d{2}/\d{4})", security_name)
    if not m:
        raise ValueError(f"Cannot parse treasury name: '{security_name}'")
    rate = m.group(1)
    maturity_dt = datetime.strptime(m.group(2), "%m/%d/%Y").strftime("%Y-%m-%d")
    return ParsedTreasury(
        annualized_rt=rate,
        maturity_dt=maturity_dt,
        coupon_kind="Fixed",
    )


def parse_swap_ticker(stock_ticker: str) -> ParsedSwap:
    """Parse swap StockTicker.

    Formats::

        02079K305-TRS-05/31/27-L-CANT   (with counterparty)
        218946101-TRS-01/19/28-L         (without counterparty)

    Returns ParsedSwap with ref_cusip, termination_dt, direction, counterparty_abbrev.
    """
    parts = stock_ticker.split("-TRS-")
    if len(parts) != 2:
        raise ValueError(f"Cannot parse swap ticker: '{stock_ticker}'")
    ref_cusip = parts[0]
    segments = parts[1].split("-")
    if len(segments) == 3:
        date_str, direction_code, counterparty = segments
    elif len(segments) == 2:
        date_str, direction_code = segments
        counterparty = ""
    else:
        raise ValueError(f"Cannot parse swap ticker suffix: '{parts[1]}'")
    termination_dt = datetime.strptime(date_str, "%m/%d/%y").strftime("%Y-%m-%d")
    direction = "Long" if direction_code == "L" else "Short"
    return ParsedSwap(
        ref_cusip=ref_cusip,
        termination_dt=termination_dt,
        direction=direction,
        counterparty_abbrev=counterparty,
    )


def _parse_swap_security_name(security_name: str) -> tuple[str, str]:
    """Parse swap SecurityName for ref_issuer_name.

    Formats::

        ALPHABET INC.-SWAP-CANT-L       → ("ALPHABET INC.", "CANT")
        CORGI ETF TR SWAP CS            → ("CORGI ETF TR", "CS")

    Returns (ref_issuer_name, counterparty_abbrev).
    """
    # Try hyphenated format first: ISSUER-SWAP-CP-DIR
    if "-SWAP-" in security_name:
        parts = security_name.split("-SWAP-")
        ref_issuer = parts[0]
        suffix = parts[1]  # "CANT-L" or "CANT-S"
        cp = suffix.rsplit("-", 1)[0] if "-" in suffix else suffix
        return ref_issuer, cp

    # Try space-separated format: ISSUER SWAP CP
    if " SWAP " in security_name:
        parts = security_name.split(" SWAP ")
        ref_issuer = parts[0]
        cp = parts[1].strip()
        return ref_issuer, cp

    return security_name, ""


# ── Transformation ────────────────────────────────────────────


def _common_fields(row: CustodianRow) -> dict[str, str]:
    """Build dict of fields common to all holding types."""
    shares = float(row.shares)
    pct = row.weightings.replace("%", "").strip()
    return {
        "name": row.security_name[:_NAME_MAX_LEN],
        "title": row.security_name,
        "cur_cd": "USD",
        "val_usd": row.market_value,
        "pct_val": pct,
        "payoff_profile": "Long" if shares >= 0 else "Short",
        "is_restricted_sec": "N",
        "is_cash_collateral": "N",
        "is_non_cash_collateral": "N",
        "is_loan_by_fund": "N",
    }


def _generate_option_id(opt: ParsedOption) -> str:
    """Generate a unique internal identifier for an option position."""
    pc = "C" if opt.put_or_call == "Call" else "P"
    date_part = opt.exp_dt.replace("-", "")
    return f"{opt.underlying}-{pc}{opt.exercise_price}-{date_part}"


def transform_to_holding_dict(
    row: CustodianRow, holding_type: HoldingType,
) -> dict[str, str]:
    """Transform a CustodianRow into a snake_case holding dict.

    The returned dict has the same field names as ``models.Holding``
    and is ready for ``merge_positions_with_master()``.
    """
    d = _common_fields(row)
    shares = float(row.shares)

    if holding_type == HoldingType.EQUITY:
        # CINS numbers (foreign CUSIPs starting with a letter) → N/A in filing
        cusip = row.cusip if row.cusip and row.cusip[0].isdigit() else "N/A"
        d.update({
            "cusip": cusip,
            "ticker": row.stock_ticker,
            "balance": row.shares,
            "units": "NS",
            "asset_cat": "EC",
            "issuer_cat": "CORP",
            "fair_val_level": "1",
        })

    elif holding_type == HoldingType.OPTION:
        opt = parse_option_name(row.security_name)
        option_id = _generate_option_id(opt)
        d.update({
            "cusip": "N/A",
            "ticker": option_id,
            "balance": str(abs(shares)),
            "units": "NC",
            "asset_cat": "DE",
            "issuer_cat": "CORP",
            "fair_val_level": "2",
            "deriv_cat": "OPT",
            "put_or_call": opt.put_or_call,
            "exercise_price": opt.exercise_price,
            "exercise_price_cur_cd": "USD",
            "exp_dt": opt.exp_dt,
            "written_or_pur": "Purchased" if shares >= 0 else "Written",
            "payoff_profile": "Long" if shares >= 0 else "Short",
            "ref_inst_type": "indexBasket",
            "other_desc": "USER DEFINED",
            "other_value": option_id,
        })
        idx = _UNDERLYING_INDEX_MAP.get(opt.underlying)
        if idx:
            d["ref_index_name"] = idx[0]
            d["ref_index_identifier"] = idx[1]

    elif holding_type == HoldingType.SWAP:
        swap = parse_swap_ticker(row.stock_ticker)
        ref_issuer, _ = _parse_swap_security_name(row.security_name)
        # Swap val_usd/pct_val/notional/unrealized come from fund accounting
        # via the security master — not derivable from the custodian CSV.
        d.update({
            "name": "N/A",
            "lei": "N/A",
            "cusip": "N/A",
            "ticker": row.stock_ticker,
            "balance": "1",
            "units": "NC",
            "val_usd": "",
            "pct_val": "",
            "payoff_profile": "N/A",
            "asset_cat": "DE",
            "issuer_cat": "OTHER",
            "issuer_conditional_desc": "N/A",
            "fair_val_level": "2",
            "inv_country": "US",
            "deriv_cat": "SWP",
            "swap_flag": "Y",
            "termination_dt": swap.termination_dt,
            "notional_amt": "",
            "swap_cur_cd": "USD",
            "unrealized_appr": "",
            "ref_inst_type": "otherRefInst",
            "ref_issuer_name": ref_issuer,
            "ref_issue_title": ref_issuer,
            "ref_cusip": swap.ref_cusip,
            "other_desc": "USER DEFINED",
            "other_value": row.stock_ticker,
        })

    elif holding_type == HoldingType.TREASURY:
        trs = parse_treasury_name(row.security_name)
        d.update({
            "cusip": row.cusip,
            "ticker": "",
            "balance": row.shares,
            "units": "PA",
            "asset_cat": "DBT",
            "issuer_cat": "UST",
            "fair_val_level": "2",
            "inv_country": "US",
            "lei": _US_TREASURY_LEI,
            "maturity_dt": trs.maturity_dt,
            "annualized_rt": trs.annualized_rt,
            "coupon_kind": trs.coupon_kind,
            "is_default": "N",
            "are_intrst_pmnts_in_arrs": "N",
            "is_paid_kind": "N",
        })

    elif holding_type == HoldingType.MONEY_MARKET:
        # Strip trailing maturity date from fund name
        clean_name = _TRAILING_DATE_RE.sub("", row.security_name)
        d.update({
            "name": clean_name[:_NAME_MAX_LEN],
            "title": clean_name,
            "cusip": row.cusip,
            "ticker": row.stock_ticker,
            "balance": row.shares,
            "units": "NS",
            "asset_cat": "STIV",
            "issuer_cat": "RF",
            "fair_val_level": "1",
        })

    return d


# ── Filing template generation ─────────────────────────────────


def _period_end_date(period: str) -> str:
    """Return the last day of a YYYY-MM period as YYYY-MM-DD."""
    year, month = int(period[:4]), int(period[5:7])
    last_day = calendar.monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-{last_day:02d}"


_FRESH_TEMPLATE = """\
# TODO: Update totAssets, netAssets, returns, flows for {period}

# Submission
submissionType=NPORT-P
liveTestFlag=TEST
repPdEnd={end_date}
repPdDate={end_date}
isFinalFiling=N
dateSigned=YYYY-MM-DD

# Fund Financials (from fund accounting)
totAssets=0
totLiabs=0
netAssets=0

# Balance Sheet Items (usually 0 for ETFs)
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

# Returns (monthly class returns; N/A if not applicable)
rtn1=N/A
rtn2=N/A
rtn3=N/A
netRealizedGainMon1=0
netUnrealizedApprMon1=0
netRealizedGainMon2=0
netUnrealizedApprMon2=0
netRealizedGainMon3=0
netUnrealizedApprMon3=0

# Flows (creations/redemptions/reinvestments per month)
mon1Sales=0
mon1Redemption=0
mon1Reinvestment=0
mon2Sales=0
mon2Redemption=0
mon2Reinvestment=0
mon3Sales=0
mon3Redemption=0
mon3Reinvestment=0

# Designated Index
nameDesignatedIndex=N/A
indexIdentifier=N/A
"""


def generate_filing_template(
    fund_dir: Path,
    period: str,
) -> Path:
    """Create a filing_data.txt template for a new period.

    If a previous filing exists, copies it with dates updated and
    returns/flows zeroed out. Otherwise creates a fresh template with
    all required fields.

    Returns the path to the created file.
    """
    filings_dir = fund_dir / "filings"
    target_dir = filings_dir / period
    target_path = target_dir / "filing_data.txt"

    if target_path.exists():
        return target_path  # caller checks and skips

    end_date = _period_end_date(period)

    # Try to find the most recent previous filing
    prev_path = _find_previous_filing(filings_dir, period)

    target_dir.mkdir(parents=True, exist_ok=True)

    if prev_path:
        _copy_with_updates(prev_path, target_path, period, end_date)
    else:
        target_path.write_text(
            _FRESH_TEMPLATE.format(period=period, end_date=end_date)
        )

    return target_path


def _find_previous_filing(filings_dir: Path, current_period: str) -> Path | None:
    """Find the most recent filing_data.txt before current_period."""
    if not filings_dir.is_dir():
        return None

    candidates = []
    for p in filings_dir.iterdir():
        if p.is_dir() and p.name != current_period:
            fd = p / "filing_data.txt"
            if fd.is_file():
                candidates.append(fd)

    if not candidates:
        return None

    # Sort by directory name (YYYY-MM) descending, take most recent
    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    return candidates[0]


# Keys that should be zeroed when copying from a previous period
_ZERO_KEYS = {
    "rtn1", "rtn2", "rtn3",
    "netRealizedGainMon1", "netUnrealizedApprMon1",
    "netRealizedGainMon2", "netUnrealizedApprMon2",
    "netRealizedGainMon3", "netUnrealizedApprMon3",
    "mon1Sales", "mon1Redemption", "mon1Reinvestment",
    "mon2Sales", "mon2Redemption", "mon2Reinvestment",
    "mon3Sales", "mon3Redemption", "mon3Reinvestment",
}

_RETURN_KEYS = {"rtn1", "rtn2", "rtn3"}


def _copy_with_updates(
    src: Path, dst: Path, period: str, end_date: str,
) -> None:
    """Copy a filing_data.txt, updating dates and zeroing returns/flows."""
    lines = src.read_text().splitlines()
    out: list[str] = []
    out.append(f"# TODO: Update totAssets, netAssets, returns, flows for {period}")

    for line in lines:
        stripped = line.strip()

        # Skip existing TODO comments from previous copies
        if stripped.startswith("# TODO:"):
            continue

        # Update date keys
        if stripped.startswith("repPdEnd="):
            out.append(f"repPdEnd={end_date}")
            continue
        if stripped.startswith("repPdDate="):
            out.append(f"repPdDate={end_date}")
            continue
        if stripped.startswith("dateSigned="):
            out.append("dateSigned=YYYY-MM-DD")
            continue

        # Zero out returns/flows
        eq_pos = stripped.find("=")
        if eq_pos > 0 and not stripped.startswith("#"):
            key = stripped[:eq_pos]
            if key in _ZERO_KEYS:
                value = "N/A" if key in _RETURN_KEYS else "0"
                out.append(f"{key}={value}")
                continue

        out.append(line)

    dst.write_text("\n".join(out) + "\n")


# ── Orchestration ─────────────────────────────────────────────


def ingest_account(
    rows: list[CustodianRow], fund_dir: Path, period: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """Transform custodian rows into enriched holding dicts.

    Classifies each row, transforms to holding dicts, merges with the
    fund's security master, and validates required fields.

    Args:
        rows: CustodianRow list for a single account.
        fund_dir: Fund directory (contains security_master.csv).
        period: Filing period string (unused here but kept for API symmetry).

    Returns:
        (enriched holding dicts, list of warning/error messages).
    """
    messages: list[str] = []
    holdings: list[dict[str, str]] = []

    for row in rows:
        ht = classify_holding(row)
        if ht == HoldingType.CASH:
            messages.append(f"Skipped Cash&Other row: ${row.market_value}")
            continue
        holdings.append(transform_to_holding_dict(row, ht))

    # Merge with security master if present
    sm_path = fund_dir / "security_master.csv"
    if sm_path.is_file():
        master = SecurityMaster(sm_path)
        messages.extend(master.load_warnings)
        holdings, merge_warnings = merge_positions_with_master(holdings, master)
        messages.extend(merge_warnings)
    else:
        messages.append(f"No security_master.csv found in {fund_dir}")

    # Validate required fields after merge
    merge_errors = validate_after_merge(holdings)
    messages.extend(merge_errors)

    return holdings, messages
