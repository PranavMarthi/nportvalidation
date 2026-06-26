"""Shared test fixtures."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from nport.config import parse_config, parse_filing, parse_holdings
from nport.models import FilingData, FundConfig, Holding

_ROOT = Path(__file__).resolve().parent.parent


_FDRS_DIR = _ROOT / "data" / "funds" / "fdrs"


@pytest.fixture(scope="session")
def fdrs_dir():
    return _FDRS_DIR


@pytest.fixture(scope="session")
def schema_dir():
    return _ROOT / "schemas" / "v1_13"


@pytest.fixture(scope="session")
def reference_xml():
    return _ROOT / "reference_nport.xml"


@pytest.fixture(scope="session")
def sample_data(fdrs_dir):
    """Parsed FDRS Dec 2025 inputs."""
    return (
        parse_config(fdrs_dir / "fund_config.txt"),
        parse_filing(fdrs_dir / "filings" / "2025-12" / "filing_data.txt"),
        parse_holdings(fdrs_dir / "filings" / "2025-12" / "holdings.csv"),
    )


@pytest.fixture(scope="session")
def funds_dir():
    return _ROOT / "data" / "funds"


# ── Fixture helpers for multi-type fund tests ─────────────


def _test_config():
    return FundConfig(
        cik="0002078265", ccc="XXXXXXXX", reg_name="Corgi ETF Trust I",
        reg_file_number="811-24117", reg_cik="0002078265",
        reg_lei="529900HSQC73ZP7RGT16", reg_street1="425 Bush St.",
        reg_street2="Suite 500", reg_city="San Francisco",
        reg_state="US-CA", reg_country="US", reg_zip="94104",
        reg_phone="855-552-6744", series_name="Test Fund",
        series_id="S000096625", series_lei="529900Y4TPD7LE3K2C21",
        class_id="C000265520", signer_org="Corgi ETF Trust I",
        signer_name="Emily Yuan", signer_title="President & PEO",
    )


def _test_filing(**overrides):
    defaults = dict(
        submission_type="NPORT-P", live_test_flag="TEST",
        rep_pd_end="2025-12-31", rep_pd_date="2025-12-31",
        is_final_filing="N", date_signed="2026-02-24",
        tot_assets="50200000.00", tot_liabs="200000.00",
        net_assets="50000000.00", assets_attr_misc_sec="0",
        assets_invested="0", amt_pay_one_yr_banks_borr="0",
        amt_pay_one_yr_ctrld_comp="0", amt_pay_one_yr_oth_affil="0",
        amt_pay_one_yr_other="0", amt_pay_aft_one_yr_banks_borr="0",
        amt_pay_aft_one_yr_ctrld_comp="0", amt_pay_aft_one_yr_oth_affil="0",
        amt_pay_aft_one_yr_other="0", delay_deliv="0", stand_by_commit="0",
        liquid_pref="0", is_non_cash_collateral="N",
        rtn1="0.35", rtn2="0.42", rtn3="0.28",
        net_realized_gain_mon1="0", net_unrealized_appr_mon1="0",
        net_realized_gain_mon2="0", net_unrealized_appr_mon2="0",
        net_realized_gain_mon3="0", net_unrealized_appr_mon3="0",
        mon1_sales="0", mon1_redemption="0", mon1_reinvestment="0",
        mon2_sales="0", mon2_redemption="0", mon2_reinvestment="0",
        mon3_sales="0", mon3_redemption="0", mon3_reinvestment="0",
        name_designated_index="N/A", index_identifier="N/A",
    )
    defaults.update(overrides)
    return FilingData(**defaults)


def _equity_holding(**overrides):
    defaults = dict(
        name="Test Stock", lei="549300DKPDN9M5S8GB14",
        title="Test Stock", cusip="58733R102", isin="US58733R1023",
        ticker="TST", balance="100", units="NS", cur_cd="USD",
        val_usd="10000.00", pct_val="1.00", payoff_profile="Long",
        asset_cat="EC", issuer_cat="CORP", inv_country="US",
        is_restricted_sec="N", fair_val_level="1",
        is_cash_collateral="N", is_non_cash_collateral="N",
        is_loan_by_fund="N",
    )
    defaults.update(overrides)
    return Holding(**defaults)


def _bond_holding(**overrides):
    defaults = dict(
        name="Apple Inc", lei="HWUPKR0MPOU8FGXBT394",
        title="Apple Inc 3.25% 2029", cusip="037833DX9",
        isin="US037833DX93", ticker="AAPL29",
        balance="5000000", units="PA", cur_cd="USD",
        val_usd="4925000.00", pct_val="9.85", payoff_profile="Long",
        asset_cat="DBT", issuer_cat="CORP", inv_country="US",
        is_restricted_sec="N", fair_val_level="2",
        is_cash_collateral="N", is_non_cash_collateral="N",
        is_loan_by_fund="N",
        maturity_dt="2029-02-09", coupon_kind="Fixed",
        annualized_rt="3.25", is_default="N",
        are_intrst_pmnts_in_arrs="N", is_paid_kind="N",
    )
    defaults.update(overrides)
    return Holding(**defaults)


def _option_holding(**overrides):
    defaults = dict(
        name="SPX Call 4800", lei="W22LROWP2IHZNBB6K528",
        title="SPX Call 4800 Dec26", cusip="N/A",
        isin="", ticker="",
        balance="50", units="NC", cur_cd="USD",
        val_usd="7500000.00", pct_val="30.00", payoff_profile="Long",
        asset_cat="DE", issuer_cat="CORP", inv_country="US",
        is_restricted_sec="N", fair_val_level="2",
        is_cash_collateral="N", is_non_cash_collateral="N",
        is_loan_by_fund="N",
        deriv_cat="OPT", counterparty_name="Goldman Sachs International",
        counterparty_lei="W22LROWP2IHZNBB6K528",
        unrealized_appr="250000.00",
        put_or_call="Call", written_or_pur="Purchased",
        share_no="5000", exercise_price="4800.00",
        exercise_price_cur_cd="USD", exp_dt="2026-12-18", delta="0.72",
        ref_inst_type="indexBasket",
        ref_index_name="S&P 500 Index", ref_index_identifier="SPX",
        other_desc="INTERNAL", other_value="SPX-C4800-DEC26",
    )
    defaults.update(overrides)
    return Holding(**defaults)


@pytest.fixture
def factories():
    """Holding/config/filing builders for multi-type tests (keyword overrides)."""
    return SimpleNamespace(
        config=_test_config, filing=_test_filing, equity=_equity_holding,
        bond=_bond_holding, option=_option_holding, swap=_swap_holding,
    )


def _swap_holding(**overrides):
    defaults = dict(
        name="SPX TRS JPMorgan", lei="8I5DZWZKVSZI1NUHU748",
        title="S&P 500 Total Return Swap JPM", cusip="N/A",
        isin="", ticker="",
        balance="50000000", units="NC", cur_cd="USD",
        val_usd="500000.00", pct_val="0.67", payoff_profile="Long",
        asset_cat="DE", issuer_cat="CORP", inv_country="US",
        is_restricted_sec="N", fair_val_level="2",
        is_cash_collateral="N", is_non_cash_collateral="N",
        is_loan_by_fund="N",
        deriv_cat="SWP", counterparty_name="JPMorgan Chase Bank NA",
        counterparty_lei="8I5DZWZKVSZI1NUHU748",
        unrealized_appr="500000.00",
        swap_flag="N", termination_dt="2026-06-30",
        upfront_pmnt="0", pmnt_cur_cd="USD",
        upfront_rcpt="0", rcpt_cur_cd="USD",
        notional_amt="50000000.00", swap_cur_cd="USD",
        rec_fixed_or_floating="Floating",
        rec_floating_rt_index="USD-SOFR-OIS",
        rec_floating_rt_spread="0.00",
        rec_pmnt_amt="0", rec_cur_cd="USD",
        rec_rate_tenor="Day", rec_rate_unit="1",
        pmnt_fixed_or_floating="Floating",
        pmnt_floating_rt_index="USD-SOFR-OIS",
        pmnt_floating_rt_spread="0.10",
        pmnt_pmnt_amt="0", pmnt_cur_cd_leg="USD",
        pmnt_rate_tenor="Day", pmnt_rate_unit="1",
        ref_inst_type="indexBasket",
        ref_index_name="S&P 500 Index", ref_index_identifier="SPX",
        other_desc="INTERNAL", other_value="SPX-TRS-JPM",
    )
    defaults.update(overrides)
    return Holding(**defaults)
