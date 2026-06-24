"""Tests for custodian CSV ingestion."""

import csv
import textwrap
from pathlib import Path

import pytest

from nport.custodian import (
    CustodianRow,
    HoldingType,
    ParsedOption,
    ParsedSwap,
    ParsedTreasury,
    build_corporate_bond_entry,
    classify_holding,
    filter_by_account,
    generate_filing_template,
    ingest_account,
    parse_custodian_csv,
    parse_option_name,
    parse_swap_ticker,
    parse_treasury_name,
    transform_to_holding_dict,
    update_security_master,
    write_security_master,
)


# ── Helpers ───────────────────────────────────────────────────


def _row(**overrides) -> CustodianRow:
    """Build a CustodianRow with sensible defaults."""
    defaults = dict(
        date="06/01/2026",
        account="FDRS",
        stock_ticker="ABNB",
        cusip="009066101",
        security_name="Airbnb Inc",
        shares="8790.00000000",
        price="133.310000",
        market_value="1171794.90",
        weightings="1.23%",
        net_assets="95625678.00",
        shares_outstanding="4000000",
        creation_units="160",
        money_market_flag="",
    )
    defaults.update(overrides)
    return CustodianRow(**defaults)


def _write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    """Write a custodian CSV to tmp_path and return the file path."""
    headers = [
        "Date", "Account", "StockTicker", "CUSIP", "SecurityName",
        "Shares", "Price", "MarketValue", "Weightings", "NetAssets",
        "SharesOutstanding", "CreationUnits", "MoneyMarketFlag",
    ]
    path = tmp_path / "test_custodian.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


_EQUITY_ROW = {
    "Date": "06/01/2026", "Account": "FDRS", "StockTicker": "ABNB",
    "CUSIP": "009066101", "SecurityName": "Airbnb Inc",
    "Shares": "8790.00000000", "Price": "133.310000",
    "MarketValue": "1171794.90", "Weightings": "1.23%",
    "NetAssets": "95625678.00", "SharesOutstanding": "4000000",
    "CreationUnits": "160", "MoneyMarketFlag": "",
}

_OPTION_ROW = {
    "Date": "06/01/2026", "Account": "CMAY", "StockTicker": "2SPY  270430C00143730",
    "CUSIP": "0SPY00270430C00143730", "SecurityName": "SPY 04/30/2027 143.73 C",
    "Shares": "100.00000000", "Price": "5.500000",
    "MarketValue": "55000.00", "Weightings": "2.50%",
    "NetAssets": "2200000.00", "SharesOutstanding": "100000",
    "CreationUnits": "4", "MoneyMarketFlag": "",
}

_SWAP_ROW = {
    "Date": "06/01/2026", "Account": "CMAG", "StockTicker": "02079K305-TRS-05/31/27-L-CANT",
    "CUSIP": "", "SecurityName": "ALPHABET INC.-SWAP-CANT-L",
    "Shares": "1000.00000000", "Price": "175.000000",
    "MarketValue": "175000.00", "Weightings": "3.50%",
    "NetAssets": "5000000.00", "SharesOutstanding": "200000",
    "CreationUnits": "8", "MoneyMarketFlag": "",
}

_TREASURY_ROW = {
    "Date": "06/01/2026", "Account": "CMAY", "StockTicker": "912828ZN3",
    "CUSIP": "912828ZN3", "SecurityName": "United States Treasury Note/Bond 0.5% 04/30/2027",
    "Shares": "500000.00000000", "Price": "99.500000",
    "MarketValue": "497500.00", "Weightings": "22.50%",
    "NetAssets": "2200000.00", "SharesOutstanding": "100000",
    "CreationUnits": "4", "MoneyMarketFlag": "",
}

_MM_ROW = {
    "Date": "06/01/2026", "Account": "FDRS", "StockTicker": "FGXXX",
    "CUSIP": "31846V336", "SecurityName": "First American Government Obligations Fund 12/01/2031",
    "Shares": "50000.00000000", "Price": "1.000000",
    "MarketValue": "50000.00", "Weightings": "0.05%",
    "NetAssets": "95625678.00", "SharesOutstanding": "4000000",
    "CreationUnits": "160", "MoneyMarketFlag": "Y",
}

_CASH_ROW = {
    "Date": "06/01/2026", "Account": "FDRS", "StockTicker": "Cash&Other",
    "CUSIP": "", "SecurityName": "Cash & Other",
    "Shares": "0", "Price": "0",
    "MarketValue": "12345.67", "Weightings": "0.01%",
    "NetAssets": "95625678.00", "SharesOutstanding": "4000000",
    "CreationUnits": "160", "MoneyMarketFlag": "",
}


# ── TestParseCustodianCsv ─────────────────────────────────────


class TestParseCustodianCsv:
    def test_reads_csv_correct_count(self, tmp_path):
        path = _write_csv(tmp_path, [_EQUITY_ROW, _MM_ROW, _CASH_ROW])
        rows = parse_custodian_csv(path)
        assert len(rows) == 3

    def test_header_mapping(self, tmp_path):
        path = _write_csv(tmp_path, [_EQUITY_ROW])
        rows = parse_custodian_csv(path)
        r = rows[0]
        assert r.stock_ticker == "ABNB"
        assert r.cusip == "009066101"
        assert r.security_name == "Airbnb Inc"
        assert r.shares == "8790.00000000"
        assert r.money_market_flag == ""

    def test_empty_file(self, tmp_path):
        path = _write_csv(tmp_path, [])
        rows = parse_custodian_csv(path)
        assert rows == []


