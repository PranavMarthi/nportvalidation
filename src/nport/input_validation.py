"""Input validation for N-PORT filing data.

Validates field formats, value ranges, and cross-field consistency
before XML generation. All format rules derived from SEC N-PORT XSD v1.13.
"""

import re
from datetime import date, datetime

from nport.models import FilingData, FundConfig, Holding

# ── Patterns from the XSD ─────────────────────────────────

_CIK_RE = re.compile(r"^\d{1,10}$")
_LEI_RE = re.compile(r"^([0-9A-Z]{20}|N/A)$")
_CUSIP_RE = re.compile(r"^([0-9A-HJ-NP-Z]{5}[0-9A-HJ-NP-Z#*@]{3}[0-9]|N/A|000000000)$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{10}$")
_SERIES_ID_RE = re.compile(r"^[Ss]\d{9}$")
_CLASS_ID_RE = re.compile(r"^[Cc]\d{9}$")
_FILE_NUMBER_RE = re.compile(r"^\d{3}-\d{5}$")
_YN_RE = re.compile(r"^[YN]$")
_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")

_VALID_SUBMISSION_TYPES = {"NPORT-P", "NPORT-NP", "NPORT-P/A", "NPORT-NP/A"}
_VALID_UNITS = {"NS", "PA", "NC", "OU"}
_VALID_ASSET_CATS = {
    "STIV", "RA", "EC", "EP", "DBT", "DCO", "DCR", "DE", "DFE",
    "DIR", "DO", "SN", "LON", "ABS-MBS", "ABS-APCP", "ABS-CBDO",
    "ABS-O", "COMM", "RE", "OTHER",
}
_VALID_ISSUER_CATS = {"CORP", "UST", "USGA", "USGSE", "MUN", "NUSS", "PF", "RF", "OTHER"}
_VALID_PAYOFF_PROFILES = {"Long", "Short", "N/A"}
_VALID_FAIR_VAL_LEVELS = {"1", "2", "3", "N/A"}

# Derivative / debt enums
_VALID_DERIV_CATS = {"FWD", "FUT", "SWP", "OPT", "SWO", "WAR", "OTH"}
_VALID_COUPON_KINDS = {"Fixed", "Floating", "Variable", "None"}
_VALID_PUT_CALL = {"Put", "Call"}
_VALID_WRITTEN_PUR = {"Written", "Purchased"}
_VALID_FIXED_FLOATING = {"Fixed", "Floating", "Other"}
_VALID_REF_INST_TYPES = {"indexBasket", "otherRefInst"}

# Fields that must be valid decimals
_BALANCE_SHEET_FIELDS = [
    "assets_attr_misc_sec", "assets_invested",
    "amt_pay_one_yr_banks_borr", "amt_pay_one_yr_ctrld_comp",
    "amt_pay_one_yr_oth_affil", "amt_pay_one_yr_other",
    "amt_pay_aft_one_yr_banks_borr", "amt_pay_aft_one_yr_ctrld_comp",
    "amt_pay_aft_one_yr_oth_affil", "amt_pay_aft_one_yr_other",
    "delay_deliv", "stand_by_commit", "liquid_pref",
]
_MONTHLY_NUMERIC_FIELDS = [
    "net_realized_gain_mon1", "net_unrealized_appr_mon1",
    "net_realized_gain_mon2", "net_unrealized_appr_mon2",
    "net_realized_gain_mon3", "net_unrealized_appr_mon3",
    "mon1_sales", "mon1_redemption", "mon1_reinvestment",
    "mon2_sales", "mon2_redemption", "mon2_reinvestment",
    "mon3_sales", "mon3_redemption", "mon3_reinvestment",
]

# ── Check helpers ──────────────────────────────────────────


def _check_re(errors, pattern, value, field):
    if not pattern.match(value):
        errors.append(f"{field}: invalid format '{value}'.")


def _check_set(errors, valid, value, field):
    if value not in valid:
        errors.append(f"{field}: invalid value '{value}' (expected: {', '.join(sorted(valid))}).")


def _check_date(errors, value, field):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        errors.append(f"{field}: invalid date '{value}' (expected YYYY-MM-DD).")


def _check_numeric(errors, value, field, allow_na=False):
    if allow_na and value == "N/A":
        return
    try:
        float(value)
    except ValueError:
        errors.append(f"{field}: not a valid number '{value}'.")


def _check_nonempty(errors, value, field):
    if not value.strip():
        errors.append(f"{field}: must not be empty.")


# ── Public validation ──────────────────────────────────────


