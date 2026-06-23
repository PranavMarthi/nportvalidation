"""CSV-based security reference data lookup table."""

import csv
from pathlib import Path

from nport.config import _HOLDINGS_KEY_MAP
from nport.input_validation import _CUSIP_RE, _ISIN_RE, _LEI_RE


class SecurityMaster:
    """Reference data keyed by CUSIP > ISIN > ticker.

    Loads a CSV with camelCase headers (matching _HOLDINGS_KEY_MAP)
    and stores rows internally using snake_case field names.
    """

    def __init__(self, path: str | Path) -> None:
        self._by_cusip: dict[str, dict[str, str]] = {}
        self._by_isin: dict[str, dict[str, str]] = {}
        self._by_ticker: dict[str, dict[str, str]] = {}
        self._records: list[dict[str, str]] = []
        self._warnings: list[str] = []
        self._load(Path(path))

    def _load(self, path: Path) -> None:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Map camelCase CSV headers to snake_case field names
                record: dict[str, str] = {}
                for csv_key, value in row.items():
                    field = _HOLDINGS_KEY_MAP.get(csv_key, csv_key)
                    record[field] = value
                self._records.append(record)

                cusip = record.get("cusip", "")
                isin = record.get("isin", "")
                ticker = record.get("ticker", "")

                name = record.get("name", f"row {len(self._records)}")
                if cusip and cusip not in ("N/A", "000000000", ""):
                    if cusip in self._by_cusip:
                        old_name = self._by_cusip[cusip].get("name", "?")
                        self._warnings.append(f"Duplicate CUSIP '{cusip}': '{old_name}' overwritten by '{name}'.")
                    self._by_cusip[cusip] = record
                if isin and isin != "N/A":
                    if isin in self._by_isin:
                        old_name = self._by_isin[isin].get("name", "?")
                        self._warnings.append(f"Duplicate ISIN '{isin}': '{old_name}' overwritten by '{name}'.")
                    self._by_isin[isin] = record
                if ticker and ticker != "N/A":
                    if ticker in self._by_ticker:
                        old_name = self._by_ticker[ticker].get("name", "?")
                        self._warnings.append(f"Duplicate ticker '{ticker}': '{old_name}' overwritten by '{name}'.")
                    self._by_ticker[ticker] = record

    def lookup(
        self,
        cusip: str | None = None,
        isin: str | None = None,
        ticker: str | None = None,
    ) -> dict[str, str] | None:
        """Look up a security by CUSIP first, then ISIN, then ticker.

        Returns a copy of the record to prevent accidental mutation of
        internal state.
        """
        if cusip and cusip not in ("N/A", "000000000", ""):
            hit = self._by_cusip.get(cusip)
            if hit:
                return dict(hit)
        if isin and isin not in ("N/A", ""):
            hit = self._by_isin.get(isin)
            if hit:
                return dict(hit)
        if ticker and ticker not in ("N/A", ""):
            hit = self._by_ticker.get(ticker)
            if hit:
                return dict(hit)
        return None

    def validate(self) -> list[str]:
        """Check CUSIP/ISIN/LEI formats, returning a list of error messages."""
        errors: list[str] = []
        for i, rec in enumerate(self._records):
            name = rec.get("name", f"row {i}")

            cusip = rec.get("cusip", "")
            if cusip and not _CUSIP_RE.match(cusip):
                errors.append(f"{name}: invalid CUSIP '{cusip}'.")

            isin = rec.get("isin", "")
            if isin and not _ISIN_RE.match(isin):
                errors.append(f"{name}: invalid ISIN '{isin}'.")

            lei = rec.get("lei", "")
            if lei and not _LEI_RE.match(lei):
                errors.append(f"{name}: invalid LEI '{lei}'.")

        return errors

    @property
    def load_warnings(self) -> list[str]:
        """Warnings generated during CSV loading (e.g. duplicate keys)."""
        return list(self._warnings)

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        return len(self._records) > 0