# ── TestFilterByAccount ───────────────────────────────────────


class TestFilterByAccount:
    def _make_rows(self):
        return [
            _row(account="FDRS"),
            _row(account="FDRS"),
            _row(account="CMAY"),
        ]

    def test_single_account(self):
        grouped = filter_by_account(self._make_rows(), "FDRS")
        assert "FDRS" in grouped
        assert len(grouped["FDRS"]) == 2
        assert len(grouped) == 1

    def test_all_accounts(self):
        grouped = filter_by_account(self._make_rows(), None)
        assert len(grouped) == 2
        assert len(grouped["FDRS"]) == 2
        assert len(grouped["CMAY"]) == 1

    def test_unknown_account(self):
        grouped = filter_by_account(self._make_rows(), "ZZZZ")
        assert grouped["ZZZZ"] == []

    def test_case_insensitive_account(self):
        grouped = filter_by_account(self._make_rows(), "fdrs")
        assert "FDRS" in grouped
        assert len(grouped["FDRS"]) == 2


# ── TestClassifyHolding ──────────────────────────────────────


class TestClassifyHolding:
    def test_equity(self):
        assert classify_holding(_row()) == HoldingType.EQUITY

    def test_option_call(self):
        r = _row(security_name="SPY 04/30/2027 143.73 C", stock_ticker="2SPY  270430C00143730")
        assert classify_holding(r) == HoldingType.OPTION

    def test_option_put(self):
        r = _row(security_name="SPY 04/30/2027 143.73 P", stock_ticker="2SPY  270430P00143730")
        assert classify_holding(r) == HoldingType.OPTION

    def test_swap(self):
        r = _row(stock_ticker="02079K305-TRS-05/31/27-L-CANT")
        assert classify_holding(r) == HoldingType.SWAP

    def test_treasury(self):
        r = _row(security_name="United States Treasury Note/Bond 0.5% 04/30/2027", stock_ticker="912828ZN3")
        assert classify_holding(r) == HoldingType.TREASURY

    def test_corporate_bond(self):
        r = _row(security_name="ACCO Brands Corp 4.25% 03/15/2029", stock_ticker="", cusip="00081TAK4")
        assert classify_holding(r) == HoldingType.CORPORATE_BOND

    def test_corporate_bond_zero_coupon(self):
        r = _row(security_name="Service Properties Trust 0% 09/30/2027", stock_ticker="", cusip="81761LAB1")
        assert classify_holding(r) == HoldingType.CORPORATE_BOND

    def test_reit_equity_not_bond(self):
        # A REIT with no coupon%/maturity in the name stays an equity.
        r = _row(security_name="Essex Property Trust Inc", stock_ticker="ESS", cusip="297178105")
        assert classify_holding(r) == HoldingType.EQUITY

    def test_money_market(self):
        r = _row(stock_ticker="FGXXX", money_market_flag="Y")
        assert classify_holding(r) == HoldingType.MONEY_MARKET

    def test_cash(self):
        r = _row(stock_ticker="Cash&Other")
        assert classify_holding(r) == HoldingType.CASH

    def test_cash_with_mm_flag(self):
        """Cash&Other takes priority even if money_market_flag is Y."""
        r = _row(stock_ticker="Cash&Other", money_market_flag="Y")
        assert classify_holding(r) == HoldingType.CASH


# ── TestParseOptionName ──────────────────────────────────────


class TestParseOptionName:
    def test_spy_call(self):
        opt = parse_option_name("SPY 04/30/2027 143.73 C")
        assert opt == ParsedOption("SPY", "2027-04-30", "143.73", "Call")

    def test_spy_put(self):
        opt = parse_option_name("SPY 04/30/2027 143.73 P")
        assert opt == ParsedOption("SPY", "2027-04-30", "143.73", "Put")

    def test_eem_option(self):
        opt = parse_option_name("EEM 06/30/2027 42.00 C")
        assert opt.underlying == "EEM"
        assert opt.exp_dt == "2027-06-30"
        assert opt.exercise_price == "42.00"
        assert opt.put_or_call == "Call"

    def test_qqq_option(self):
        opt = parse_option_name("QQQ 12/31/2026 380.50 P")
        assert opt.underlying == "QQQ"
        assert opt.put_or_call == "Put"

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Cannot parse option name"):
            parse_option_name("INVALID")


# ── TestParseTreasuryName ────────────────────────────────────


class TestParseTreasuryName:
    def test_half_percent_bond(self):
        trs = parse_treasury_name("United States Treasury Note/Bond 0.5% 04/30/2027")
        assert trs == ParsedTreasury("0.5", "2027-04-30", "Fixed")

    def test_three_and_three_quarter(self):
        trs = parse_treasury_name("United States Treasury Note/Bond 3.75% 11/15/2028")
        assert trs == ParsedTreasury("3.75", "2028-11-15", "Fixed")

    def test_integer_rate(self):
        trs = parse_treasury_name("United States Treasury Note/Bond 4% 02/15/2030")
        assert trs == ParsedTreasury("4", "2030-02-15", "Fixed")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Cannot parse treasury name"):
            parse_treasury_name("Some Other Bond 5%")


# ── TestParseSwapTicker ──────────────────────────────────────


