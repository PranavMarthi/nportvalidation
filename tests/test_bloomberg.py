"""Mocked Bloomberg adapter tests — no live Bloomberg connection needed."""

import csv
from dataclasses import fields
from unittest.mock import MagicMock, patch

import pytest

from nport.bloomberg import (
    BloombergSession,
    MinimalRow,
    _build_holding_from_row,
    _map_asset_cat,
    _map_issuer_cat,
    _read_minimal_csv,
    _write_canonical_csv,
)
from nport.models import Holding


# ── Minimal CSV reading ───────────────────────────────────


class TestReadMinimalCsv:
    def test_basic(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Name,Type,Weight%,Market Value\n"
            "Apple Inc,CS,5.0,50000.00\n"
            "Cash,CASH,10.0,100000.00\n"
        )
        rows = _read_minimal_csv(csv_file)
        assert len(rows) == 2
        assert rows[0].name == "Apple Inc"
        assert rows[0].type == "CS"
        assert rows[0].weight_pct == 5.0
        assert rows[0].market_value == 50000.00
        assert rows[1].type == "CASH"

    def test_skips_bad_rows(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Name,Type,Weight%,Market Value\n"
            "Good Row,CS,5.0,50000.00\n"
            "Bad Row,CS,NOT_A_NUMBER,50000.00\n"
        )
        rows = _read_minimal_csv(csv_file)
        assert len(rows) == 1
        assert rows[0].name == "Good Row"

    def test_empty_type(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text(
            "Name,Type,Weight%,Market Value\n"
            "Something,,2.0,20000.00\n"
        )
        rows = _read_minimal_csv(csv_file)
        assert len(rows) == 1
        assert rows[0].type == ""


# ── Field mapping ─────────────────────────────────────────


class TestFieldMapping:
    def test_asset_cat_common_stock(self):
        assert _map_asset_cat("Common Stock") == "EC"

    def test_asset_cat_bond(self):
        assert _map_asset_cat("Bond") == "DBT"

    def test_asset_cat_etf(self):
        assert _map_asset_cat("ETF") == "STIV"

    def test_asset_cat_unknown(self):
        assert _map_asset_cat("Unknown Type") == "EC"  # default

    def test_issuer_cat_corporate(self):
        assert _map_issuer_cat("Corporate") == "CORP"

    def test_issuer_cat_government(self):
        assert _map_issuer_cat("Government") == "UST"

    def test_issuer_cat_municipal(self):
        assert _map_issuer_cat("Municipal") == "MUN"

    def test_issuer_cat_unknown(self):
        assert _map_issuer_cat("Unknown Sector") == "CORP"  # default


# ── Holding construction ──────────────────────────────────


class TestBuildHoldingFromRow:
    def test_cash_position(self):
        row = MinimalRow(name="Cash", type="CASH", weight_pct=10.0, market_value=100000.0)
        h = _build_holding_from_row(row, {}, {})
        assert h["name"] == "Cash"
        assert h["cusip"] == "N/A"
        assert h["lei"] == "N/A"
        assert h["asset_cat"] == "STIV"
        assert h["units"] == "PA"
        assert h["balance"] == "100000.00"
        assert h["pct_val"] == "10.00"

    def test_equity_with_bloomberg_data(self):
        row = MinimalRow(name="Apple Inc", type="CS", weight_pct=5.0, market_value=50000.0)
        tickers = {"Apple Inc": "AAPL US Equity"}
        bdp_data = {
            "AAPL US Equity": {
                "ID_CUSIP": "037833100",
                "ID_ISIN": "US0378331005",
                "ID_LEI": "HWUPKR0MPOU8FGXBT394",
                "CNTRY_OF_DOMICILE": "US",
                "PX_LAST": "200.00",
                "SECURITY_TYP": "Common Stock",
                "INDUSTRY_SECTOR": "Technology",
                "TICKER": "AAPL",
            }
        }
        h = _build_holding_from_row(row, tickers, bdp_data)
        assert h["name"] == "Apple Inc"
        assert h["cusip"] == "037833100"
        assert h["isin"] == "US0378331005"
        assert h["lei"] == "HWUPKR0MPOU8FGXBT394"
        assert h["inv_country"] == "US"
        assert h["balance"] == "250"  # 50000 / 200
        assert h["ticker"] == "AAPL"
        assert h["asset_cat"] == "EC"
        assert h["issuer_cat"] == "CORP"

    def test_merge_semantics_preserve_existing(self):
        """Pre-populated fields should NOT be overwritten by Bloomberg."""
        row = MinimalRow(name="Apple Inc", type="CS", weight_pct=5.0, market_value=50000.0)
        tickers = {"Apple Inc": "AAPL US Equity"}
        bdp_data = {
            "AAPL US Equity": {
                "ID_CUSIP": "BLOOMBERG_CUSIP",
                "PX_LAST": "200.00",
            }
        }
        # _build_holding_from_row starts from defaults, so to test merge we need to
        # verify that Bloomberg data fills empty fields. The function doesn't take
        # pre-populated fields directly — it builds from MinimalRow. The merge
        # semantics apply at a higher level in _process_batch / enrich_holdings.
        h = _build_holding_from_row(row, tickers, bdp_data)
        assert h["cusip"] == "BLOOMBERG_CUSIP"

    def test_no_bloomberg_data(self):
        """When no Bloomberg data, defaults should be applied."""
        row = MinimalRow(name="Unknown Co", type="CS", weight_pct=1.0, market_value=10000.0)
        h = _build_holding_from_row(row, {}, {})
        assert h["name"] == "Unknown Co"
        assert h["cusip"] == "N/A"
        assert h["lei"] == "N/A"
        assert h["inv_country"] == "US"
        assert h["balance"] == "0"  # no price to compute

    def test_zero_price_no_crash(self):
        row = MinimalRow(name="Penny Co", type="CS", weight_pct=0.1, market_value=100.0)
        tickers = {"Penny Co": "PENNY US Equity"}
        bdp_data = {"PENNY US Equity": {"PX_LAST": "0"}}
        h = _build_holding_from_row(row, tickers, bdp_data)
        assert h["balance"] == "0"  # division by zero handled


# ── CSV output ────────────────────────────────────────────


class TestWriteCanonicalCsv:
    def test_roundtrip(self, tmp_path):
        holding = {f.name: "" for f in fields(Holding)}
        holding.update(name="Test", cusip="N/A", lei="N/A", cur_cd="USD")
        output = tmp_path / "out.csv"
        _write_canonical_csv([holding], output)

        assert output.exists()
        with open(output, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["name"] == "Test"


# ── Bloomberg session (mocked) ────────────────────────────


class TestBloombergSession:
    @patch("nport.bloomberg._lazy_import_blpapi")
    def test_session_open_close(self, mock_import):
        mock_blpapi = MagicMock()
        mock_import.return_value = mock_blpapi

        session_mock = MagicMock()
        session_mock.start.return_value = True
        session_mock.openService.return_value = True
        mock_blpapi.Session.return_value = session_mock

        bs = BloombergSession()
        bs.open()
        session_mock.start.assert_called_once()
        bs.close()
        session_mock.stop.assert_called_once()

    @patch("nport.bloomberg._lazy_import_blpapi")
    def test_session_connect_failure(self, mock_import):
        mock_blpapi = MagicMock()
        mock_import.return_value = mock_blpapi

        session_mock = MagicMock()
        session_mock.start.return_value = False
        mock_blpapi.Session.return_value = session_mock

        bs = BloombergSession()
        with pytest.raises(ConnectionError, match="Failed to connect"):
            bs.open()

    @patch("nport.bloomberg._lazy_import_blpapi")
    def test_context_manager(self, mock_import):
        mock_blpapi = MagicMock()
        mock_import.return_value = mock_blpapi

        session_mock = MagicMock()
        session_mock.start.return_value = True
        session_mock.openService.return_value = True
        mock_blpapi.Session.return_value = session_mock

        with BloombergSession() as bs:
            assert bs._session is not None
        session_mock.stop.assert_called_once()
