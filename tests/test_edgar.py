"""Tests for EDGAR API client (mocked HTTP)."""

import json
from pathlib import Path

import pytest

from nport.edgar import (
    EdgarClient,
    extract_filing_summary,
    normalize_fund_name,
    parse_series_blocks,
)

_ROOT = Path(__file__).resolve().parent.parent


class _MockResponse:
    """Minimal mock for urllib.request.urlopen context manager."""

    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _patch_urlopen(monkeypatch, response_data: bytes):
    """Monkey-patch urllib.request.urlopen to return fixed data."""
    def mock_urlopen(req, **kwargs):
        return _MockResponse(response_data)
    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)


class TestResolveTickerToCik:
    def test_found(self, monkeypatch):
        tickers = {
            "0": {"cik_str": 2078265, "ticker": "FDRS", "title": "Founder-Led ETF"},
            "1": {"cik_str": 1234567, "ticker": "XYZ", "title": "Other Fund"},
        }
        _patch_urlopen(monkeypatch, json.dumps(tickers).encode())
        client = EdgarClient("Test Agent test@example.com")
        cik = client.resolve_ticker_to_cik("FDRS")
        assert cik == "0002078265"

    def test_not_found(self, monkeypatch):
        tickers = {"0": {"cik_str": 1, "ticker": "ABC", "title": "X"}}
        _patch_urlopen(monkeypatch, json.dumps(tickers).encode())
        client = EdgarClient("Test Agent test@example.com")
        assert client.resolve_ticker_to_cik("NOTEXIST") is None

    def test_case_insensitive(self, monkeypatch):
        tickers = {"0": {"cik_str": 2078265, "ticker": "FDRS", "title": "X"}}
        _patch_urlopen(monkeypatch, json.dumps(tickers).encode())
        client = EdgarClient("Test Agent test@example.com")
        assert client.resolve_ticker_to_cik("fdrs") == "0002078265"


class TestGetNportFilings:
    def test_filters_nport(self, monkeypatch):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-K", "NPORT-P", "NPORT-P/A", "13F-HR", "NPORT-P"],
                    "accessionNumber": ["a-1", "a-2", "a-3", "a-4", "a-5"],
                    "filingDate": ["2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-05-01"],
                    "primaryDocument": ["d1.xml", "d2.xml", "d3.xml", "d4.xml", "d5.xml"],
                }
            }
        }
        _patch_urlopen(monkeypatch, json.dumps(submissions).encode())
        client = EdgarClient("Test Agent test@example.com")
        filings = client.get_nport_filings("0002078265", count=10)
        assert len(filings) == 3  # only NPORT-P and NPORT-P/A
        assert all(f.form_type in ("NPORT-P", "NPORT-P/A") for f in filings)

    def test_count_limit(self, monkeypatch):
        submissions = {
            "filings": {
                "recent": {
                    "form": ["NPORT-P"] * 10,
                    "accessionNumber": [f"a-{i}" for i in range(10)],
                    "filingDate": [f"2025-0{i+1}-01" for i in range(10)],
                    "primaryDocument": [f"d{i}.xml" for i in range(10)],
                }
            }
        }
        _patch_urlopen(monkeypatch, json.dumps(submissions).encode())
        client = EdgarClient("Test Agent test@example.com")
        filings = client.get_nport_filings("0002078265", count=3)
        assert len(filings) == 3

    def test_no_filings(self, monkeypatch):
        submissions = {"filings": {"recent": {"form": [], "accessionNumber": [], "filingDate": [], "primaryDocument": []}}}
        _patch_urlopen(monkeypatch, json.dumps(submissions).encode())
        client = EdgarClient("Test Agent test@example.com")
        filings = client.get_nport_filings("0002078265")
        assert filings == []


class TestExtractFilingSummary:
    def test_reference_xml(self):
        """Use the existing reference_nport.xml fixture to test extraction."""
        ref_path = _ROOT / "reference_nport.xml"
        if not ref_path.exists():
            pytest.skip("reference_nport.xml not found")
        xml_bytes = ref_path.read_bytes()
        summary = extract_filing_summary(xml_bytes)
        assert summary["reg_name"] == "Corgi ETF Trust I"
        assert summary["series_name"] == "Founder-Led ETF"
        assert summary["rep_pd_end"] == "2025-12-31"
        assert summary["holdings_count"] == 54
        assert summary["net_assets"]  # non-empty

    def test_empty_xml(self):
        """Minimal valid N-PORT XML returns empty strings for missing fields."""
        xml = b'<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData></formData></edgarSubmission>'
        summary = extract_filing_summary(xml)
        assert summary["reg_name"] == ""
        assert summary["holdings_count"] == 0


_HEADER = """\
<SEC-HEADER>
<SERIES-AND-CLASSES-CONTRACTS-DATA>
<SERIES>
<OWNER-CIK>0002078265
<SERIES-ID>S000096625
<SERIES-NAME>Founder-Led ETF
<CLASS-CONTRACT>
<CLASS-CONTRACT-ID>C000265520
<CLASS-CONTRACT-NAME>Shares
</CLASS-CONTRACT>
</SERIES>
<SERIES>
<SERIES-ID>S000104291
<SERIES-NAME>Corgi 0-5 Year High Yield Corporate Bond ETF
<CLASS-CONTRACT>
<CLASS-CONTRACT-ID>C000274892
<CLASS-CONTRACT-NAME>Shares
</CLASS-CONTRACT>
</SERIES>
</SERIES-AND-CLASSES-CONTRACTS-DATA>
</SEC-HEADER>
"""


class TestParseSeriesBlocks:
    def test_parses_series_and_classes(self):
        series = parse_series_blocks(_HEADER)
        assert len(series) == 2
        a, b = series
        assert a.series_id == "S000096625" and a.series_name == "Founder-Led ETF"
        assert a.classes == [("C000265520", "Shares")]
        assert b.series_id == "S000104291" and b.classes[0][0] == "C000274892"

    def test_ignores_blocks_without_series_id(self):
        assert parse_series_blocks("<SERIES>\n<SERIES-NAME>No id\n</SERIES>") == []


class TestNormalizeFundName:
    def test_matches_edgar_to_bloomberg(self):
        # EDGAR drops the "Corgi" prefix on some series; Bloomberg keeps it.
        assert normalize_fund_name("Corgi Founder-Led ETF") == normalize_fund_name("Founder-Led ETF")
        # "U.S." vs "US" collapse to the same key.
        assert normalize_fund_name("Corgi U.S. War Machine ETF") == \
            normalize_fund_name("Corgi US War Machine ETF")
        # Corp vs Corporate Bond + ETF suffix normalize together.
        assert normalize_fund_name("Corgi 0-5 Year High Yield Corp") == \
            normalize_fund_name("Corgi 0-5 Year High Yield Corporate Bond ETF")

    def test_keeps_real_differences_distinct(self):
        assert normalize_fund_name("Corgi US Technology 2x Daily ETF") != \
            normalize_fund_name("Corgi US Healthcare 2x Daily ETF")
        assert normalize_fund_name("...Buffer ETF - May Series") != \
            normalize_fund_name("...Buffer ETF - June Series")