class TestParseSwapTicker:
    def test_individual_equity_swap(self):
        swap = parse_swap_ticker("02079K305-TRS-05/31/27-L-CANT")
        assert swap == ParsedSwap("02079K305", "2027-05-31", "Long", "CANT")

    def test_short_swap(self):
        swap = parse_swap_ticker("037833100-TRS-12/31/26-S-GS")
        assert swap == ParsedSwap("037833100", "2026-12-31", "Short", "GS")

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Cannot parse swap ticker"):
            parse_swap_ticker("ABNB")

    def test_no_counterparty(self):
        """FDRX format: no counterparty suffix."""
        swap = parse_swap_ticker("218946101-TRS-01/19/28-L")
        assert swap == ParsedSwap("218946101", "2028-01-19", "Long", "")

    def test_invalid_suffix(self):
        with pytest.raises(ValueError, match="Cannot parse swap ticker suffix"):
            parse_swap_ticker("02079K305-TRS-BAD")


# ── TestTransformEquity ──────────────────────────────────────


class TestTransformEquity:
    def test_full_fields(self):
        r = _row()
        d = transform_to_holding_dict(r, HoldingType.EQUITY)
        assert d["cusip"] == "009066101"
        assert d["ticker"] == "ABNB"
        assert d["balance"] == "8790.00000000"
        assert d["units"] == "NS"
        assert d["asset_cat"] == "EC"
        assert d["issuer_cat"] == "CORP"
        assert d["fair_val_level"] == "1"
        assert d["cur_cd"] == "USD"
        assert d["val_usd"] == "1171794.90"
        assert d["pct_val"] == "1.23"
        assert d["payoff_profile"] == "Long"
        assert d["name"] == "Airbnb Inc"
        assert d["title"] == "Airbnb Inc"
        assert d["is_restricted_sec"] == "N"
        assert d["is_cash_collateral"] == "N"
        assert d["is_non_cash_collateral"] == "N"
        assert d["is_loan_by_fund"] == "N"

    def test_short_equity(self):
        r = _row(shares="-100.00000000")
        d = transform_to_holding_dict(r, HoldingType.EQUITY)
        assert d["payoff_profile"] == "Short"

    def test_name_truncated_to_30_chars(self):
        r = _row(security_name="Grupo Aeroportuario del Sureste SAB de CV")
        d = transform_to_holding_dict(r, HoldingType.EQUITY)
        assert len(d["name"]) == 30
        assert d["name"] == "Grupo Aeroportuario del Surest"
        assert d["title"] == "Grupo Aeroportuario del Sureste SAB de CV"


# ── TestTransformOption ──────────────────────────────────────


class TestTransformOption:
    def test_purchased_call(self):
        r = _row(
            security_name="SPY 04/30/2027 143.73 C",
            stock_ticker="2SPY  270430C00143730",
            shares="100.00000000",
            market_value="55000.00",
            weightings="2.50%",
        )
        d = transform_to_holding_dict(r, HoldingType.OPTION)
        assert d["cusip"] == "N/A"
        assert d["ticker"] == "SPY-C143.73-20270430"
        assert d["balance"] == "100.0"
        assert d["units"] == "NC"
        assert d["asset_cat"] == "DE"
        assert d["deriv_cat"] == "OPT"
        assert d["put_or_call"] == "Call"
        assert d["exercise_price"] == "143.73"
        assert d["exercise_price_cur_cd"] == "USD"
        assert d["exp_dt"] == "2027-04-30"
        assert d["written_or_pur"] == "Purchased"
        assert d["payoff_profile"] == "Long"
        assert d["ref_inst_type"] == "indexBasket"
        assert d["ref_index_name"] == "S&P 500 Index"
        assert d["ref_index_identifier"] == "SPX"
        assert d["other_desc"] == "USER DEFINED"
        assert d["other_value"] == "SPY-C143.73-20270430"
        assert "unrealized_appr" not in d

    def test_written_put(self):
        r = _row(
            security_name="SPY 04/30/2027 143.73 P",
            stock_ticker="2SPY  270430P00143730",
            shares="-50.00000000",
            market_value="-25000.00",
            weightings="-1.10%",
        )
        d = transform_to_holding_dict(r, HoldingType.OPTION)
        assert d["written_or_pur"] == "Written"
        assert d["payoff_profile"] == "Short"
        assert d["put_or_call"] == "Put"
        assert d["balance"] == "50.0"
        assert d["ticker"] == "SPY-P143.73-20270430"
        assert d["other_value"] == "SPY-P143.73-20270430"


# ── TestTransformSwap ────────────────────────────────────────


