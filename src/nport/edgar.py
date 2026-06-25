"""EDGAR API client for downloading N-PORT filings.

Uses only stdlib (urllib.request, json) and lxml (already a dependency).
Rate-limited to 100ms between requests per SEC fair-use policy.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from lxml import etree

from nport.constants import NS_NPORT

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.sec.gov"
_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
_MIN_REQUEST_INTERVAL = 0.1  # 100ms between requests


@dataclass
class FilingMetadata:
    """Metadata for a single EDGAR filing."""
    accession_number: str
    filing_date: str
    primary_document: str
    form_type: str


@dataclass
class SeriesInfo:
    """One registered fund series + its share classes, from an EDGAR filing header."""
    series_id: str                       # S#########
    series_name: str                     # e.g. "Corgi Founder-Led ETF"
    classes: list[tuple[str, str]]       # [(class_id C#########, class_name)]


def parse_series_blocks(header_text: str) -> list[SeriesInfo]:
    """Parse ``<SERIES>…</SERIES>`` blocks from an EDGAR submission SGML header.

    The header format is line-oriented SGML (open tags only):
    ``<SERIES-ID>S000104286`` / ``<SERIES-NAME>…`` / ``<CLASS-CONTRACT-ID>C000274887``.
    """
    out: list[SeriesInfo] = []
    for block in re.findall(r"<SERIES>(.*?)</SERIES>", header_text, re.S):
        sid = re.search(r"<SERIES-ID>\s*(S\d{9})", block)
        if not sid:
            continue
        sname = re.search(r"<SERIES-NAME>\s*([^<\n]+)", block)
        classes: list[tuple[str, str]] = []
        for cblock in re.findall(r"<CLASS-CONTRACT>(.*?)</CLASS-CONTRACT>", block, re.S):
            cid = re.search(r"<CLASS-CONTRACT-ID>\s*(C\d{9})", cblock)
            if not cid:
                continue
            cname = re.search(r"<CLASS-CONTRACT-NAME>\s*([^<\n]+)", cblock)
            classes.append((cid.group(1), cname.group(1).strip() if cname else ""))
        out.append(SeriesInfo(sid.group(1), sname.group(1).strip() if sname else "", classes))
    return out


def normalize_fund_name(name: str) -> str:
    """Canonical key for matching an EDGAR series name to a Bloomberg fund name.

    Lowercases, drops punctuation, collapses whitespace, and standardizes common
    abbreviations so "Corgi 0-5 Year High Yield Corp" == "...High Yield Corporate Bond ETF".
    """
    s = (name or "").lower()
    s = s.replace("®", " ").replace("™", " ").replace(".", "")   # "U.S." -> "US"
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # expand/standardize abbreviations and drop noise words that vary between sources
    s = re.sub(r"\bcorp\b", "corporate bond", s)
    s = re.sub(r"\bcorporate bond bond\b", "corporate bond", s)
    s = re.sub(r"\bdly\b", "daily", s)
    s = re.sub(r"\byr\b", "year", s)
    if s.startswith("corgi "):     # EDGAR omits the "Corgi" prefix on some series
        s = s[len("corgi "):]
    for drop in (" etf", " fund"):
        if s.endswith(drop):
            s = s[: -len(drop)]
    return s.strip()


class EdgarClient:
    """Rate-limited client for SEC EDGAR API.

    Args:
        user_agent: Required by SEC. Format: "Company Name email@example.com"
    """

    def __init__(self, user_agent: str) -> None:
        self._user_agent = user_agent
        self._last_request: float = 0.0

    _TIMEOUT = 30  # seconds
    _MAX_RETRIES = 3

    def _get(self, url: str, max_bytes: int | None = None) -> bytes:
        """HTTP GET with rate limiting, timeout, retries, and error handling.

        ``max_bytes`` reads only the first N bytes then closes — used to grab a filing's
        SGML header (always at the top of the submission .txt) without downloading the
        whole prospectus.
        """
        elapsed = time.monotonic() - self._last_request
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)

        req = urllib.request.Request(url)
        req.add_header("User-Agent", self._user_agent)

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=self._TIMEOUT) as resp:
                    data = resp.read(max_bytes) if max_bytes else resp.read()
                self._last_request = time.monotonic()
                return data
            except urllib.error.HTTPError as e:
                self._last_request = time.monotonic()
                if e.code in (429, 503) and attempt < self._MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning("EDGAR returned %d, retrying in %ds...", e.code, wait)
                    time.sleep(wait)
                    last_exc = e
                    continue
                raise ConnectionError(
                    f"EDGAR request failed: HTTP {e.code} for {url}"
                ) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                self._last_request = time.monotonic()
                if attempt < self._MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning("EDGAR request error (%s), retrying in %ds...", e, wait)
                    time.sleep(wait)
                    last_exc = e
                    continue
                raise ConnectionError(
                    f"EDGAR request failed for {url}: {e}"
                ) from e
        raise ConnectionError(f"EDGAR request failed after {self._MAX_RETRIES} retries") from last_exc

    def _get_json(self, url: str) -> dict:
        return json.loads(self._get(url))

    def resolve_ticker_to_cik(self, ticker: str) -> str | None:
        """Look up CIK from ticker via company_tickers.json.

        Returns CIK as zero-padded 10-digit string, or None if not found.
        """
        url = f"{_BASE_URL}/files/company_tickers.json"
        data = self._get_json(url)

        ticker_upper = ticker.upper()
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                return str(entry["cik_str"]).zfill(10)
        return None

    def get_nport_filings(
        self, cik: str, count: int = 5
    ) -> list[FilingMetadata]:
        """Get recent N-PORT filing metadata for a CIK.

        Args:
            cik: 10-digit CIK (zero-padded).
            count: Maximum number of filings to return.

        Returns:
            List of FilingMetadata for N-PORT filings, most recent first.
        """
        padded = cik.zfill(10)
        url = f"{_BASE_URL}/submissions/CIK{padded}.json"
        data = self._get_json(url)

        filings: list[FilingMetadata] = []
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        docs = recent.get("primaryDocument", [])

        for i in range(len(forms)):
            if forms[i] in ("NPORT-P", "NPORT-P/A"):
                filings.append(FilingMetadata(
                    accession_number=accessions[i],
                    filing_date=dates[i],
                    primary_document=docs[i],
                    form_type=forms[i],
                ))
                if len(filings) >= count:
                    break

        return filings

    def list_filings(
        self, cik: str, forms: set[str] | None = None, count: int = 500
    ) -> list[FilingMetadata]:
        """List recent filings for a CIK, optionally filtered to given form types."""
        padded = cik.zfill(10)
        data = self._get_json(f"{_BASE_URL}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms_l = recent.get("form", [])
        acc = recent.get("accessionNumber", [])
        dates = recent.get("filingDate", [])
        docs = recent.get("primaryDocument", [])
        out: list[FilingMetadata] = []
        for i in range(len(forms_l)):
            if forms is None or forms_l[i] in forms:
                out.append(FilingMetadata(acc[i], dates[i], docs[i], forms_l[i]))
                if len(out) >= count:
                    break
        return out

    def fetch_filing_series(self, cik: str, accession: str) -> list[SeriesInfo]:
        """Parse the SERIES/CLASS-CONTRACT blocks from a filing's SGML header."""
        acc_flat = accession.replace("-", "")
        url = f"{_ARCHIVES_URL}/{cik.lstrip('0')}/{acc_flat}/{accession}.txt"
        header = self._get(url, max_bytes=60000).decode("utf-8", "replace")
        return parse_series_blocks(header)

    def harvest_trust_series(
        self,
        cik: str,
        forms: tuple[str, ...] = (
            "485BPOS", "485APOS", "485BXT", "497", "497K", "N-1A", "N-1A/A",
        ),
        max_filings: int = 400,
    ) -> dict[str, SeriesInfo]:
        """Harvest every series (id, name, classes) of a trust from its filing headers.

        Returns ``{normalized_series_name: SeriesInfo}``. Reads multi-series prospectus
        headers first (485*), then per-fund 497Ks fill any gaps; the first (most-recent)
        occurrence of each series name wins.
        """
        out: dict[str, SeriesInfo] = {}
        for fm in self.list_filings(cik, forms=set(forms), count=max_filings):
            try:
                series = self.fetch_filing_series(cik, fm.accession_number)
            except ConnectionError:
                continue
            for s in series:
                key = normalize_fund_name(s.series_name)
                if key and key not in out:
                    out[key] = s
        return out

    def download_filing_xml(self, cik: str, filing: FilingMetadata) -> bytes:
        """Download the XML document for a filing.

        Args:
            cik: 10-digit CIK.
            filing: Filing metadata from get_nport_filings.

        Returns:
            Raw XML bytes.
        """
        accession_flat = filing.accession_number.replace("-", "")
        url = (
            f"{_ARCHIVES_URL}/{cik.lstrip('0')}"
            f"/{accession_flat}/{filing.primary_document}"
        )
        return self._get(url)

    def download_latest_nport(
        self, cik: str
    ) -> tuple[bytes, FilingMetadata]:
        """Download the most recent N-PORT filing.

        Returns:
            (xml_bytes, filing_metadata)

        Raises:
            ValueError: If no N-PORT filings found.
        """
        filings = self.get_nport_filings(cik, count=1)
        if not filings:
            raise ValueError(f"No N-PORT filings found for CIK {cik}.")
        filing = filings[0]
        xml = self.download_filing_xml(cik, filing)
        return xml, filing


def extract_filing_summary(xml_bytes: bytes) -> dict:
    """Extract key fields from an N-PORT XML document.

    Returns dict with: reg_name, series_name, rep_pd_end, holdings_count, net_assets.
    """
    ns = {"n": NS_NPORT}
    root = etree.fromstring(xml_bytes)

    def _text(xpath: str) -> str:
        el = root.find(xpath, ns)
        return el.text if el is not None and el.text else ""

    holdings = root.findall(".//n:invstOrSec", ns)

    return {
        "reg_name": _text(".//n:regName"),
        "series_name": _text(".//n:seriesName"),
        "rep_pd_end": _text(".//n:repPdEnd"),
        "holdings_count": len(holdings),
        "net_assets": _text(".//n:netAssets"),
    }
