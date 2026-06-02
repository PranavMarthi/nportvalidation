"""Tests for SecurityMaster."""

import textwrap
from pathlib import Path

import pytest

from nport.security_master import SecurityMaster


@pytest.fixture
def sm_csv(tmp_path: Path) -> Path:
    """Write a small security master CSV and return its path."""
    csv_text = textwrap.dedent("""\
        name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat
        Meta Platforms Inc,BQ4BKCS1HXDV9HN80Z93,Meta Platforms Inc,30303M102,US30303M1027,META,US,EC,CORP
        Spotify Technology SA,549300B4X0JHWV0DTD60,Spotify Technology SA,N/A,LU1778762911,SPOT,SE,EC,CORP
        Credo Technology Group,N/A,Credo Technology Group Holding Ltd,N/A,KYG254571055,CRDO,US,EC,CORP
    """)
    p = tmp_path / "security_master.csv"
    p.write_text(csv_text)
    return p


@pytest.fixture
def sm(sm_csv: Path) -> SecurityMaster:
    return SecurityMaster(sm_csv)


class TestLookup:
    def test_lookup_by_cusip(self, sm: SecurityMaster):
        rec = sm.lookup(cusip="30303M102")
        assert rec is not None
        assert rec["ticker"] == "META"

    def test_lookup_isin_fallback(self, sm: SecurityMaster):
        """Spotify has cusip=N/A so ISIN should match."""
        rec = sm.lookup(cusip="N/A", isin="LU1778762911")
        assert rec is not None
        assert rec["ticker"] == "SPOT"

    def test_lookup_ticker_fallback(self, sm: SecurityMaster):
        """Credo has cusip=N/A; look up by ticker."""
        rec = sm.lookup(ticker="CRDO")
        assert rec is not None
        assert rec["name"] == "Credo Technology Group"

    def test_lookup_not_found(self, sm: SecurityMaster):
        assert sm.lookup(cusip="XXXXXXXXX") is None

    def test_lookup_skips_na(self, sm: SecurityMaster):
        """N/A cusip should not match anything."""
        assert sm.lookup(cusip="N/A") is None


class TestValidation:
    def test_valid_data(self, sm: SecurityMaster):
        errors = sm.validate()
        assert errors == []

    def test_bad_cusip(self, tmp_path: Path):
        csv_text = "name,cusip,isin,ticker\nBad Co,ZZZZ,US12345678AB,TICK\n"
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        errors = SecurityMaster(p).validate()
        assert any("CUSIP" in e for e in errors)

    def test_bad_isin(self, tmp_path: Path):
        csv_text = "name,cusip,isin,ticker\nBad Co,N/A,BADISIN,TICK\n"
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        errors = SecurityMaster(p).validate()
        assert any("ISIN" in e for e in errors)

    def test_bad_lei(self, tmp_path: Path):
        csv_text = "name,lei,cusip,isin,ticker\nBad Co,short,N/A,,TICK\n"
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        errors = SecurityMaster(p).validate()
        assert any("LEI" in e for e in errors)


class TestLenBool:
    def test_len(self, sm: SecurityMaster):
        assert len(sm) == 3

    def test_bool_nonempty(self, sm: SecurityMaster):
        assert bool(sm) is True

    def test_empty(self, tmp_path: Path):
        csv_text = "name,cusip,isin,ticker\n"
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        empty = SecurityMaster(p)
        assert len(empty) == 0
        assert bool(empty) is False


class TestDuplicateDetection:
    def test_duplicate_cusip_warns(self, tmp_path: Path):
        csv_text = textwrap.dedent("""\
            name,cusip,isin,ticker
            Company A,30303M102,US30303M1027,AAAA
            Company B,30303M102,US99999X1234,BBBB
        """)
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        sm = SecurityMaster(p)
        assert len(sm.load_warnings) >= 1
        assert any("Duplicate CUSIP" in w for w in sm.load_warnings)

    def test_no_duplicate_no_warning(self, sm: SecurityMaster):
        assert len(sm.load_warnings) == 0

    def test_duplicate_isin_warns(self, tmp_path: Path):
        csv_text = textwrap.dedent("""\
            name,cusip,isin,ticker
            Company A,N/A,US30303M1027,AAAA
            Company B,N/A,US30303M1027,BBBB
        """)
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        sm = SecurityMaster(p)
        assert any("Duplicate ISIN" in w for w in sm.load_warnings)

    def test_duplicate_ticker_warns(self, tmp_path: Path):
        csv_text = textwrap.dedent("""\
            name,cusip,isin,ticker
            Company A,N/A,,SAME
            Company B,N/A,,SAME
        """)
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        sm = SecurityMaster(p)
        assert any("Duplicate ticker" in w for w in sm.load_warnings)


class TestMultipleSecurities:
    def test_all_indexed(self, sm: SecurityMaster):
        assert sm.lookup(cusip="30303M102") is not None
        assert sm.lookup(isin="LU1778762911") is not None
        assert sm.lookup(ticker="CRDO") is not None
