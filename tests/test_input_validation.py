"""Tests for input validation — field formats, value ranges, cross-field checks."""


from nport.input_validation import (
    validate_all,
    validate_config,
    validate_filing,
    validate_holding,
    validate_holdings,
)
from nport.models import FilingData, FundConfig, Holding

# ── Minimal valid objects for mutation testing ────────────


def _config(**overrides) -> FundConfig:
    defaults = dict(
        cik="0002078265", ccc="XXXXXXXX", reg_name="Corgi ETF Trust I",
        reg_file_number="811-24117", reg_cik="0002078265",
        reg_lei="529900HSQC73ZP7RGT16", reg_street1="425 Bush St.",
        reg_street2="Suite 500", reg_city="San Francisco",
        reg_state="US-CA", reg_country="US", reg_zip="94104",
        reg_phone="855-552-6744", series_name="Founder-Led ETF",
        series_id="S000096625", series_lei="529900Y4TPD7LE3K2C21",
        class_id="C000265520", signer_org="Corgi ETF Trust I",
        signer_name="Emily Yuan", signer_title="President & PEO",
    )
    defaults.update(overrides)
    return FundConfig(**defaults)


def _filing(**overrides) -> FilingData:
    defaults = dict(
        submission_type="NPORT-P", live_test_flag="TEST",
        rep_pd_end="2025-12-31",
        rep_pd_date="2025-12-31", is_final_filing="N",
        date_signed="2026-02-24", tot_assets="19914806.89",
        tot_liabs="9903037.79", net_assets="10011769.10",
        assets_attr_misc_sec="0", assets_invested="0",
        amt_pay_one_yr_banks_borr="0", amt_pay_one_yr_ctrld_comp="0",
        amt_pay_one_yr_oth_affil="0", amt_pay_one_yr_other="0",
        amt_pay_aft_one_yr_banks_borr="0", amt_pay_aft_one_yr_ctrld_comp="0",
        amt_pay_aft_one_yr_oth_affil="0", amt_pay_aft_one_yr_other="0",
        delay_deliv="0", stand_by_commit="0", liquid_pref="0",
        is_non_cash_collateral="N", rtn1="N/A", rtn2="N/A", rtn3="-1.34",
        net_realized_gain_mon1="0", net_unrealized_appr_mon1="0",
        net_realized_gain_mon2="0", net_unrealized_appr_mon2="0",
        net_realized_gain_mon3="-872.52", net_unrealized_appr_mon3="-108350.40",
        mon1_sales="0", mon1_redemption="0", mon1_reinvestment="0",
        mon2_sales="0", mon2_redemption="0", mon2_reinvestment="0",
        mon3_sales="10120740", mon3_redemption="0", mon3_reinvestment="0",
        name_designated_index="N/A", index_identifier="N/A",
    )
    defaults.update(overrides)
    return FilingData(**defaults)


def _holding(**overrides) -> Holding:
    defaults = dict(
        name="MercadoLibre Inc", lei="549300DKPDN9M5S8GB14",
        title="MercadoLibre Inc", cusip="58733R102", isin="US58733R1023",
        ticker="MELI", balance="91", units="NS", cur_cd="USD",
        val_usd="183297.66", pct_val="1.83", payoff_profile="Long",
        asset_cat="EC", issuer_cat="CORP", inv_country="UY",
        is_restricted_sec="N", fair_val_level="1", is_cash_collateral="N",
        is_non_cash_collateral="N", is_loan_by_fund="N",
    )
    defaults.update(overrides)
    return Holding(**defaults)


# ── Config ────────────────────────────────────────────────


class TestConfigValidation:
    def test_valid(self):
        assert validate_config(_config())[0] == []

    def test_bad_cik(self):
        errors, _ = validate_config(_config(cik="ABC"))
        assert any("cik" in e for e in errors)

    def test_bad_ccc_length(self):
        errors, _ = validate_config(_config(ccc="short"))
        assert any("ccc" in e for e in errors)

    def test_bad_lei(self):
        errors, _ = validate_config(_config(reg_lei="BADLEI!!!"))
        assert any("regLei" in e for e in errors)

    def test_na_lei_ok(self):
        assert not any("regLei" in e for e in validate_config(_config(reg_lei="N/A"))[0])

    def test_bad_series_id(self):
        errors, _ = validate_config(_config(series_id="INVALID"))
        assert any("seriesId" in e for e in errors)

    def test_bad_class_id(self):
        errors, _ = validate_config(_config(class_id="X000265520"))
        assert any("classId" in e for e in errors)

    def test_bad_file_number(self):
        errors, _ = validate_config(_config(reg_file_number="811_24117"))
        assert any("regFileNumber" in e for e in errors)

    def test_empty_name(self):
        errors, _ = validate_config(_config(reg_name=""))
        assert any("regName" in e for e in errors)

    def test_empty_signer(self):
        errors, _ = validate_config(_config(signer_name=""))
        assert any("signerName" in e for e in errors)

    def test_cik_mismatch_warns(self):
        _, warnings = validate_config(_config(cik="0001234567"))
        assert any("cik" in w and "regCik" in w for w in warnings)

    def test_bad_country(self):
        errors, _ = validate_config(_config(reg_country="USA"))
        assert any("regCountry" in e for e in errors)

    def test_state_format_warns(self):
        _, warnings = validate_config(_config(reg_state="CA"))
        assert any("regState" in w for w in warnings)