def validate_config(config: FundConfig) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    _check_re(errors, _CIK_RE, config.cik, "cik")
    if len(config.ccc) != 8:
        errors.append(f"ccc: must be exactly 8 characters, got {len(config.ccc)}.")
    _check_nonempty(errors, config.reg_name, "regName")
    _check_re(errors, _FILE_NUMBER_RE, config.reg_file_number, "regFileNumber")
    _check_re(errors, _CIK_RE, config.reg_cik, "regCik")
    _check_re(errors, _LEI_RE, config.reg_lei, "regLei")
    _check_nonempty(errors, config.reg_street1, "regStreet1")
    _check_nonempty(errors, config.reg_city, "regCity")
    _check_re(errors, _COUNTRY_RE, config.reg_country, "regCountry")
    _check_nonempty(errors, config.series_name, "seriesName")
    _check_re(errors, _SERIES_ID_RE, config.series_id, "seriesId")
    _check_re(errors, _LEI_RE, config.series_lei, "seriesLei")
    _check_re(errors, _CLASS_ID_RE, config.class_id, "classId")
    _check_nonempty(errors, config.signer_org, "signerOrg")
    _check_nonempty(errors, config.signer_name, "signerName")
    _check_nonempty(errors, config.signer_title, "signerTitle")

    if config.cik != config.reg_cik:
        warnings.append(f"cik ({config.cik}) differs from regCik ({config.reg_cik}).")
    if config.reg_country == "US" and not config.reg_state.startswith("US-"):
        warnings.append(f"regState '{config.reg_state}' should start with 'US-'.")

    return errors, warnings


def validate_filing(filing: FilingData) -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    _check_set(errors, _VALID_SUBMISSION_TYPES, filing.submission_type, "submissionType")
    _check_date(errors, filing.rep_pd_end, "repPdEnd")
    _check_date(errors, filing.rep_pd_date, "repPdDate")
    _check_re(errors, _YN_RE, filing.is_final_filing, "isFinalFiling")
    _check_date(errors, filing.date_signed, "dateSigned")
    _check_numeric(errors, filing.tot_assets, "totAssets")
    _check_numeric(errors, filing.tot_liabs, "totLiabs")
    _check_numeric(errors, filing.net_assets, "netAssets")
    _check_re(errors, _YN_RE, filing.is_non_cash_collateral, "isNonCashCollateral")

    for field in _BALANCE_SHEET_FIELDS:
        _check_numeric(errors, getattr(filing, field), field)
    for rtn in ["rtn1", "rtn2", "rtn3"]:
        _check_numeric(errors, getattr(filing, rtn), rtn, allow_na=True)
    for field in _MONTHLY_NUMERIC_FIELDS:
        _check_numeric(errors, getattr(filing, field), field)

    # Cross-field checks (only if individual fields parsed OK)
    try:
        assets, liabs, net = float(filing.tot_assets), float(filing.tot_liabs), float(filing.net_assets)
        if abs(net - (assets - liabs)) > 0.02:
            errors.append(f"NAV mismatch: netAssets ({net}) != totAssets - totLiabs ({assets - liabs}).")
        if assets < 0:
            errors.append(f"totAssets must be non-negative, got {filing.tot_assets}.")
        if liabs < 0:
            errors.append(f"totLiabs must be non-negative, got {filing.tot_liabs}.")
    except ValueError:
        pass  # Individual field errors already reported above

    try:
        pd_end = datetime.strptime(filing.rep_pd_end, "%Y-%m-%d").date()
        signed = datetime.strptime(filing.date_signed, "%Y-%m-%d").date()
        if signed < pd_end:
            warnings.append(f"dateSigned ({filing.date_signed}) is before repPdEnd ({filing.rep_pd_end}).")
        if (signed - pd_end).days > 90:
            warnings.append(f"dateSigned is {(signed - pd_end).days} days after repPdEnd — filings due within 60 days.")
        if pd_end > date.today():
            warnings.append(f"repPdEnd ({filing.rep_pd_end}) is in the future.")
    except ValueError:
        pass

    return errors, warnings