class TestTransformSwap:
    def test_individual_equity_swap(self):
        r = _row(
            stock_ticker="02079K305-TRS-05/31/27-L-CANT",
            security_name="ALPHABET INC.-SWAP-CANT-L",
            shares="1000.00000000",
            market_value="175000.00",
            weightings="3.50%",
        )
        d = transform_to_holding_dict(r, HoldingType.SWAP)
        assert d["name"] == "N/A"
        assert d["lei"] == "N/A"
        assert d["title"] == "ALPHABET INC.-SWAP-CANT-L"
        assert d["cusip"] == "N/A"
        assert d["ticker"] == "02079K305-TRS-05/31/27-L-CANT"
        assert d["balance"] == "1"
        assert d["payoff_profile"] == "N/A"
        assert d["issuer_cat"] == "OTHER"
        assert d["issuer_conditional_desc"] == "N/A"
        assert d["deriv_cat"] == "SWP"
        assert d["swap_flag"] == "Y"
        assert d["termination_dt"] == "2027-05-31"
        assert d["swap_cur_cd"] == "USD"
        assert d["inv_country"] == "US"
        assert d["ref_inst_type"] == "otherRefInst"
        assert d["ref_issuer_name"] == "ALPHABET INC."
        assert d["ref_issue_title"] == "ALPHABET INC."
        assert d["ref_cusip"] == "02079K305"
        assert d["other_desc"] == "USER DEFINED"
        assert d["other_value"] == "02079K305-TRS-05/31/27-L-CANT"
        # These must come from fund accounting via security master
        assert d["val_usd"] == ""
        assert d["pct_val"] == ""
        assert d["notional_amt"] == ""
        assert d["unrealized_appr"] == ""

    def test_fdrx_swap(self):
        """FDRX format: no counterparty in ticker, space-separated name."""
        r = _row(
            stock_ticker="218946101-TRS-01/19/28-L",
            security_name="CORGI ETF TR SWAP CS",
            shares="1749131.00000000",
            market_value="43850714.17",
            weightings="199.78%",
        )
        d = transform_to_holding_dict(r, HoldingType.SWAP)
        assert d["name"] == "N/A"
        assert d["title"] == "CORGI ETF TR SWAP CS"
        assert d["ticker"] == "218946101-TRS-01/19/28-L"
        assert d["balance"] == "1"
        assert d["ref_issuer_name"] == "CORGI ETF TR"
        assert d["ref_cusip"] == "218946101"
        assert d["termination_dt"] == "2028-01-19"
        assert d["other_value"] == "218946101-TRS-01/19/28-L"


# ── TestTransformTreasury ────────────────────────────────────


class TestTransformTreasury:
    def test_debt_fields(self):
        r = _row(
            security_name="United States Treasury Note/Bond 0.5% 04/30/2027",
            cusip="912828ZN3",
            stock_ticker="912828ZN3",
            shares="500000.00000000",
            market_value="497500.00",
            weightings="22.50%",
        )
        d = transform_to_holding_dict(r, HoldingType.TREASURY)
        assert d["cusip"] == "912828ZN3"
        assert d["ticker"] == ""
        assert d["units"] == "PA"
        assert d["asset_cat"] == "DBT"
        assert d["issuer_cat"] == "UST"
        assert d["fair_val_level"] == "2"
        assert d["inv_country"] == "US"
        assert d["lei"] == "254900HROIFWPRGM1V77"
        assert d["maturity_dt"] == "2027-04-30"
        assert d["annualized_rt"] == "0.5"
        assert d["coupon_kind"] == "Fixed"
        assert d["is_default"] == "N"
        assert d["are_intrst_pmnts_in_arrs"] == "N"
        assert d["is_paid_kind"] == "N"


# ── TestCorporateBond ────────────────────────────────────────


class TestCorporateBond:
    def test_build_entry_leaves_bloomberg_fields_empty(self):
        r = _row(security_name="ACCO Brands Corp 4.25% 03/15/2029",
                 stock_ticker="", cusip="00081TAK4")
        e = build_corporate_bond_entry(r)
        assert e["assetCat"] == "DBT" and e["issuerCat"] == "CORP"
        assert e["cusip"] == "00081TAK4"
        # Bloomberg-owned identity + C.9 fields are EMPTY (filled by =BDP later).
        assert e["lei"] == "" and e["isin"] == "" and e["invCountry"] == ""
        assert e["maturityDt"] == "" and e["couponKind"] == "" and e["annualizedRt"] == ""

    def test_transform_debt_fields(self):
        r = _row(security_name="ACCO Brands Corp 4.25% 03/15/2029", stock_ticker="",
                 cusip="00081TAK4", shares="100000.00000000",
                 market_value="98500.00", weightings="2.50%")
        d = transform_to_holding_dict(r, HoldingType.CORPORATE_BOND)
        assert d["cusip"] == "00081TAK4"
        assert d["units"] == "PA"
        assert d["asset_cat"] == "DBT"
        assert d["issuer_cat"] == "CORP"
        assert d["fair_val_level"] == "2"
        assert d["is_default"] == "N"
        assert d["are_intrst_pmnts_in_arrs"] == "N"
        assert d["is_paid_kind"] == "N"
        # maturity/coupon/rate/country/lei NOT parsed here — Bloomberg fills them
        # via the master merge. Left empty so a missing lookup fails visibly.
        assert d.get("maturity_dt", "") == ""
        assert d.get("coupon_kind", "") == ""
        assert d.get("annualized_rt", "") == ""
        assert d.get("inv_country", "") == ""
        assert d.get("lei", "") == ""


# ── TestTransformMoneyMarket ─────────────────────────────────


class TestTransformMoneyMarket:
    def test_stiv_classification(self):
        r = _row(
            stock_ticker="FGXXX",
            cusip="31846V336",
            security_name="First American Government Obligations Fund 12/01/2031",
            shares="50000.00000000",
            market_value="50000.00",
            weightings="0.05%",
            money_market_flag="Y",
        )
        d = transform_to_holding_dict(r, HoldingType.MONEY_MARKET)
        assert d["cusip"] == "31846V336"
        assert d["ticker"] == "FGXXX"
        assert d["units"] == "NS"
        assert d["asset_cat"] == "STIV"
        assert d["issuer_cat"] == "RF"
        assert d["fair_val_level"] == "1"
        # Date stripped from name/title
        assert d["title"] == "First American Government Obligations Fund"
        assert d["name"] == "First American Government Obli"  # 30-char truncation
        assert "12/01/2031" not in d["title"]


