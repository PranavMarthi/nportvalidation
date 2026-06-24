"""Bloomberg Desktop API adapter for N-PORT holdings enrichment.

Connects to a running Bloomberg Terminal via blpapi (localhost:8194),
resolves security identifiers, and fetches N-PORT-required fields
from a minimal 4-column CSV (Name, Type, Weight%, Market Value).

blpapi is an optional dependency — this module lazy-imports it.
"""

import csv
import logging
import sys
from dataclasses import dataclass, fields
from pathlib import Path

from nport.models import Holding

logger = logging.getLogger(__name__)

# Bloomberg field → N-PORT Holding field mapping
_BDP_FIELD_MAP = {
    "ID_CUSIP": "cusip",
    "ID_ISIN": "isin",
    "ID_LEI": "lei",
    "CNTRY_OF_DOMICILE": "inv_country",
    "PX_LAST": "_px_last",  # internal, used to compute balance
}

# Additional BDP fields for options
_OPT_FIELD_MAP = {
    "OPT_PUT_CALL": "put_or_call",
    "OPT_STRIKE_PX": "exercise_price",
    "OPT_EXPIRE_DT": "exp_dt",
    "DELTA_MID_RT": "delta",
}

# Additional BDP fields for bonds
_BOND_FIELD_MAP = {
    "MATURITY": "maturity_dt",
    "CPN_TYP": "coupon_kind",
    "CPN": "annualized_rt",
}

# Bloomberg SECURITY_TYP → N-PORT asset_cat
_SECURITY_TYPE_MAP = {
    "Common Stock": "EC",
    "Preferred Stock": "EP",
    "ADR": "EC",
    "REIT": "RE",
    "ETF": "STIV",
    "MLP": "EC",
    "Bond": "DBT",
    "Corp": "DBT",
    "Govt": "DBT",
    "Muni": "DBT",
    "Mtge": "ABS-MBS",
    "Equity": "EC",
}

# Bloomberg INDUSTRY_SECTOR → N-PORT issuer_cat
_SECTOR_TO_ISSUER_MAP = {
    "Government": "UST",
    "Agency": "USGA",
    "Municipal": "MUN",
    "Corporate": "CORP",
    "Financial": "CORP",
    "Industrial": "CORP",
    "Utility": "CORP",
    "Technology": "CORP",
    "Consumer, Non-cyclical": "CORP",
    "Consumer, Cyclical": "CORP",
    "Basic Materials": "CORP",
    "Energy": "CORP",
    "Communications": "CORP",
    "Diversified": "CORP",
}


@dataclass
class MinimalRow:
    """One row from the minimal input CSV."""
    name: str
    type: str
    weight_pct: float
    market_value: float


def _lazy_import_blpapi():
    """Import blpapi lazily so it's only required for enrichment."""
    try:
        import blpapi
        return blpapi
    except ImportError:
        raise ImportError(
            "blpapi is required for Bloomberg enrichment. "
            "Install with: pip install blpapi  "
            "Requires Bloomberg Terminal running on localhost:8194."
        )