def validate_holding(holding: Holding, index: int, rep_pd_end: str = "") -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    p = f"holding[{index}] ({holding.name})"

    _check_nonempty(errors, holding.name, f"{p}/name")
    _check_re(errors, _LEI_RE, holding.lei, f"{p}/lei")
    _check_nonempty(errors, holding.title, f"{p}/title")
    _check_re(errors, _CUSIP_RE, holding.cusip, f"{p}/cusip")
    _check_numeric(errors, holding.balance, f"{p}/balance")
    _check_set(errors, _VALID_UNITS, holding.units, f"{p}/units")
    _check_numeric(errors, holding.val_usd, f"{p}/valUSD")
    _check_numeric(errors, holding.pct_val, f"{p}/pctVal")
    _check_set(errors, _VALID_PAYOFF_PROFILES, holding.payoff_profile, f"{p}/payoffProfile")
    _check_set(errors, _VALID_ASSET_CATS, holding.asset_cat, f"{p}/assetCat")
    _check_set(errors, _VALID_ISSUER_CATS, holding.issuer_cat, f"{p}/issuerCat")
    _check_re(errors, _COUNTRY_RE, holding.inv_country, f"{p}/invCountry")
    _check_re(errors, _YN_RE, holding.is_restricted_sec, f"{p}/isRestrictedSec")
    _check_set(errors, _VALID_FAIR_VAL_LEVELS, holding.fair_val_level, f"{p}/fairValLevel")
    _check_re(errors, _YN_RE, holding.is_cash_collateral, f"{p}/isCashCollateral")
    _check_re(errors, _YN_RE, holding.is_non_cash_collateral, f"{p}/isNonCashCollateral")
    _check_re(errors, _YN_RE, holding.is_loan_by_fund, f"{p}/isLoanByFund")

    if holding.isin and not _ISIN_RE.match(holding.isin):
        errors.append(f"{p}/isin: invalid format '{holding.isin}'.")
    if holding.cur_cd != "USD":
        warnings.append(f"{p}/curCd: '{holding.cur_cd}' is not USD — non-USD not yet supported.")

    # Conditional element validation
    if holding.issuer_cat == "OTHER" and not holding.issuer_conditional_desc:
        warnings.append(f"{p}/issuerCat: 'OTHER' should have issuerConditionalDesc.")
    if holding.asset_cat == "OTHER" and not holding.asset_conditional_desc:
        warnings.append(f"{p}/assetCat: 'OTHER' should have assetConditionalDesc.")

    # Debt validation (when maturity_dt is set)
    if holding.maturity_dt:
        _check_date(errors, holding.maturity_dt, f"{p}/maturityDt")
        _check_set(errors, _VALID_COUPON_KINDS, holding.coupon_kind, f"{p}/couponKind")
        _check_numeric(errors, holding.annualized_rt, f"{p}/annualizedRt")
        if holding.is_default:
            _check_re(errors, _YN_RE, holding.is_default, f"{p}/isDefault")
        if holding.are_intrst_pmnts_in_arrs:
            _check_re(errors, _YN_RE, holding.are_intrst_pmnts_in_arrs, f"{p}/areIntrstPmntsInArrs")
        if holding.is_paid_kind:
            _check_re(errors, _YN_RE, holding.is_paid_kind, f"{p}/isPaidKind")

    # Derivative validation (when deriv_cat is set)
    if holding.deriv_cat:
        _check_set(errors, _VALID_DERIV_CATS, holding.deriv_cat, f"{p}/derivCat")
        _check_nonempty(errors, holding.counterparty_name, f"{p}/counterpartyName")
        _check_re(errors, _LEI_RE, holding.counterparty_lei, f"{p}/counterpartyLei")
        if holding.counterparty_lei == "N/A":
            warnings.append(f"{p}/counterpartyLei: real counterparties should have LEIs.")
        _check_numeric(errors, holding.unrealized_appr, f"{p}/unrealizedAppr")

        # Option-specific validation
        if holding.deriv_cat in ("OPT", "SWO", "WAR"):
            _check_set(errors, _VALID_PUT_CALL, holding.put_or_call, f"{p}/putOrCall")
            _check_set(errors, _VALID_WRITTEN_PUR, holding.written_or_pur, f"{p}/writtenOrPur")
            _check_numeric(errors, holding.exercise_price, f"{p}/exercisePrice")
            _check_date(errors, holding.exp_dt, f"{p}/expDt")
            _check_numeric(errors, holding.delta, f"{p}/delta", allow_na=True)
            if holding.share_no:
                _check_numeric(errors, holding.share_no, f"{p}/shareNo", allow_na=True)
            # Written options should have negative balance
            if holding.written_or_pur == "Written":
                try:
                    if float(holding.balance) > 0:
                        warnings.append(f"{p}: written option has positive balance.")
                except ValueError:
                    pass
            # Cross-field: exercise price should be positive
            try:
                if float(holding.exercise_price) <= 0:
                    warnings.append(f"{p}/exercisePrice: should be positive, got {holding.exercise_price}.")
            except ValueError:
                pass
            # Cross-field: delta should be in [-1, 1]
            if holding.delta and holding.delta != "N/A":
                try:
                    d = float(holding.delta)
                    if not (-1.0 <= d <= 1.0):
                        warnings.append(f"{p}/delta: should be in [-1, 1], got {holding.delta}.")
                except ValueError:
                    pass

        # Swap-specific validation
        if holding.deriv_cat == "SWP":
            _check_date(errors, holding.termination_dt, f"{p}/terminationDt")
            _check_numeric(errors, holding.notional_amt, f"{p}/notionalAmt")
            if not holding.rec_fixed_or_floating:
                errors.append(f"{p}/recFixedOrFloating: must not be empty for swaps.")
            else:
                _check_set(errors, _VALID_FIXED_FLOATING, holding.rec_fixed_or_floating, f"{p}/recFixedOrFloating")
                if holding.rec_fixed_or_floating == "Fixed":
                    _check_numeric(errors, holding.rec_fixed_rt, f"{p}/recFixedRt")
                elif holding.rec_fixed_or_floating == "Floating":
                    _check_nonempty(errors, holding.rec_floating_rt_index, f"{p}/recFloatingRtIndex")
                    _check_numeric(errors, holding.rec_floating_rt_spread, f"{p}/recFloatingRtSpread")
            if not holding.pmnt_fixed_or_floating:
                errors.append(f"{p}/pmntFixedOrFloating: must not be empty for swaps.")
            else:
                _check_set(errors, _VALID_FIXED_FLOATING, holding.pmnt_fixed_or_floating, f"{p}/pmntFixedOrFloating")
                if holding.pmnt_fixed_or_floating == "Fixed":
                    _check_numeric(errors, holding.pmnt_fixed_rt, f"{p}/pmntFixedRt")
                elif holding.pmnt_fixed_or_floating == "Floating":
                    _check_nonempty(errors, holding.pmnt_floating_rt_index, f"{p}/pmntFloatingRtIndex")
                    _check_numeric(errors, holding.pmnt_floating_rt_spread, f"{p}/pmntFloatingRtSpread")
            # Cross-field: swap may have expired
            if rep_pd_end and holding.termination_dt:
                try:
                    term = datetime.strptime(holding.termination_dt, "%Y-%m-%d").date()
                    pd_end = datetime.strptime(rep_pd_end, "%Y-%m-%d").date()
                    if term <= pd_end:
                        warnings.append(f"{p}: terminationDt ({holding.termination_dt}) <= repPdEnd ({rep_pd_end}) — swap may have expired.")
                except ValueError:
                    pass

        # Forward/Future-specific validation
        if holding.deriv_cat in ("FWD", "FUT"):
            _check_set(errors, _VALID_PAYOFF_PROFILES, holding.payoff_prof_deriv, f"{p}/payoffProfDeriv")
            if holding.exp_dt:
                _check_date(errors, holding.exp_dt, f"{p}/expDt")
            if holding.notional_amt:
                _check_numeric(errors, holding.notional_amt, f"{p}/notionalAmt")

    # Reference instrument validation (applies to all derivatives with ref_inst_type)
    if holding.ref_inst_type:
        _check_set(errors, _VALID_REF_INST_TYPES, holding.ref_inst_type, f"{p}/refInstType")
        if holding.ref_inst_type == "indexBasket":
            _check_nonempty(errors, holding.ref_index_name, f"{p}/refIndexName")
            _check_nonempty(errors, holding.ref_index_identifier, f"{p}/refIndexIdentifier")
        elif holding.ref_inst_type == "otherRefInst":
            _check_nonempty(errors, holding.ref_issuer_name, f"{p}/refIssuerName")
            _check_nonempty(errors, holding.ref_issue_title, f"{p}/refIssueTitle")

    return errors, warnings