# ── TestCashSkipped ──────────────────────────────────────────


class TestCashSkipped:
    def test_cash_excluded_from_ingest(self, tmp_path):
        """Cash&Other rows should be skipped with a warning message."""
        rows = [
            _row(stock_ticker="Cash&Other", security_name="Cash & Other",
                 market_value="12345.67"),
            _row(),  # equity — should survive
        ]
        # Create minimal fund dir
        fund_dir = tmp_path / "fund"
        fund_dir.mkdir()
        (fund_dir / "fund_config.txt").touch()  # not loaded, just needs to exist

        holdings, messages = ingest_account(rows, fund_dir, "2026-06")
        assert len(holdings) == 1  # only the equity
        cash_msgs = [m for m in messages if "Cash&Other" in m]
        assert len(cash_msgs) == 1
        assert "$12345.67" in cash_msgs[0]


# ── TestIngestAccount ────────────────────────────────────────


class TestIngestAccount:
    def test_equity_enrichment(self, tmp_path):
        """End-to-end: equity custodian row → enriched dict via security master."""
        # Set up fund dir with security master
        fund_dir = tmp_path / "fund"
        fund_dir.mkdir()
        sm_path = fund_dir / "security_master.csv"
        sm_path.write_text(
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
        )

        rows = [_row()]
        holdings, messages = ingest_account(rows, fund_dir, "2026-06")

        assert len(holdings) == 1
        h = holdings[0]
        assert h["lei"] == "549300HMUDNO0RY56D37"
        assert h["inv_country"] == "US"
        assert h["isin"] == "US0090661010"

    def test_no_security_master_warns(self, tmp_path):
        fund_dir = tmp_path / "fund"
        fund_dir.mkdir()

        rows = [_row()]
        holdings, messages = ingest_account(rows, fund_dir, "2026-06")

        assert len(holdings) == 1
        sm_msgs = [m for m in messages if "No security_master.csv" in m]
        assert len(sm_msgs) == 1

    def test_mixed_types(self, tmp_path):
        """Multiple holding types processed correctly."""
        fund_dir = tmp_path / "fund"
        fund_dir.mkdir()

        rows = [
            _row(),  # equity
            _row(stock_ticker="FGXXX", cusip="31846V336",
                 security_name="First American Government Obligations Fund 12/01/2031",
                 shares="50000.00000000", money_market_flag="Y"),
            _row(stock_ticker="Cash&Other", security_name="Cash & Other",
                 market_value="100.00"),
        ]
        holdings, messages = ingest_account(rows, fund_dir, "2026-06")
        assert len(holdings) == 2  # equity + MM, cash skipped
        types = {h["asset_cat"] for h in holdings}
        assert types == {"EC", "STIV"}


# ── TestIngestCLI ────────────────────────────────────────────


class TestIngestCLI:
    def test_dry_run(self, tmp_path, capsys):
        """CLI --dry-run transforms without writing XML."""
        from nport.cli import main

        # Write custodian CSV
        csv_path = _write_csv(tmp_path, [_EQUITY_ROW, _MM_ROW, _CASH_ROW])

        # Create fund dir with security master
        fund_dir = tmp_path / "fdrs"
        fund_dir.mkdir()
        (fund_dir / "fund_config.txt").write_text("")
        sm_path = fund_dir / "security_master.csv"
        sm_path.write_text(
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
            "First Amer Govt Oblg,549300R5MYM6VZF1RM44,First American Govt Obligations Fd,31846V336,US31846V3362,FGXXX,US,STIV,RF\n"
        )

        main([
            "ingest",
            "--custodian", str(csv_path),
            "--fund-dir", str(fund_dir),
            "--period", "2026-06",
            "--account", "FDRS",
            "--dry-run",
        ])
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "2 holdings" in captured.out

    def test_no_rows_for_account(self, tmp_path, capsys):
        """CLI exits with error when account has no rows."""
        from nport.cli import main

        csv_path = _write_csv(tmp_path, [_EQUITY_ROW])
        fund_dir = tmp_path / "zzzz"
        fund_dir.mkdir()
        (fund_dir / "fund_config.txt").write_text("")

        with pytest.raises(SystemExit):
            main([
                "ingest",
                "--custodian", str(csv_path),
                "--fund-dir", str(fund_dir),
                "--period", "2026-06",
                "--account", "ZZZZ",
            ])
        captured = capsys.readouterr()
        assert "No rows for account" in captured.err


# ── TestUpdateSecurityMaster ─────────────────────────────────