# ── Filing ────────────────────────────────────────────────


class TestFilingValidation:
    def test_valid(self):
        assert validate_filing(_filing())[0] == []

    def test_bad_submission_type(self):
        errors, _ = validate_filing(_filing(submission_type="NPORT-X"))
        assert any("submissionType" in e for e in errors)

    def test_amendment_type_ok(self):
        assert not any("submissionType" in e for e in validate_filing(_filing(submission_type="NPORT-P/A"))[0])

    def test_bad_date_format(self):
        errors, _ = validate_filing(_filing(rep_pd_end="12/31/2025"))
        assert any("repPdEnd" in e for e in errors)

    def test_impossible_date(self):
        errors, _ = validate_filing(_filing(rep_pd_end="2025-02-30"))
        assert any("repPdEnd" in e for e in errors)

    def test_bad_yn(self):
        errors, _ = validate_filing(_filing(is_final_filing="No"))
        assert any("isFinalFiling" in e for e in errors)

    def test_non_numeric_assets(self):
        errors, _ = validate_filing(_filing(tot_assets="abc"))
        assert any("totAssets" in e for e in errors)

    def test_nav_mismatch(self):
        errors, _ = validate_filing(_filing(net_assets="5000000"))
        assert any("NAV mismatch" in e for e in errors)

    def test_negative_assets(self):
        errors, _ = validate_filing(_filing(tot_assets="-1000"))
        assert any("non-negative" in e for e in errors)

    def test_signed_before_period_warns(self):
        _, warnings = validate_filing(_filing(date_signed="2025-12-01"))
        assert any("before" in w for w in warnings)

    def test_signed_very_late_warns(self):
        _, warnings = validate_filing(_filing(date_signed="2026-06-01"))
        assert any("days after" in w for w in warnings)

    def test_return_na_ok(self):
        assert not any("rtn1" in e for e in validate_filing(_filing(rtn1="N/A"))[0])


# ── Holdings ──────────────────────────────────────────────


class TestHoldingValidation:
    def test_valid(self):
        assert validate_holding(_holding(), 0)[0] == []

    def test_bad_lei(self):
        errors, _ = validate_holding(_holding(lei="BAD"), 0)
        assert any("lei" in e for e in errors)

    def test_na_lei_ok(self):
        assert not any("lei" in e for e in validate_holding(_holding(lei="N/A"), 0)[0])

    def test_bad_cusip(self):
        errors, _ = validate_holding(_holding(cusip="TOOLONG!!!"), 0)
        assert any("cusip" in e for e in errors)

    def test_na_cusip_ok(self):
        assert not any("cusip" in e for e in validate_holding(_holding(cusip="N/A"), 0)[0])

    def test_bad_units(self):
        errors, _ = validate_holding(_holding(units="SHARES"), 0)
        assert any("units" in e for e in errors)

    def test_bad_asset_cat(self):
        errors, _ = validate_holding(_holding(asset_cat="EQUITY"), 0)
        assert any("assetCat" in e for e in errors)

    def test_bad_issuer_cat(self):
        errors, _ = validate_holding(_holding(issuer_cat="CORPORATE"), 0)
        assert any("issuerCat" in e for e in errors)

    def test_bad_payoff_profile(self):
        errors, _ = validate_holding(_holding(payoff_profile="long"), 0)
        assert any("payoffProfile" in e for e in errors)

    def test_bad_fair_val_level(self):
        errors, _ = validate_holding(_holding(fair_val_level="4"), 0)
        assert any("fairValLevel" in e for e in errors)

    def test_bad_country(self):
        errors, _ = validate_holding(_holding(inv_country="USA"), 0)
        assert any("invCountry" in e for e in errors)

    def test_bad_isin(self):
        errors, _ = validate_holding(_holding(isin="BADFORMAT"), 0)
        assert any("isin" in e for e in errors)

    def test_non_usd_warns(self):
        _, warnings = validate_holding(_holding(cur_cd="EUR"), 0)
        assert any("not USD" in w for w in warnings)

    def test_bad_yn(self):
        errors, _ = validate_holding(_holding(is_restricted_sec="No"), 0)
        assert any("isRestrictedSec" in e for e in errors)

    def test_non_numeric_balance(self):
        errors, _ = validate_holding(_holding(balance="lots"), 0)
        assert any("balance" in e for e in errors)

    def test_empty_name(self):
        errors, _ = validate_holding(_holding(name=""), 0)
        assert any("name" in e for e in errors)


class TestHoldingsLevel:
    def test_empty_is_error(self):
        errors, _ = validate_holdings([])
        assert any("No holdings" in e for e in errors)

    def test_pct_sum_warns(self):
        _, warnings = validate_holdings([_holding(pct_val="5.0")])
        assert any("pctVal sum" in w for w in warnings)

    def test_duplicate_cusip_warns(self):
        _, warnings = validate_holdings([_holding(), _holding(name="Dup")])
        assert any("Duplicate CUSIPs" in w for w in warnings)


class TestFullValidation:
    def test_sample_data_passes(self, sample_data):
        config, filing, holdings = sample_data
        errors, _ = validate_all(config, filing, holdings)
        assert errors == []
