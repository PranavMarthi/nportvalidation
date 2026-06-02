"""Tests for DataLoader, write_canonical_csv, and merge_positions_with_master."""

import shutil
import textwrap
from pathlib import Path

import pytest

from nport.config import parse_holdings
from nport.data_loader import DataLoader, merge_positions_with_master, validate_after_merge, write_canonical_csv
from nport.security_master import SecurityMaster

_FDRS_DIR = Path(__file__).resolve().parent.parent / "data" / "funds" / "fdrs"


def _build_fund_dir(tmp_path: Path, period: str = "2025-12", with_sm: bool = False) -> Path:
    """Create a minimal fund directory from fdrs data."""
    fund = tmp_path / "test_fund"
    filings = fund / "filings" / period
    filings.mkdir(parents=True)

    shutil.copy(_FDRS_DIR / "fund_config.txt", fund / "fund_config.txt")
    shutil.copy(_FDRS_DIR / "filings" / "2025-12" / "filing_data.txt", filings / "filing_data.txt")
    shutil.copy(_FDRS_DIR / "filings" / "2025-12" / "holdings.csv", filings / "holdings.csv")

    if with_sm:
        sm_csv = textwrap.dedent("""\
            name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat
            Meta Platforms Inc,BQ4BKCS1HXDV9HN80Z93,Meta Platforms Inc,30303M102,US30303M1027,META,US,EC,CORP
        """)
        (fund / "security_master.csv").write_text(sm_csv)

    return fund


class TestDataLoaderLoadAll:
    def test_load_all(self, tmp_path: Path):
        fund = _build_fund_dir(tmp_path)
        loader = DataLoader(fund)
        config, filing, holdings = loader.load_all("2025-12")
        assert config.series_name == "Founder-Led ETF"
        assert filing.submission_type == "NPORT-P"
        assert len(holdings) == 54

    def test_missing_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            DataLoader(tmp_path / "nonexistent")

    def test_output_path(self, tmp_path: Path):
        fund = _build_fund_dir(tmp_path)
        loader = DataLoader(fund)
        assert loader.output_path("2025-12") == fund / "filings" / "2025-12" / "output.xml"


class TestSecurityMasterProperty:
    def test_present(self, tmp_path: Path):
        fund = _build_fund_dir(tmp_path, with_sm=True)
        loader = DataLoader(fund)
        sm = loader.security_master
        assert sm is not None
        assert len(sm) == 1

    def test_absent(self, tmp_path: Path):
        fund = _build_fund_dir(tmp_path, with_sm=False)
        loader = DataLoader(fund)
        assert loader.security_master is None

    def test_cached(self, tmp_path: Path):
        fund = _build_fund_dir(tmp_path, with_sm=True)
        loader = DataLoader(fund)
        sm1 = loader.security_master
        sm2 = loader.security_master
        assert sm1 is sm2


class TestMergePositionsWithMaster:
    @pytest.fixture
    def master(self, tmp_path: Path) -> SecurityMaster:
        csv_text = textwrap.dedent("""\
            name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat
            Meta Platforms Inc,BQ4BKCS1HXDV9HN80Z93,Meta Platforms Inc,30303M102,US30303M1027,META,US,EC,CORP
        """)
        p = tmp_path / "sm.csv"
        p.write_text(csv_text)
        return SecurityMaster(p)

    def test_fills_empty_fields(self, master: SecurityMaster):
        positions = [{"name": "Meta Platforms Inc", "cusip": "30303M102", "lei": "", "inv_country": ""}]
        enriched, warnings = merge_positions_with_master(positions, master)
        assert enriched[0]["lei"] == "BQ4BKCS1HXDV9HN80Z93"
        assert enriched[0]["inv_country"] == "US"
        assert warnings == []

    def test_preserves_existing(self, master: SecurityMaster):
        positions = [{"name": "Meta Platforms Inc", "cusip": "30303M102", "lei": "CUSTOM_LEI_VALUE_12345"}]
        enriched, _ = merge_positions_with_master(positions, master)
        assert enriched[0]["lei"] == "CUSTOM_LEI_VALUE_12345"

    def test_warns_on_unmatched(self, master: SecurityMaster):
        positions = [{"name": "Unknown Corp", "cusip": "N/A", "isin": "", "ticker": ""}]
        enriched, warnings = merge_positions_with_master(positions, master)
        assert len(warnings) == 1
        assert "Unknown Corp" in warnings[0]
        # Row should still be present, unmodified
        assert enriched[0]["name"] == "Unknown Corp"


class TestValidateAfterMerge:
    def test_missing_fields_reported(self):
        positions = [{"name": "Incomplete Corp", "cusip": "12345A789"}]
        errors = validate_after_merge(positions)
        assert any("lei" in e for e in errors)
        assert any("balance" in e for e in errors)
        assert any("units" in e for e in errors)

    def test_complete_position_no_errors(self):
        positions = [{
            "name": "Good Corp", "lei": "N/A", "title": "Good Corp",
            "cusip": "12345A789", "balance": "100", "units": "NS",
            "cur_cd": "USD", "val_usd": "1000", "pct_val": "1.0",
            "payoff_profile": "Long", "asset_cat": "EC", "issuer_cat": "CORP",
            "inv_country": "US", "is_restricted_sec": "N", "fair_val_level": "1",
            "is_cash_collateral": "N", "is_non_cash_collateral": "N",
            "is_loan_by_fund": "N",
        }]
        errors = validate_after_merge(positions)
        assert errors == []


class TestWriteCanonicalCsvRoundTrip:
    def test_round_trip(self, tmp_path: Path):
        """Write holdings via write_canonical_csv, then parse back with parse_holdings."""
        holdings_dicts = [
            {
                "name": "Test Corp", "lei": "N/A", "title": "Test Corp",
                "cusip": "N/A", "isin": "", "ticker": "TEST",
                "balance": "100", "units": "NS", "cur_cd": "USD",
                "val_usd": "5000.00", "pct_val": "50.00",
                "payoff_profile": "Long", "asset_cat": "EC", "issuer_cat": "CORP",
                "inv_country": "US", "is_restricted_sec": "N", "fair_val_level": "1",
                "is_cash_collateral": "N", "is_non_cash_collateral": "N", "is_loan_by_fund": "N",
            },
        ]
        out = tmp_path / "out.csv"
        write_canonical_csv(holdings_dicts, out)
        parsed = parse_holdings(out)
        assert len(parsed) == 1
        assert parsed[0].name == "Test Corp"
        assert parsed[0].ticker == "TEST"
        assert parsed[0].val_usd == "5000.00"
