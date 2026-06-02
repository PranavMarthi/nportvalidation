"""End-to-end multi-type fund tests — bond, buffered ETF, leveraged ETF, mixed."""

from lxml import etree

from nport.builder import NportBuilder
from nport.constants import NS_NPORT
from nport.input_validation import validate_all
from nport.models import FilingData, FundConfig, Holding
from nport.xsd_validator import NportValidator

NS = {"n": NS_NPORT}


def _config():
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


def _filing(**overrides):
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


def _holding(**overrides):
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


def _bond_h(**overrides):
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


def _option_h(**overrides):
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


def _swap_h(**overrides):
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


def _full_pipeline(holdings, filing_overrides=None):
    """Validate, build, and XSD-check a list of holdings. Returns (xml_bytes, root)."""
    config = _config()
    filing = _filing(**(filing_overrides or {}))

    errors, warnings = validate_all(config, filing, holdings)
    assert not errors, f"Validation errors: {errors}"

    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()

    xsd_errors = NportValidator().validate_xsd(xml_bytes)
    assert not xsd_errors, f"XSD errors: {xsd_errors}"

    root = etree.fromstring(xml_bytes)
    return xml_bytes, root


class TestBondFund:
    def test_validate_all_passes(self):
        holdings = [
            _bond_h(pct_val="40.00"),
            _bond_h(
                name="US Treasury", lei="254900HROIFWPRGM1V77",
                title="US Treasury Note 4.25% 2028", cusip="91282CKV1",
                isin="US91282CKV19", ticker="T428",
                balance="8000000", val_usd="8200000.00", pct_val="16.40",
                issuer_cat="UST", fair_val_level="1",
                maturity_dt="2028-11-15", annualized_rt="4.25",
            ),
            _holding(
                name="Cash Equiv", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="21750000.00", pct_val="43.50",
                fair_val_level="1",
            ),
        ]
        errors, _ = validate_all(_config(), _filing(), holdings)
        assert not errors

    def test_xml_has_debt_sec(self):
        holdings = [
            _bond_h(pct_val="50.00"),
            _holding(
                name="Cash", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="25000000.00", pct_val="50.00",
                fair_val_level="1",
            ),
        ]
        _, root = _full_pipeline(holdings)
        debt_secs = root.findall(".//n:debtSec", NS)
        assert len(debt_secs) >= 1
        assert debt_secs[0].find("n:maturityDt", NS).text == "2029-02-09"
        assert debt_secs[0].find("n:couponKind", NS).text == "Fixed"


class TestBufferedETF:
    def test_validate_all_passes(self):
        holdings = [
            _option_h(pct_val="30.00"),
            _option_h(
                name="SPX Put 4800", put_or_call="Put",
                exercise_price="4800.00", delta="-0.28",
                pct_val="12.00", val_usd="3000000.00",
                unrealized_appr="75000.00",
                other_value="SPX-P4800-DEC26",
            ),
            _holding(
                name="Treasury Collateral", cusip="91282CKV1",
                isin="US91282CKV19", ticker="T428",
                asset_cat="DBT", issuer_cat="UST",
                val_usd="29000000.00", pct_val="58.00",
                fair_val_level="1",
            ),
        ]
        errors, _ = validate_all(_config(), _filing(), holdings)
        assert not errors

    def test_xml_has_option_member(self):
        holdings = [
            _option_h(pct_val="40.00"),
            _holding(
                name="Cash", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="30000000.00", pct_val="60.00",
                fair_val_level="1",
            ),
        ]
        _, root = _full_pipeline(holdings)
        opts = root.findall(".//n:optionSwaptionWarrantDeriv", NS)
        assert len(opts) >= 1
        assert opts[0].get("derivCat") == "OPT"
        assert opts[0].find("n:putOrCall", NS).text == "Call"


class TestLeveragedETF:
    def test_validate_all_passes(self):
        holdings = [
            _swap_h(pct_val="0.67"),
            _holding(
                name="Treasury Collateral", cusip="91282CJR1",
                isin="US91282CJR14",
                asset_cat="DBT", issuer_cat="UST",
                val_usd="25000000.00", pct_val="50.00",
                fair_val_level="1",
                maturity_dt="2028-02-15", coupon_kind="Fixed",
                annualized_rt="4.0", is_default="N",
                are_intrst_pmnts_in_arrs="N", is_paid_kind="N",
            ),
            _holding(
                name="Cash", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="24500000.00", pct_val="49.00",
                fair_val_level="1",
            ),
        ]
        errors, _ = validate_all(_config(), _filing(), holdings)
        assert not errors

    def test_xml_has_swap_elements(self):
        holdings = [
            _swap_h(pct_val="1.00"),
            _holding(
                name="Cash", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="49500000.00", pct_val="99.00",
                fair_val_level="1",
            ),
        ]
        _, root = _full_pipeline(holdings)
        swaps = root.findall(".//n:swapDeriv", NS)
        assert len(swaps) >= 1
        assert swaps[0].get("derivCat") == "SWP"
        fl = swaps[0].find("n:floatingRecDesc", NS)
        assert fl is not None
        assert fl.get("floatingRtIndex") == "USD-SOFR-OIS"


class TestMixedFund:
    def test_equity_bond_derivative_combined(self):
        """Full pipeline with equity + bond + derivative in one fund."""
        holdings = [
            _holding(pct_val="30.00", val_usd="15000000.00"),
            _bond_h(pct_val="30.00", val_usd="15000000.00"),
            _option_h(pct_val="10.00", val_usd="5000000.00"),
            _holding(
                name="Cash", cusip="31846V336", isin="US31846V3362",
                ticker="FGXX", asset_cat="STIV", issuer_cat="RF",
                val_usd="15000000.00", pct_val="30.00",
                fair_val_level="1",
            ),
        ]
        xml_bytes, root = _full_pipeline(holdings)

        assert root.findall(".//n:debtSec", NS)
        assert root.findall(".//n:optionSwaptionWarrantDeriv", NS)

        secs = root.findall(".//n:invstOrSec", NS)
        assert len(secs) == 4