class BloombergSession:
    """Manages a blpapi session to Bloomberg Desktop API."""

    def __init__(self, host: str = "localhost", port: int = 8194):
        self._blpapi = _lazy_import_blpapi()
        self._host = host
        self._port = port
        self._session = None

    def open(self):
        blpapi = self._blpapi
        opts = blpapi.SessionOptions()
        opts.setServerHost(self._host)
        opts.setServerPort(self._port)
        self._session = blpapi.Session(opts)
        if not self._session.start():
            raise ConnectionError(
                f"Failed to connect to Bloomberg at {self._host}:{self._port}. "
                "Is Bloomberg Terminal running?"
            )
        if not self._session.openService("//blp/refdata"):
            raise ConnectionError("Failed to open //blp/refdata service.")
        logger.info("Bloomberg session opened")

    def close(self):
        if self._session:
            self._session.stop()
            self._session = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def bdp(self, securities: list[str], fields: list[str]) -> dict[str, dict[str, str]]:
        """Fetch reference data (BDP) for a list of securities.

        Returns {security: {field: value}} mapping.
        """
        blpapi = self._blpapi
        svc = self._session.getService("//blp/refdata")
        request = svc.createRequest("ReferenceDataRequest")
        for sec in securities:
            request.append("securities", sec)
        for fld in fields:
            request.append("fields", fld)

        self._session.sendRequest(request)

        results: dict[str, dict[str, str]] = {}
        while True:
            event = self._session.nextEvent(5000)
            for msg in event:
                if msg.hasElement("securityData"):
                    sec_data = msg.getElement("securityData")
                    for i in range(sec_data.numValues()):
                        item = sec_data.getValueAsElement(i)
                        sec_name = item.getElementAsString("security")
                        field_data = item.getElement("fieldData")
                        row = {}
                        for fld in fields:
                            if field_data.hasElement(fld):
                                el = field_data.getElement(fld)
                                row[fld] = str(el.getValue())
                        results[sec_name] = row
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return results

    def search_security(self, query: str) -> str | None:
        """Search for a security by name using //blp/instruments.

        Returns the Bloomberg security identifier or None.
        """
        blpapi = self._blpapi
        if not self._session.openService("//blp/instruments"):
            logger.warning("Could not open //blp/instruments service")
            return None

        svc = self._session.getService("//blp/instruments")
        request = svc.createRequest("instrumentListRequest")
        request.set("query", query)
        request.set("maxResults", 1)

        self._session.sendRequest(request)

        result = None
        while True:
            event = self._session.nextEvent(5000)
            for msg in event:
                if msg.hasElement("results"):
                    results_el = msg.getElement("results")
                    if results_el.numValues() > 0:
                        result = results_el.getValueAsElement(0).getElementAsString("security")
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        return result