def validate_holdings(holdings: list[Holding], rep_pd_end: str = "") -> tuple[list[str], list[str]]:
    errors, warnings = [], []

    if not holdings:
        errors.append("No holdings provided.")
        return errors, warnings

    has_derivatives = any(h.deriv_cat for h in holdings)

    for i, h in enumerate(holdings):
        h_err, h_warn = validate_holding(h, i, rep_pd_end=rep_pd_end)
        errors.extend(h_err)
        warnings.extend(h_warn)

    try:
        pct_sum = sum(float(h.pct_val) for h in holdings)
        # Wider tolerance for derivative funds (leverage makes pctVal deviate)
        tolerance = 20.0 if has_derivatives else 5.0
        if abs(pct_sum - 100.0) > tolerance:
            warnings.append(f"pctVal sum is {pct_sum:.2f}% — expected ~100%.")
    except ValueError:
        warnings.append("Could not sum pctVal — some values are not numeric.")

    cusips = [h.cusip for h in holdings if h.cusip not in ("N/A", "000000000")]
    dupes = {c for c in cusips if cusips.count(c) > 1}
    if dupes:
        warnings.append(f"Duplicate CUSIPs: {', '.join(sorted(dupes))}.")

    return errors, warnings


def validate_all(
    config: FundConfig, filing: FilingData, holdings: list[Holding],
) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for fn, args in [
        (validate_config, (config,)),
        (validate_filing, (filing,)),
        (validate_holdings, (holdings, filing.rep_pd_end)),
    ]:
        e, w = fn(*args)
        errors.extend(e)
        warnings.extend(w)
    return errors, warnings