class TestUpdateSecurityMaster:
    """Tests for incremental security master updates."""

    def _make_sm(self, tmp_path, content):
        """Write a security_master.csv and return its path."""
        sm_path = tmp_path / "security_master.csv"
        sm_path.write_text(content)
        return sm_path

    def test_new_equity_added(self, tmp_path):
        """New equity position is added to empty security master."""
        sm_path = tmp_path / "security_master.csv"
        rows = [_row()]  # ABNB equity

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["added"] == 1
        assert stats["removed"] == 0
        assert stats["kept"] == 0
        assert len(entries) == 1
        assert entries[0]["ticker"] == "ABNB"
        assert entries[0]["cusip"] == "009066101"

    def test_existing_equity_preserved(self, tmp_path):
        """Existing equity entry is kept as-is (manual fields preserved)."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,MANUALLY_SET_LEI,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
        )
        rows = [_row()]  # same ABNB equity

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["added"] == 0
        assert stats["removed"] == 0
        assert stats["kept"] == 1
        assert len(entries) == 1
        # LEI was manually set — must be preserved
        assert entries[0]["lei"] == "MANUALLY_SET_LEI"

    def test_removed_position_dropped(self, tmp_path):
        """Position no longer in custodian is removed from security master."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
            "Old Stock,N/A,Old Stock Inc,999999999,,OLDX,US,EC,CORP\n"
        )
        rows = [_row()]  # only ABNB — OLDX should be removed

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["kept"] == 1
        assert stats["removed"] == 1
        assert stats["added"] == 0
        assert len(entries) == 1
        assert entries[0]["ticker"] == "ABNB"

    def test_mixed_add_keep_remove(self, tmp_path):
        """Mixed scenario: one kept, one added, one removed."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
            "Old Stock,N/A,Old Stock Inc,999999999,,OLDX,US,EC,CORP\n"
        )
        rows = [
            _row(),  # ABNB — kept
            _row(stock_ticker="MSFT", cusip="594918104", security_name="Microsoft Corp"),  # new
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["kept"] == 1
        assert stats["added"] == 1
        assert stats["removed"] == 1
        assert len(entries) == 2
        tickers = {e["ticker"] for e in entries}
        assert tickers == {"ABNB", "MSFT"}

    def test_option_keyed_by_ticker(self, tmp_path):
        """Options are matched by generated ticker ID."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat,"
            "derivCat,counterpartyName,counterpartyLei,putOrCall,writtenOrPur,"
            "exercisePrice,exercisePriceCurCd,expDt,delta,refInstType,refIndexName,refIndexIdentifier\n"
            "SPY 04/30/2027 143.73 C,N/A,SPY 04/30/2027 143.73 C,N/A,,SPY-C143.73-20270430,US,DE,CORP,"
            "OPT,MY COUNTERPARTY,LEI123,Call,Purchased,143.73,USD,2027-04-30,0.65,indexBasket,S&P 500 Index,SPX\n"
        )
        rows = [
            _row(
                security_name="SPY 04/30/2027 143.73 C",
                stock_ticker="2SPY  270430C00143730",
                shares="100.00000000",
            ),
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["kept"] == 1
        assert stats["added"] == 0
        # Counterparty and delta preserved
        assert entries[0]["counterpartyName"] == "MY COUNTERPARTY"
        assert entries[0]["delta"] == "0.65"

    def test_swap_keyed_by_ticker(self, tmp_path):
        """Swaps are matched by full swap ticker."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat,"
            "derivCat,counterpartyName,counterpartyLei,swapFlag,terminationDt,"
            "notionalAmt,swapCurCd,unrealizedAppr,valUSD,pctVal,"
            "recFixedOrFloating,recDesc,pmntFixedOrFloating,pmntFloatingRtIndex,"
            "pmntFloatingRtSpread,pmntPmntAmt,pmntCurCdLeg,pmntRateTenor,pmntRateUnit,"
            "refInstType,refIssuerName,refIssueTitle,refCusip,refIsin,refTicker\n"
            "N/A,N/A,ALPHABET INC.-SWAP-CANT-L,N/A,,02079K305-TRS-05/31/27-L-CANT,US,DE,OTHER,"
            "SWP,Cantor Fitzgerald,CANTLEI123,Y,2027-05-31,"
            "500000,USD,12345,175000,3.50,"
            ",,,,,,,,,"
            "otherRefInst,ALPHABET INC.,ALPHABET INC.,02079K305,,\n"
        )
        rows = [
            _row(
                stock_ticker="02079K305-TRS-05/31/27-L-CANT",
                security_name="ALPHABET INC.-SWAP-CANT-L",
                shares="1000.00000000",
            ),
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["kept"] == 1
        # Counterparty, notional, unrealized preserved
        assert entries[0]["counterpartyName"] == "Cantor Fitzgerald"
        assert entries[0]["notionalAmt"] == "500000"
        assert entries[0]["unrealizedAppr"] == "12345"

    def test_cash_rows_skipped(self, tmp_path):
        """Cash&Other rows are ignored during update."""
        sm_path = tmp_path / "security_master.csv"
        rows = [
            _row(stock_ticker="Cash&Other", security_name="Cash & Other"),
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert len(entries) == 0
        assert stats["added"] == 0

    def test_headers_expanded_for_new_options(self, tmp_path):
        """Headers expand when a fund gains its first option."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
        )
        rows = [
            _row(),  # equity — kept
            _row(
                security_name="SPY 04/30/2027 143.73 C",
                stock_ticker="2SPY  270430C00143730",
                shares="100.00000000",
            ),
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert "derivCat" in headers
        assert "counterpartyName" in headers
        assert "delta" in headers

    def test_write_and_roundtrip(self, tmp_path):
        """Written CSV can be read back correctly."""
        sm_path = tmp_path / "security_master.csv"
        rows = [_row()]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)
        write_security_master(entries, headers, sm_path)

        # Read back
        entries2, headers2, stats2 = update_security_master(rows, sm_path, tmp_path)

        assert stats2["kept"] == 1
        assert stats2["added"] == 0
        assert stats2["removed"] == 0

    def test_money_market_keyed_by_cusip(self, tmp_path):
        """Money market positions are matched by CUSIP."""
        sm_path = self._make_sm(tmp_path,
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "First Amer Govt Oblg,549300R5MYM6VZF1RM44,First American Government Obligations Fund,31846V336,US31846V3362,FGXXX,US,STIV,RF\n"
        )
        rows = [
            _row(stock_ticker="FGXXX", cusip="31846V336",
                 security_name="First American Government Obligations Fund 12/01/2031",
                 money_market_flag="Y"),
        ]

        entries, headers, stats = update_security_master(rows, sm_path, tmp_path)

        assert stats["kept"] == 1
        assert stats["added"] == 0
        # Original name preserved (not overwritten by build_mm_entry)
        assert entries[0]["name"] == "First Amer Govt Oblg"


