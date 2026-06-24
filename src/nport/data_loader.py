"""Local data loading — no Bloomberg at runtime.

Provides DataLoader for fund directory orchestration,
write_canonical_csv / write_split_csv for holdings output, and
merge_positions_with_master for enriching positions from a SecurityMaster.
"""

import csv
import tempfile
from dataclasses import fields
from pathlib import Path

from nport.config import (
    _HOLDINGS_KEY_MAP,
    parse_config,
    parse_filing,
    parse_holdings,
)
from nport.cusip import is_valid_cusip
from nport.models import FilingData, FundConfig, Holding
from nport.schema import FIELD_SPECS
from nport.security_master import SecurityMaster


def write_canonical_csv(holdings: list[dict[str, str]], output_path: Path) -> None:
    """Write holdings dicts to canonical CSV with all Holding fields as columns."""
    field_to_csv = {v: k for k, v in _HOLDINGS_KEY_MAP.items()}
    all_fields = [f.name for f in fields(Holding)]
    headers = [field_to_csv.get(f, f) for f in all_fields]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with open(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for h in holdings:
                row = {field_to_csv.get(k, k): v for k, v in h.items()}
                writer.writerow(row)
        Path(tmp).replace(output_path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


_BASE_GROUPS = {"base", "conditional"}
_DEBT_GROUPS = {"debt"}
_DERIV_GROUPS = {"deriv_common", "option", "ref_instrument", "swap", "forward", "other_deriv"}


def _generate_holding_ids(holdings: list[dict[str, str]]) -> list[str]:
    """Generate unique holdingId for each holding."""
    ids: list[str] = []
    seen: dict[str, int] = {}
    for i, h in enumerate(holdings):
        ticker = h.get("ticker", "").strip()
        other = h.get("other_value", "").strip()
        cusip = h.get("cusip", "").strip()
        if ticker:
            base = ticker
        elif other:
            base = other
        elif cusip and cusip not in ("N/A", "000000000"):
            base = cusip
        else:
            base = f"row-{i}"
        if base in seen:
            seen[base] += 1
            ids.append(f"{base}-{seen[base]}")
        else:
            seen[base] = 0
            ids.append(base)
    return ids


def _write_atomic_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    """Write CSV atomically using tempfile + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        Path(tmp).replace(path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_split_csv(holdings: list[dict[str, str]], output_dir: Path) -> list[Path]:
    """Write holdings to split CSV files: base + optional debt/derivative satellites.

    Args:
        holdings: list of dicts with snake_case Holding field names.
        output_dir: directory to write split files into.

    Returns:
        List of paths written.
    """
    field_to_csv = {v: k for k, v in _HOLDINGS_KEY_MAP.items()}

    base_fields = [s.name for s in FIELD_SPECS if s.group in _BASE_GROUPS]
    debt_fields = [s.name for s in FIELD_SPECS if s.group in _DEBT_GROUPS]
    deriv_fields = [s.name for s in FIELD_SPECS if s.group in _DERIV_GROUPS]

    holding_ids = _generate_holding_ids(holdings)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # Base holdings.csv — always include all base fields, conditional only if populated
    active_base = []
    for f in base_fields:
        spec = next(s for s in FIELD_SPECS if s.name == f)
        if spec.group == "base" or any(h.get(f, "").strip() for h in holdings):
            active_base.append(f)

    csv_headers = ["holdingId"] + [field_to_csv.get(f, f) for f in active_base]
    rows = []
    for hid, h in zip(holding_ids, holdings):
        row: dict[str, str] = {"holdingId": hid}
        for f in active_base:
            row[field_to_csv.get(f, f)] = h.get(f, "")
        rows.append(row)
    _write_atomic_csv(output_dir / "holdings.csv", csv_headers, rows)
    written.append(output_dir / "holdings.csv")

    # Satellite files — only rows + columns with data
    for filename, field_list in [
        ("debt_securities.csv", debt_fields),
        ("derivatives.csv", deriv_fields),
    ]:
        # Find rows with at least one non-empty value
        sat_rows = [
            (hid, h)
            for hid, h in zip(holding_ids, holdings)
            if any(h.get(f, "").strip() for f in field_list)
        ]
        if not sat_rows:
            continue

        # Find columns with at least one non-empty value
        active = [
            f for f in field_list if any(h.get(f, "").strip() for _, h in sat_rows)
        ]
        if not active:
            continue

        csv_hdrs = ["holdingId"] + [field_to_csv.get(f, f) for f in active]
        csv_rows = []
        for hid, h in sat_rows:
            row = {"holdingId": hid}
            for f in active:
                row[field_to_csv.get(f, f)] = h.get(f, "")
            csv_rows.append(row)
        _write_atomic_csv(output_dir / filename, csv_hdrs, csv_rows)
        written.append(output_dir / filename)

    return written


class DataLoader:
    """Loads fund data from a structured fund directory.

    Expected layout::

        fund_dir/
            fund_config.txt
            security_master.csv   (optional)
            filings/
                <period>/
                    filing_data.txt
                    holdings.csv
    """

    def __init__(self, fund_dir: str | Path) -> None:
        self._dir = Path(fund_dir)
        if not self._dir.is_dir():
            raise FileNotFoundError(f"Fund directory not found: {self._dir}")
        self._security_master: SecurityMaster | None = None
        self._sm_loaded = False

    def load_config(self) -> FundConfig:
        return parse_config(self._dir / "fund_config.txt")

    def load_filing(self, period: str) -> FilingData:
        return parse_filing(self._dir / "filings" / period / "filing_data.txt")

    def load_holdings(self, period: str) -> list[Holding]:
        return parse_holdings(self._dir / "filings" / period / "holdings.csv")

    def load_all(self, period: str) -> tuple[FundConfig, FilingData, list[Holding]]:
        return self.load_config(), self.load_filing(period), self.load_holdings(period)

    @property
    def security_master(self) -> SecurityMaster | None:
        """Lazy-load security_master.csv if present."""
        if not self._sm_loaded:
            sm_path = self._dir / "security_master.csv"
            if sm_path.is_file():
                self._security_master = SecurityMaster(sm_path)
            self._sm_loaded = True
        return self._security_master

    def output_path(self, period: str) -> Path:
        return self._dir / "filings" / period / "output.xml"


_BASE_REQUIRED_FIELDS = [
    "name", "lei", "title", "cusip", "balance", "units", "cur_cd",
    "val_usd", "pct_val", "payoff_profile", "asset_cat", "issuer_cat",
    "inv_country", "is_restricted_sec", "fair_val_level",
    "is_cash_collateral", "is_non_cash_collateral", "is_loan_by_fund",
]


def validate_after_merge(positions: list[dict[str, str]]) -> list[str]:
    """Check that base required fields are populated after merge.

    Returns list of error messages for missing fields.
    """
    errors: list[str] = []
    for i, pos in enumerate(positions):
        name = pos.get("name", f"row {i}")
        for field in _BASE_REQUIRED_FIELDS:
            val = pos.get(field, "")
            if not val.strip():
                errors.append(f"{name}: missing required field '{field}'.")
    return errors


def merge_positions_with_master(
    positions: list[dict[str, str]],
    master: SecurityMaster,
) -> tuple[list[dict[str, str]], list[str]]:
    """Enrich position dicts by filling empty fields from the security master.

    Args:
        positions: list of dicts with snake_case Holding field names.
        master: SecurityMaster instance.

    Returns:
        (enriched positions, warning messages).
    """
    warnings: list[str] = []
    enriched: list[dict[str, str]] = []

    for i, pos in enumerate(positions):
        cusip = pos.get("cusip", "")
        isin = pos.get("isin", "")
        ticker = pos.get("ticker", "")
        name = pos.get("name", f"row {i}")

        ref = master.lookup(cusip=cusip, isin=isin, ticker=ticker)
        if ref is None:
            warnings.append(f"No master record for {name} (cusip={cusip}, isin={isin}, ticker={ticker}).")
            enriched.append(dict(pos))
            continue

        merged = dict(pos)
        for field, value in ref.items():
            if merged.get(field, "") == "" and value:
                merged[field] = value

        # A valid CUSIP in the master overrides an invalid one from the
        # custodian (e.g. a spreadsheet-corrupted value the custodian feed
        # couldn't self-recover). The operator's master entry wins.
        master_cusip = ref.get("cusip", "")
        if (
            is_valid_cusip(master_cusip)
            and not is_valid_cusip(merged.get("cusip", ""))
            and merged.get("cusip", "") not in ("N/A", "000000000")
        ):
            warnings.append(
                f"{name}: replaced invalid CUSIP "
                f"'{merged.get('cusip', '')}' with master value '{master_cusip}'."
            )
            merged["cusip"] = master_cusip

        enriched.append(merged)

    return enriched, warnings
