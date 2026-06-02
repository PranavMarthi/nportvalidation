"""Tests for split CSV holdings parsing and writing."""

import csv
import warnings
from dataclasses import asdict
from pathlib import Path

import pytest

from nport.config import parse_holdings
from nport.data_loader import write_split_csv
from nport.models import Holding


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    """Helper to write a CSV file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _base_headers():
    return [
        "holdingId", "name", "lei", "title", "cusip", "isin", "ticker",
        "balance", "units", "curCd", "valUSD", "pctVal", "payoffProfile",
        "assetCat", "issuerCat", "invCountry", "isRestrictedSec",
        "fairValLevel", "isCashCollateral", "isNonCashCollateral",
        "isLoanByFund",
    ]


def _equity_row(hid: str = "TST", **overrides) -> dict[str, str]:
    defaults = {
        "holdingId": hid, "name": "Test Stock", "lei": "549300DKPDN9M5S8GB14",
        "title": "Test Stock", "cusip": "58733R102", "isin": "US58733R1023",
        "ticker": "TST", "balance": "100", "units": "NS", "curCd": "USD",
        "valUSD": "10000.00", "pctVal": "1.00", "payoffProfile": "Long",
        "assetCat": "EC", "issuerCat": "CORP", "invCountry": "US",
        "isRestrictedSec": "N", "fairValLevel": "1",
        "isCashCollateral": "N", "isNonCashCollateral": "N",
        "isLoanByFund": "N",
    }
    defaults.update(overrides)
    return defaults


def _bond_row(hid: str = "AAPL29", **overrides) -> dict[str, str]:
    defaults = _equity_row(hid, name="Apple Inc", title="Apple Inc 3.25% 2029",
                           cusip="037833DX9", isin="US037833DX93", ticker="AAPL29",
                           balance="5000000", units="PA", valUSD="4925000.00",
                           pctVal="9.85", assetCat="DBT", fairValLevel="2")
    defaults.update(overrides)
    return defaults


def _debt_row(hid: str = "AAPL29") -> dict[str, str]:
    return {
        "holdingId": hid, "maturityDt": "2029-02-09", "couponKind": "Fixed",
        "annualizedRt": "3.25", "isDefault": "N", "areIntrstPmntsInArrs": "N",
        "isPaidKind": "N",
    }


class TestParseSplitHoldings:
    """Parse split CSVs into correct list[Holding]."""

    def test_base_only(self, tmp_path):
        """Base holdings.csv with holdingId, no satellites."""
        _write_csv(tmp_path / "holdings.csv", _base_headers(), [_equity_row()])
        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 1
        h = holdings[0]
        assert h.name == "Test Stock"
        assert h.ticker == "TST"
        assert h.maturity_dt == ""  # no debt satellite

    def test_base_plus_debt(self, tmp_path):
        """Base + debt_securities.csv merge correctly."""
        _write_csv(tmp_path / "holdings.csv", _base_headers(), [_bond_row()])
        debt_headers = ["holdingId", "maturityDt", "couponKind", "annualizedRt",
                        "isDefault", "areIntrstPmntsInArrs", "isPaidKind"]
        _write_csv(tmp_path / "debt_securities.csv", debt_headers, [_debt_row()])
        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 1
        h = holdings[0]
        assert h.name == "Apple Inc"
        assert h.maturity_dt == "2029-02-09"
        assert h.coupon_kind == "Fixed"
        assert h.annualized_rt == "3.25"

    def test_base_plus_derivatives(self, tmp_path):
        """Base + derivatives.csv merge correctly."""
        base_headers = _base_headers() + ["otherDesc", "otherValue"]
        base_row = _equity_row("SPX-C4800", name="SPX Call 4800", cusip="N/A",
                               isin="", ticker="", assetCat="DE", fairValLevel="2")
        base_row["otherDesc"] = "INTERNAL"
        base_row["otherValue"] = "SPX-C4800"
        _write_csv(tmp_path / "holdings.csv", base_headers, [base_row])

        deriv_headers = ["holdingId", "derivCat", "counterpartyName",
                         "counterpartyLei", "unrealizedAppr", "putOrCall",
                         "writtenOrPur", "exercisePrice", "expDt", "delta"]
        deriv_row = {
            "holdingId": "SPX-C4800", "derivCat": "OPT",
            "counterpartyName": "Goldman Sachs", "counterpartyLei": "W22LROWP2IHZNBB6K528",
            "unrealizedAppr": "250000.00", "putOrCall": "Call",
            "writtenOrPur": "Purchased", "exercisePrice": "4800.00",
            "expDt": "2026-12-18", "delta": "0.72",
        }
        _write_csv(tmp_path / "derivatives.csv", deriv_headers, [deriv_row])

        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 1
        h = holdings[0]
        assert h.deriv_cat == "OPT"
        assert h.put_or_call == "Call"
        assert h.exercise_price == "4800.00"
        assert h.other_value == "SPX-C4800"

    def test_multiple_holdings_selective_satellites(self, tmp_path):
        """Multiple holdings — only some appear in satellite files."""
        base_rows = [_bond_row("AAPL29"), _equity_row("FGXX", name="FGXX Fund",
                      cusip="31846V336", ticker="FGXX", assetCat="STIV",
                      issuerCat="RF")]
        _write_csv(tmp_path / "holdings.csv", _base_headers(), base_rows)
        _write_csv(tmp_path / "debt_securities.csv",
                   ["holdingId", "maturityDt", "couponKind", "annualizedRt",
                    "isDefault", "areIntrstPmntsInArrs", "isPaidKind"],
                   [_debt_row("AAPL29")])

        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 2
        assert holdings[0].maturity_dt == "2029-02-09"
        assert holdings[1].maturity_dt == ""  # FGXX not in debt satellite

    def test_preserves_row_order(self, tmp_path):
        """Holdings returned in same order as base CSV."""
        rows = [
            _equity_row("ZZZ", name="Z Corp"),
            _equity_row("AAA", name="A Corp"),
            _equity_row("MMM", name="M Corp"),
        ]
        _write_csv(tmp_path / "holdings.csv", _base_headers(), rows)
        holdings = parse_holdings(tmp_path / "holdings.csv")
        names = [h.name for h in holdings]
        assert names == ["Z Corp", "A Corp", "M Corp"]


class TestAutoDetect:
    """Auto-detect flat vs split format by holdingId column presence."""

    def test_flat_csv_still_works(self, tmp_path):
        """CSV without holdingId uses flat code path."""
        headers = [
            "name", "lei", "title", "cusip", "isin", "ticker",
            "balance", "units", "curCd", "valUSD", "pctVal", "payoffProfile",
            "assetCat", "issuerCat", "invCountry", "isRestrictedSec",
            "fairValLevel", "isCashCollateral", "isNonCashCollateral",
            "isLoanByFund",
        ]
        row = {
            "name": "Test", "lei": "549300DKPDN9M5S8GB14",
            "title": "Test", "cusip": "58733R102", "isin": "", "ticker": "TST",
            "balance": "100", "units": "NS", "curCd": "USD",
            "valUSD": "10000.00", "pctVal": "1.00", "payoffProfile": "Long",
            "assetCat": "EC", "issuerCat": "CORP", "invCountry": "US",
            "isRestrictedSec": "N", "fairValLevel": "1",
            "isCashCollateral": "N", "isNonCashCollateral": "N",
            "isLoanByFund": "N",
        }
        _write_csv(tmp_path / "holdings.csv", headers, [row])
        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 1
        assert holdings[0].name == "Test"

    def test_split_csv_detected(self, tmp_path):
        """CSV with holdingId uses split code path."""
        _write_csv(tmp_path / "holdings.csv", _base_headers(), [_equity_row()])
        holdings = parse_holdings(tmp_path / "holdings.csv")
        assert len(holdings) == 1
        assert holdings[0].name == "Test Stock"


class TestWriteSplitCsv:
    """write_split_csv produces correct split files."""

    def test_equity_only_no_satellites(self, tmp_path):
        """Equity-only fund writes base CSV, no satellites."""
        holdings = [asdict(Holding(
            name="Test", lei="549300DKPDN9M5S8GB14", title="Test",
            cusip="58733R102", isin="", ticker="TST", balance="100",
            units="NS", cur_cd="USD", val_usd="10000.00", pct_val="1.00",
            payoff_profile="Long", asset_cat="EC", issuer_cat="CORP",
            inv_country="US", is_restricted_sec="N", fair_val_level="1",
            is_cash_collateral="N", is_non_cash_collateral="N",
            is_loan_by_fund="N",
        ))]
        written = write_split_csv(holdings, tmp_path)
        assert len(written) == 1
        assert written[0].name == "holdings.csv"
        assert not (tmp_path / "debt_securities.csv").exists()
        assert not (tmp_path / "derivatives.csv").exists()

    def test_debt_fund_creates_satellite(self, tmp_path):
        """Fund with debt securities creates debt_securities.csv."""
        holdings = [asdict(Holding(
            name="Apple Inc", lei="HWUPKR0MPOU8FGXBT394",
            title="Apple 3.25% 2029", cusip="037833DX9", isin="", ticker="AAPL29",
            balance="5000000", units="PA", cur_cd="USD", val_usd="4925000.00",
            pct_val="9.85", payoff_profile="Long", asset_cat="DBT",
            issuer_cat="CORP", inv_country="US", is_restricted_sec="N",
            fair_val_level="2", is_cash_collateral="N",
            is_non_cash_collateral="N", is_loan_by_fund="N",
            maturity_dt="2029-02-09", coupon_kind="Fixed",
            annualized_rt="3.25", is_default="N",
            are_intrst_pmnts_in_arrs="N", is_paid_kind="N",
        ))]
        written = write_split_csv(holdings, tmp_path)
        assert len(written) == 2
        assert (tmp_path / "debt_securities.csv").exists()
        # Read back and verify
        with open(tmp_path / "debt_securities.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["maturityDt"] == "2029-02-09"

    def test_round_trip(self, tmp_path):
        """Write split CSVs, read back — same Holding objects."""
        original = Holding(
            name="Apple Inc", lei="HWUPKR0MPOU8FGXBT394",
            title="Apple 3.25% 2029", cusip="037833DX9", isin="US037833DX93",
            ticker="AAPL29", balance="5000000", units="PA", cur_cd="USD",
            val_usd="4925000.00", pct_val="9.85", payoff_profile="Long",
            asset_cat="DBT", issuer_cat="CORP", inv_country="US",
            is_restricted_sec="N", fair_val_level="2",
            is_cash_collateral="N", is_non_cash_collateral="N",
            is_loan_by_fund="N", maturity_dt="2029-02-09",
            coupon_kind="Fixed", annualized_rt="3.25", is_default="N",
            are_intrst_pmnts_in_arrs="N", is_paid_kind="N",
        )
        write_split_csv([asdict(original)], tmp_path)
        parsed = parse_holdings(tmp_path / "holdings.csv")
        assert len(parsed) == 1
        assert parsed[0] == original

    def test_holding_id_generation(self, tmp_path):
        """holdingId generated from ticker, then other_value, then cusip."""
        holdings = [
            asdict(Holding(
                name="With Ticker", lei="X", title="X", cusip="X", isin="",
                ticker="TST", balance="1", units="NS", cur_cd="USD",
                val_usd="1", pct_val="0.01", payoff_profile="Long",
                asset_cat="EC", issuer_cat="CORP", inv_country="US",
                is_restricted_sec="N", fair_val_level="1",
                is_cash_collateral="N", is_non_cash_collateral="N",
                is_loan_by_fund="N",
            )),
            asdict(Holding(
                name="With OtherValue", lei="X", title="X", cusip="N/A",
                isin="", ticker="", balance="1", units="NS", cur_cd="USD",
                val_usd="1", pct_val="0.01", payoff_profile="Long",
                asset_cat="EC", issuer_cat="CORP", inv_country="US",
                is_restricted_sec="N", fair_val_level="1",
                is_cash_collateral="N", is_non_cash_collateral="N",
                is_loan_by_fund="N", other_value="MY-ID",
            )),
            asdict(Holding(
                name="With Cusip", lei="X", title="X", cusip="12345ABC9",
                isin="", ticker="", balance="1", units="NS", cur_cd="USD",
                val_usd="1", pct_val="0.01", payoff_profile="Long",
                asset_cat="EC", issuer_cat="CORP", inv_country="US",
                is_restricted_sec="N", fair_val_level="1",
                is_cash_collateral="N", is_non_cash_collateral="N",
                is_loan_by_fund="N",
            )),
        ]
        write_split_csv(holdings, tmp_path)
        with open(tmp_path / "holdings.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        ids = [r["holdingId"] for r in rows]
        assert ids == ["TST", "MY-ID", "12345ABC9"]

    def test_satellite_only_populated_columns(self, tmp_path):
        """Satellite files exclude columns that are all empty."""
        holdings = [asdict(Holding(
            name="Bond", lei="X", title="X", cusip="X", isin="", ticker="BND",
            balance="1", units="PA", cur_cd="USD", val_usd="1", pct_val="0.01",
            payoff_profile="Long", asset_cat="DBT", issuer_cat="CORP",
            inv_country="US", is_restricted_sec="N", fair_val_level="2",
            is_cash_collateral="N", is_non_cash_collateral="N",
            is_loan_by_fund="N",
            maturity_dt="2029-01-01", coupon_kind="Fixed", annualized_rt="3.0",
            # is_default, are_intrst_pmnts_in_arrs, is_paid_kind left empty
        ))]
        write_split_csv(holdings, tmp_path)
        with open(tmp_path / "debt_securities.csv", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
        # Only populated columns should be present
        assert "maturityDt" in headers
        assert "couponKind" in headers
        assert "annualizedRt" in headers
        # Empty columns excluded
        assert "isDefault" not in headers
        assert "areIntrstPmntsInArrs" not in headers


class TestMissingHoldingId:
    """Satellite has holdingId not found in base → warning."""

    def test_unknown_satellite_id_warns(self, tmp_path):
        """Unknown holdingId in satellite produces a warning."""
        _write_csv(tmp_path / "holdings.csv", _base_headers(), [_equity_row("TST")])
        debt_headers = ["holdingId", "maturityDt", "couponKind", "annualizedRt",
                        "isDefault", "areIntrstPmntsInArrs", "isPaidKind"]
        _write_csv(tmp_path / "debt_securities.csv", debt_headers,
                   [_debt_row("UNKNOWN")])

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            holdings = parse_holdings(tmp_path / "holdings.csv")

        assert len(holdings) == 1  # base row still parsed
        assert any("UNKNOWN" in str(warning.message) for warning in w)


class TestDuplicateHoldingId:
    """Duplicate holdingId in base → error."""

    def test_duplicate_id_raises(self, tmp_path):
        """Duplicate holdingId in base CSV raises ValueError."""
        rows = [_equity_row("DUP", name="First"), _equity_row("DUP", name="Second")]
        _write_csv(tmp_path / "holdings.csv", _base_headers(), rows)

        with pytest.raises(ValueError, match="duplicate holdingId 'DUP'"):
            parse_holdings(tmp_path / "holdings.csv")

    def test_missing_holdingid_value_raises(self, tmp_path):
        """Empty holdingId value raises ValueError."""
        row = _equity_row("")
        _write_csv(tmp_path / "holdings.csv", _base_headers(), [row])

        with pytest.raises(ValueError, match="missing holdingId value"):
            parse_holdings(tmp_path / "holdings.csv")