# ── TestUpdateMastersCLI ─────────────────────────────────────


class TestUpdateMastersCLI:
    def test_dry_run(self, tmp_path, capsys):
        """CLI --dry-run shows changes without writing."""
        from nport.cli import main

        csv_path = _write_csv(tmp_path, [_EQUITY_ROW, _MM_ROW])

        fund_dir = tmp_path / "fdrs"
        fund_dir.mkdir()
        sm_path = fund_dir / "security_master.csv"
        sm_path.write_text(
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
        )

        main([
            "update-masters",
            "--custodian", str(csv_path),
            "--fund-dir", str(fund_dir),
            "--account", "FDRS",
            "--xml-dir", str(tmp_path),  # empty — no XMLs
            "--dry-run",
        ])
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "Added 1" in captured.out  # MM added
        assert "kept 1" in captured.out   # ABNB kept

    def test_writes_file(self, tmp_path, capsys):
        """CLI writes updated security master."""
        from nport.cli import main

        csv_path = _write_csv(tmp_path, [_EQUITY_ROW])

        fund_dir = tmp_path / "fdrs"
        fund_dir.mkdir()
        sm_path = fund_dir / "security_master.csv"
        # Start with ABNB + OLDX; OLDX should be removed
        sm_path.write_text(
            "name,lei,title,cusip,isin,ticker,invCountry,assetCat,issuerCat\n"
            "Airbnb Inc,549300HMUDNO0RY56D37,Airbnb Inc,009066101,US0090661010,ABNB,US,EC,CORP\n"
            "Old Stock,N/A,Old Stock Inc,999999999,,OLDX,US,EC,CORP\n"
        )

        main([
            "update-masters",
            "--custodian", str(csv_path),
            "--fund-dir", str(fund_dir),
            "--account", "FDRS",
            "--xml-dir", str(tmp_path),
        ])

        # Verify file was updated
        with open(sm_path) as f:
            content = f.read()
        assert "ABNB" in content
        assert "OLDX" not in content


# ── TestGenerateFilingTemplate ─────────────────────────────────