def _read_minimal_csv(path: Path) -> list[MinimalRow]:
    """Read a minimal 4-column CSV file."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rownum, row in enumerate(reader, 2):
            try:
                rows.append(MinimalRow(
                    name=row["Name"].strip(),
                    type=row.get("Type", "").strip(),
                    weight_pct=float(row["Weight%"]),
                    market_value=float(row["Market Value"]),
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Row %d: skipping — %s", rownum, e)
    return rows


def _resolve_bbg_ticker(session: BloombergSession, name: str, sec_type: str) -> str | None:
    """Resolve a security name to a Bloomberg ticker."""
    # Try direct search first
    result = session.search_security(name)
    if result:
        return result

    # Try common suffixes
    for suffix in [" US Equity", " Equity"]:
        candidate = name.replace(" ", " ") + suffix  # crude
        result = session.search_security(candidate)
        if result:
            return result

    logger.warning("Could not resolve '%s' (type=%s) to Bloomberg ticker", name, sec_type)
    return None


def _map_asset_cat(sec_type: str) -> str:
    """Map Bloomberg SECURITY_TYP to N-PORT assetCat."""
    return _SECURITY_TYPE_MAP.get(sec_type, "EC")


def _map_issuer_cat(sector: str) -> str:
    """Map Bloomberg INDUSTRY_SECTOR to N-PORT issuerCat."""
    return _SECTOR_TO_ISSUER_MAP.get(sector, "CORP")


def enrich_holdings(
    input_path: Path,
    output_path: Path,
    host: str = "localhost",
    port: int = 8194,
    batch_size: int = 50,
) -> None:
    """Enrich a minimal CSV with Bloomberg data and write canonical holdings CSV.

    Merge semantics: pre-populated fields in the input are preserved.
    Only empty fields are filled from Bloomberg.
    """
    rows = _read_minimal_csv(input_path)
    if not rows:
        print("No rows to process.", file=sys.stderr)
        return

    logger.info("Processing %d rows from %s", len(rows), input_path)

    with BloombergSession(host, port) as session:
        holdings = []
        # Process in batches
        for batch_start in range(0, len(rows), batch_size):
            batch = rows[batch_start:batch_start + batch_size]
            batch_holdings = _process_batch(session, batch)
            holdings.extend(batch_holdings)

    _write_canonical_csv(holdings, output_path)
    print(f"Written: {output_path} ({len(holdings)} holdings)")


def _process_batch(
    session: BloombergSession, rows: list[MinimalRow]
) -> list[dict[str, str]]:
    """Process a batch of minimal rows into canonical holding dicts."""
    # Resolve tickers
    tickers: dict[str, str] = {}
    for row in rows:
        if row.type in ("CASH", ""):
            continue
        ticker = _resolve_bbg_ticker(session, row.name, row.type)
        if ticker:
            tickers[row.name] = ticker

    # BDP for all resolved tickers
    if tickers:
        all_fields = list(_BDP_FIELD_MAP.keys()) + ["SECURITY_TYP", "INDUSTRY_SECTOR", "TICKER"]
        bdp_data = session.bdp(list(tickers.values()), all_fields)
    else:
        bdp_data = {}

    holdings = []
    for row in rows:
        h = _build_holding_from_row(row, tickers, bdp_data)
        holdings.append(h)

    return holdings


def _build_holding_from_row(
    row: MinimalRow,
    tickers: dict[str, str],
    bdp_data: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Construct a canonical holding dict from a minimal row + Bloomberg data."""
    # Start with defaults for all Holding fields
    h: dict[str, str] = {f.name: "" for f in fields(Holding)}

    h["name"] = row.name
    h["title"] = row.name
    h["val_usd"] = f"{row.market_value:.2f}"
    h["pct_val"] = f"{row.weight_pct:.2f}"
    h["cur_cd"] = "USD"
    h["units"] = "NS"
    h["payoff_profile"] = "Long"
    h["is_restricted_sec"] = "N"
    h["fair_val_level"] = "1"
    h["is_cash_collateral"] = "N"
    h["is_non_cash_collateral"] = "N"
    h["is_loan_by_fund"] = "N"

    # Handle cash/other positions
    if row.type in ("CASH", ""):
        h["cusip"] = "N/A"
        h["lei"] = "N/A"
        h["asset_cat"] = "STIV"
        h["issuer_cat"] = "CORP"
        h["inv_country"] = "US"
        h["balance"] = f"{row.market_value:.2f}"
        h["units"] = "PA"
        return h

    # Look up Bloomberg data
    bbg_ticker = tickers.get(row.name)
    bbg_fields = bdp_data.get(bbg_ticker, {}) if bbg_ticker else {}

    # Map standard BDP fields
    for bbg_field, nport_field in _BDP_FIELD_MAP.items():
        if nport_field.startswith("_"):
            continue  # internal fields
        val = bbg_fields.get(bbg_field, "")
        if val and not h.get(nport_field):
            h[nport_field] = val

    # Compute balance from market value / price
    px_last = bbg_fields.get("PX_LAST", "")
    if px_last:
        try:
            price = float(px_last)
            if price > 0:
                h["balance"] = str(int(row.market_value / price))
        except (ValueError, ZeroDivisionError):
            pass
    if not h["balance"]:
        h["balance"] = "0"

    # Ticker
    ticker_val = bbg_fields.get("TICKER", "")
    if ticker_val and not h["ticker"]:
        h["ticker"] = ticker_val

    # Asset category
    sec_type = bbg_fields.get("SECURITY_TYP", "")
    if not h["asset_cat"]:
        h["asset_cat"] = _map_asset_cat(sec_type)

    # Issuer category
    sector = bbg_fields.get("INDUSTRY_SECTOR", "")
    if not h["issuer_cat"]:
        h["issuer_cat"] = _map_issuer_cat(sector)

    # Defaults for missing fields
    if not h["cusip"]:
        h["cusip"] = "N/A"
    if not h["lei"]:
        h["lei"] = "N/A"
    if not h["inv_country"]:
        h["inv_country"] = "US"

    return h


from nport.data_loader import write_canonical_csv as _write_canonical_csv  # noqa: E402
