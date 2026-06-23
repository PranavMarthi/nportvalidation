"""Data models for N-PORT filing inputs."""

from dataclasses import dataclass


@dataclass
class FundConfig:
    """Static per-fund data that rarely changes."""
    cik: str
    ccc: str
    reg_name: str
    reg_file_number: str
    reg_cik: str
    reg_lei: str
    reg_street1: str
    reg_street2: str
    reg_city: str
    reg_state: str
    reg_country: str
    reg_zip: str
    reg_phone: str
    series_name: str
    series_id: str
    series_lei: str
    class_id: str
    signer_org: str
    signer_name: str
    signer_title: str


@dataclass
class FilingData:
    """Per-filing data that changes monthly."""
    submission_type: str
    live_test_flag: str  # "TEST" or "LIVE"; LIVE omits the element (matches EDGAR default)
    rep_pd_end: str
    rep_pd_date: str
    is_final_filing: str
    date_signed: str
    # Fund financials
    tot_assets: str
    tot_liabs: str
    net_assets: str
    # Balance sheet items
    assets_attr_misc_sec: str
    assets_invested: str
    amt_pay_one_yr_banks_borr: str
    amt_pay_one_yr_ctrld_comp: str
    amt_pay_one_yr_oth_affil: str
    amt_pay_one_yr_other: str
    amt_pay_aft_one_yr_banks_borr: str
    amt_pay_aft_one_yr_ctrld_comp: str
    amt_pay_aft_one_yr_oth_affil: str
    amt_pay_aft_one_yr_other: str
    delay_deliv: str
    stand_by_commit: str
    liquid_pref: str
    is_non_cash_collateral: str
    # Returns
    rtn1: str
    rtn2: str
    rtn3: str
    net_realized_gain_mon1: str
    net_unrealized_appr_mon1: str
    net_realized_gain_mon2: str
    net_unrealized_appr_mon2: str
    net_realized_gain_mon3: str
    net_unrealized_appr_mon3: str
    # Flows
    mon1_sales: str
    mon1_redemption: str
    mon1_reinvestment: str
    mon2_sales: str
    mon2_redemption: str
    mon2_reinvestment: str
    mon3_sales: str
    mon3_redemption: str
    mon3_reinvestment: str
    # Designated index (varInfo/fundsDesignatedInfo)
    name_designated_index: str
    index_identifier: str
    # B.3 Risk metrics (optional, JSON-encoded arrays/objects)
    cur_metrics_json: str = ""
    credit_sprd_risk_ig_json: str = ""
    credit_sprd_risk_nonig_json: str = ""


@dataclass
class Holding:
    """One portfolio holding (one row from holdings CSV)."""
    name: str
    lei: str
    title: str
    cusip: str
    isin: str
    ticker: str
    balance: str
    units: str
    cur_cd: str
    val_usd: str
    pct_val: str
    payoff_profile: str
    asset_cat: str
    issuer_cat: str
    inv_country: str
    is_restricted_sec: str
    fair_val_level: str
    is_cash_collateral: str
    is_non_cash_collateral: str
    is_loan_by_fund: str
    # Conditional elements
    issuer_conditional_desc: str = ""
    asset_conditional_desc: str = ""
    other_desc: str = ""
    other_value: str = ""
    exchange_rt: str = ""
    # Debt fields (C.9)
    maturity_dt: str = ""
    coupon_kind: str = ""
    annualized_rt: str = ""
    is_default: str = ""
    are_intrst_pmnts_in_arrs: str = ""
    is_paid_kind: str = ""
    # Derivative common
    deriv_cat: str = ""
    counterparty_name: str = ""
    counterparty_lei: str = ""
    unrealized_appr: str = ""
    # Options (C.11.c) — buffer funds
    put_or_call: str = ""
    written_or_pur: str = ""
    share_no: str = ""
    exercise_price: str = ""
    exercise_price_cur_cd: str = ""
    exp_dt: str = ""
    delta: str = ""
    # Reference instrument
    ref_inst_type: str = ""
    ref_index_name: str = ""
    ref_index_identifier: str = ""
    ref_issuer_name: str = ""
    ref_issue_title: str = ""
    ref_cusip: str = ""
    ref_isin: str = ""
    ref_ticker: str = ""
    # Swaps (C.11.f) — leveraged funds
    swap_flag: str = ""
    termination_dt: str = ""
    upfront_pmnt: str = ""
    pmnt_cur_cd: str = ""
    upfront_rcpt: str = ""
    rcpt_cur_cd: str = ""
    notional_amt: str = ""
    swap_cur_cd: str = ""
    # Receive leg
    rec_fixed_or_floating: str = ""
    rec_fixed_rt: str = ""
    rec_floating_rt_index: str = ""
    rec_floating_rt_spread: str = ""
    rec_pmnt_amt: str = ""
    rec_cur_cd: str = ""
    rec_rate_tenor: str = ""
    rec_rate_unit: str = ""
    rec_reset_dt: str = ""
    rec_reset_unit: str = ""
    rec_desc: str = ""
    # Pay leg
    pmnt_desc: str = ""
    pmnt_fixed_or_floating: str = ""
    pmnt_fixed_rt: str = ""
    pmnt_floating_rt_index: str = ""
    pmnt_floating_rt_spread: str = ""
    pmnt_pmnt_amt: str = ""
    pmnt_cur_cd_leg: str = ""
    pmnt_rate_tenor: str = ""
    pmnt_rate_unit: str = ""
    pmnt_reset_dt: str = ""
    pmnt_reset_unit: str = ""
    # Futures/forwards
    payoff_prof_deriv: str = ""  # payOffProf element for futures/forwards
    # Other derivatives
    other_deriv_desc: str = ""  # othDesc attribute on othDeriv element