class TestGenerateFilingTemplate:
    """Tests for generate_filing_template()."""

    def test_fresh_template_created(self, tmp_path):
        """Creates a fresh template when no previous filing exists."""
        fund_dir = tmp_path / "cmay"
        fund_dir.mkdir()

        path = generate_filing_template(fund_dir, "2026-06")

        assert path == fund_dir / "filings" / "2026-06" / "filing_data.txt"
        assert path.exists()
        content = path.read_text()
        assert "repPdEnd=2026-06-30" in content
        assert "repPdDate=2026-06-30" in content
        assert "liveTestFlag=TEST" in content
        assert "totAssets=0" in content
        assert "netAssets=0" in content
        assert "rtn1=N/A" in content
        assert "mon1Sales=0" in content
        assert "# TODO:" in content

    def test_fresh_template_february(self, tmp_path):
        """Correctly handles February end dates."""
        fund_dir = tmp_path / "test"
        fund_dir.mkdir()

        path = generate_filing_template(fund_dir, "2026-02")
        content = path.read_text()
        assert "repPdEnd=2026-02-28" in content

    def test_copies_from_previous_period(self, tmp_path):
        """Copies from previous filing, updating dates and zeroing returns/flows."""
        fund_dir = tmp_path / "fdrs"
        fund_dir.mkdir()
        prev_dir = fund_dir / "filings" / "2026-05"
        prev_dir.mkdir(parents=True)
        prev_dir.joinpath("filing_data.txt").write_text(
            "# Old filing\n"
            "submissionType=NPORT-P\n"
            "liveTestFlag=TEST\n"
            "repPdEnd=2026-05-31\n"
            "repPdDate=2026-05-31\n"
            "isFinalFiling=N\n"
            "dateSigned=2026-07-15\n"
            "totAssets=50000000\n"
            "totLiabs=1000000\n"
            "netAssets=49000000\n"
            "rtn1=1.5\n"
            "rtn2=2.0\n"
            "rtn3=-0.5\n"
            "netRealizedGainMon1=1000\n"
            "mon1Sales=5000000\n"
            "mon1Redemption=2000000\n"
            "nameDesignatedIndex=N/A\n"
            "indexIdentifier=N/A\n"
        )

        path = generate_filing_template(fund_dir, "2026-06")

        content = path.read_text()
        # Dates updated
        assert "repPdEnd=2026-06-30" in content
        assert "repPdDate=2026-06-30" in content
        assert "2026-05-31" not in content
        # dateSigned reset
        assert "dateSigned=YYYY-MM-DD" in content
        # Returns zeroed to N/A
        assert "rtn1=N/A" in content
        assert "rtn2=N/A" in content
        assert "rtn3=N/A" in content
        # Flows zeroed
        assert "mon1Sales=0" in content
        assert "mon1Redemption=0" in content
        assert "netRealizedGainMon1=0" in content
        # Balance sheet preserved
        assert "totAssets=50000000" in content
        assert "netAssets=49000000" in content
        # Structural keys preserved
        assert "submissionType=NPORT-P" in content
        assert "nameDesignatedIndex=N/A" in content
        # TODO added
        assert "# TODO:" in content

    def test_skips_existing_filing(self, tmp_path):
        """Returns existing path without overwriting."""
        fund_dir = tmp_path / "test"
        target_dir = fund_dir / "filings" / "2026-06"
        target_dir.mkdir(parents=True)
        target = target_dir / "filing_data.txt"
        target.write_text("original content\n")

        path = generate_filing_template(fund_dir, "2026-06")

        assert path == target
        assert target.read_text() == "original content\n"

    def test_picks_most_recent_previous(self, tmp_path):
        """When multiple previous filings exist, picks the most recent."""
        fund_dir = tmp_path / "test"
        for period, end in [("2026-03", "2026-03-31"), ("2026-05", "2026-05-31")]:
            d = fund_dir / "filings" / period
            d.mkdir(parents=True)
            d.joinpath("filing_data.txt").write_text(
                f"repPdEnd={end}\ntotAssets=100\nrtn1=1.0\nmon1Sales=500\n"
            )

        path = generate_filing_template(fund_dir, "2026-06")
        content = path.read_text()

        # Should copy from 2026-05, not 2026-03
        assert "repPdEnd=2026-06-30" in content

    def test_live_flag_reset_to_test(self, tmp_path):
        """liveTestFlag=LIVE is reset to TEST when copying from previous period."""
        fund_dir = tmp_path / "test"
        prev_dir = fund_dir / "filings" / "2026-05"
        prev_dir.mkdir(parents=True)
        prev_dir.joinpath("filing_data.txt").write_text(
            "liveTestFlag=LIVE\n"
            "repPdEnd=2026-05-31\n"
            "repPdDate=2026-05-31\n"
            "totAssets=100\n"
            "rtn1=1.0\n"
            "mon1Sales=500\n"
        )

        path = generate_filing_template(fund_dir, "2026-06")
        content = path.read_text()
        assert "liveTestFlag=TEST" in content
        assert "liveTestFlag=LIVE" not in content

    def test_previous_todo_not_duplicated(self, tmp_path):
        """TODO comments from previous filing are not carried over."""
        fund_dir = tmp_path / "test"
        prev_dir = fund_dir / "filings" / "2026-05"
        prev_dir.mkdir(parents=True)
        prev_dir.joinpath("filing_data.txt").write_text(
            "# TODO: Update totAssets for 2026-05\n"
            "repPdEnd=2026-05-31\n"
            "repPdDate=2026-05-31\n"
            "totAssets=100\n"
            "rtn1=1.0\n"
            "mon1Sales=500\n"
        )

        path = generate_filing_template(fund_dir, "2026-06")
        content = path.read_text()

        # Should have exactly one TODO line (for the new period)
        todo_lines = [l for l in content.splitlines() if "# TODO:" in l]
        assert len(todo_lines) == 1
        assert "2026-06" in todo_lines[0]


# ── TestNewFilingCLI ───────────────────────────────────────────


class TestNewFilingCLI:
    def test_creates_template(self, tmp_path, capsys):
        """CLI creates a filing template for a single fund."""
        from nport.cli import main

        fund_dir = tmp_path / "cmay"
        fund_dir.mkdir()
        (fund_dir / "fund_config.txt").touch()

        main(["new-filing", "--period", "2026-07", "--fund-dir", str(fund_dir)])

        captured = capsys.readouterr()
        assert "created" in captured.out
        assert (fund_dir / "filings" / "2026-07" / "filing_data.txt").exists()

    def test_skips_existing(self, tmp_path, capsys):
        """CLI skips when filing already exists."""
        from nport.cli import main

        fund_dir = tmp_path / "cmay"
        target_dir = fund_dir / "filings" / "2026-07"
        target_dir.mkdir(parents=True)
        (fund_dir / "fund_config.txt").touch()
        (target_dir / "filing_data.txt").write_text("existing\n")

        main(["new-filing", "--period", "2026-07", "--fund-dir", str(fund_dir)])

        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert (target_dir / "filing_data.txt").read_text() == "existing\n"

    def test_all_funds(self, tmp_path, capsys):
        """CLI processes all fund subdirs in a parent directory."""
        from nport.cli import main

        parent = tmp_path / "funds"
        for name in ("aaa", "bbb"):
            d = parent / name
            d.mkdir(parents=True)
            (d / "fund_config.txt").touch()

        main(["new-filing", "--period", "2026-07", "--fund-dir", str(parent)])

        captured = capsys.readouterr()
        assert "aaa" in captured.out
        assert "bbb" in captured.out
        assert (parent / "aaa" / "filings" / "2026-07" / "filing_data.txt").exists()
        assert (parent / "bbb" / "filings" / "2026-07" / "filing_data.txt").exists()


# ── TestGuideCLI ───────────────────────────────────────────────


class TestGuideCLI:
    def test_prints_guide(self, capsys):
        from nport.cli import main

        main(["guide"])
        captured = capsys.readouterr()
        assert "N-PORT Monthly Filing Guide" in captured.out
        assert "STEP 1" in captured.out
        assert "STEP 5" in captured.out
