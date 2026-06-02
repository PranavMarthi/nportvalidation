"""Parsers for key=value txt files and CSV holdings files."""

import csv
import warnings
from pathlib import Path

from nport.models import FilingData, FundConfig, Holding

# Key name in txt file -> dataclass field name
_CONFIG_KEY_MAP = {
    "cik": "cik", "ccc": "ccc",
    "regName": "reg_name", "regFileNumber": "reg_file_number",
    "regCik": "reg_cik", "regLei": "reg_lei",
    "regStreet1": "reg_street1", "regStreet2": "reg_street2",
    "regCity": "reg_city", "regState": "reg_state",
    "regCountry": "reg_country", "regZipOrPostalCode": "reg_zip",
    "regPhone": "reg_phone",
    "seriesName": "series_name", "seriesId": "series_id",
    "seriesLei": "series_lei", "classId": "class_id",
    "signerOrg": "signer_org", "signerName": "signer_name",
    "signerTitle": "signer_title",
}

_FILING_KEY_MAP = {
    "submissionType": "submission_type",
    "liveTestFlag": "live_test_flag",
    "repPdEnd": "rep_pd_end", "repPdDate": "rep_pd_date",
    "isFinalFiling": "is_final_filing", "dateSigned": "date_signed",
    "totAssets": "tot_assets", "totLiabs": "tot_liabs",
    "netAssets": "net_assets",
    "assetsAttrMiscSec": "assets_attr_misc_sec",
    "assetsInvested": "assets_invested",
    "amtPayOneYrBanksBorr": "amt_pay_one_yr_banks_borr",
    "amtPayOneYrCtrldComp": "amt_pay_one_yr_ctrld_comp",
    "amtPayOneYrOthAffil": "amt_pay_one_yr_oth_affil",
    "amtPayOneYrOther": "amt_pay_one_yr_other",
    "amtPayAftOneYrBanksBorr": "amt_pay_aft_one_yr_banks_borr",
    "amtPayAftOneYrCtrldComp": "amt_pay_aft_one_yr_ctrld_comp",
    "amtPayAftOneYrOthAffil": "amt_pay_aft_one_yr_oth_affil",
    "amtPayAftOneYrOther": "amt_pay_aft_one_yr_other",
    "delayDeliv": "delay_deliv", "standByCommit": "stand_by_commit",
    "liquidPref": "liquid_pref",
    "isNonCashCollateral": "is_non_cash_collateral",
    "rtn1": "rtn1", "rtn2": "rtn2", "rtn3": "rtn3",
    "netRealizedGainMon1": "net_realized_gain_mon1",
    "netUnrealizedApprMon1": "net_unrealized_appr_mon1",
    "netRealizedGainMon2": "net_realized_gain_mon2",
    "netUnrealizedApprMon2": "net_unrealized_appr_mon2",
    "netRealizedGainMon3": "net_realized_gain_mon3",
    "netUnrealizedApprMon3": "net_unrealized_appr_mon3",
    "mon1Sales": "mon1_sales", "mon1Redemption": "mon1_redemption",
    "mon1Reinvestment": "mon1_reinvestment",
    "mon2Sales": "mon2_sales", "mon2Redemption": "mon2_redemption",
    "mon2Reinvestment": "mon2_reinvestment",
    "mon3Sales": "mon3_sales", "mon3Redemption": "mon3_redemption",
    "mon3Reinvestment": "mon3_reinvestment",
    "nameDesignatedIndex": "name_designated_index",
    "indexIdentifier": "index_identifier",
    # B.3 Risk metrics (optional)
    "curMetricsJson": "cur_metrics_json",
    "creditSprdRiskIgJson": "credit_sprd_risk_ig_json",
    "creditSprdRiskNonigJson": "credit_sprd_risk_nonig_json",
}

_HOLDINGS_KEY_MAP = {
    "name": "name", "lei": "lei", "title": "title",
    "cusip": "cusip", "isin": "isin", "ticker": "ticker",
    "balance": "balance", "units": "units", "curCd": "cur_cd",
    "valUSD": "val_usd", "pctVal": "pct_val",
    "payoffProfile": "payoff_profile",
    "assetCat": "asset_cat", "issuerCat": "issuer_cat",
    "invCountry": "inv_country",
    "isRestrictedSec": "is_restricted_sec",
    "fairValLevel": "fair_val_level",
    "isCashCollateral": "is_cash_collateral",
    "isNonCashCollateral": "is_non_cash_collateral",
    "isLoanByFund": "is_loan_by_fund",
    # Conditional elements
    "issuerConditionalDesc": "issuer_conditional_desc",
    "assetConditionalDesc": "asset_conditional_desc",
    "otherDesc": "other_desc",
    "otherValue": "other_value",
    "exchangeRt": "exchange_rt",
    # Debt fields (C.9)
    "maturityDt": "maturity_dt",
    "couponKind": "coupon_kind",
    "annualizedRt": "annualized_rt",
    "isDefault": "is_default",
    "areIntrstPmntsInArrs": "are_intrst_pmnts_in_arrs",
    "isPaidKind": "is_paid_kind",
    # Derivative common
    "derivCat": "deriv_cat",
    "counterpartyName": "counterparty_name",
    "counterpartyLei": "counterparty_lei",
    "unrealizedAppr": "unrealized_appr",
    # Options (C.11.c)
    "putOrCall": "put_or_call",
    "writtenOrPur": "written_or_pur",
    "shareNo": "share_no",
    "exercisePrice": "exercise_price",
    "exercisePriceCurCd": "exercise_price_cur_cd",
    "expDt": "exp_dt",
    "delta": "delta",
    # Reference instrument
    "refInstType": "ref_inst_type",
    "refIndexName": "ref_index_name",
    "refIndexIdentifier": "ref_index_identifier",
    "refIssuerName": "ref_issuer_name",
    "refIssueTitle": "ref_issue_title",
    "refCusip": "ref_cusip",
    "refIsin": "ref_isin",
    "refTicker": "ref_ticker",
    # Swaps (C.11.f)
    "swapFlag": "swap_flag",
    "terminationDt": "termination_dt",
    "upfrontPmnt": "upfront_pmnt",
    "pmntCurCd": "pmnt_cur_cd",
    "upfrontRcpt": "upfront_rcpt",
    "rcptCurCd": "rcpt_cur_cd",
    "notionalAmt": "notional_amt",
    "swapCurCd": "swap_cur_cd",
    # Receive leg
    "recFixedOrFloating": "rec_fixed_or_floating",
    "recFixedRt": "rec_fixed_rt",
    "recFloatingRtIndex": "rec_floating_rt_index",
    "recFloatingRtSpread": "rec_floating_rt_spread",
    "recPmntAmt": "rec_pmnt_amt",
    "recCurCd": "rec_cur_cd",
    "recRateTenor": "rec_rate_tenor",
    "recRateUnit": "rec_rate_unit",
    "recResetDt": "rec_reset_dt",
    "recResetUnit": "rec_reset_unit",
    "recDesc": "rec_desc",
    # Pay leg
    "pmntFixedOrFloating": "pmnt_fixed_or_floating",
    "pmntFixedRt": "pmnt_fixed_rt",
    "pmntFloatingRtIndex": "pmnt_floating_rt_index",
    "pmntFloatingRtSpread": "pmnt_floating_rt_spread",
    "pmntPmntAmt": "pmnt_pmnt_amt",
    "pmntCurCdLeg": "pmnt_cur_cd_leg",
    "pmntRateTenor": "pmnt_rate_tenor",
    "pmntRateUnit": "pmnt_rate_unit",
    "pmntResetDt": "pmnt_reset_dt",
    "pmntResetUnit": "pmnt_reset_unit",
    # Futures/forwards
    "payoffProfDeriv": "payoff_prof_deriv",
    # Other derivatives
    "otherDerivDesc": "other_deriv_desc",
}

_OPTIONAL_HOLDINGS_KEYS = {
    "issuer_conditional_desc", "asset_conditional_desc",
    "other_desc", "other_value", "exchange_rt",
    "maturity_dt", "coupon_kind", "annualized_rt",
    "is_default", "are_intrst_pmnts_in_arrs", "is_paid_kind",
    "deriv_cat", "counterparty_name", "counterparty_lei", "unrealized_appr",
    "put_or_call", "written_or_pur", "share_no",
    "exercise_price", "exercise_price_cur_cd", "exp_dt", "delta",
    "ref_inst_type", "ref_index_name", "ref_index_identifier",
    "ref_issuer_name", "ref_issue_title", "ref_cusip", "ref_isin", "ref_ticker",
    "swap_flag", "termination_dt", "upfront_pmnt", "pmnt_cur_cd",
    "upfront_rcpt", "rcpt_cur_cd", "notional_amt", "swap_cur_cd",
    "rec_fixed_or_floating", "rec_fixed_rt", "rec_floating_rt_index",
    "rec_floating_rt_spread", "rec_pmnt_amt", "rec_cur_cd",
    "rec_rate_tenor", "rec_rate_unit", "rec_reset_dt", "rec_reset_unit", "rec_desc",
    "pmnt_fixed_or_floating", "pmnt_fixed_rt", "pmnt_floating_rt_index",
    "pmnt_floating_rt_spread", "pmnt_pmnt_amt", "pmnt_cur_cd_leg",
    "pmnt_rate_tenor", "pmnt_rate_unit", "pmnt_reset_dt", "pmnt_reset_unit",
    "payoff_prof_deriv", "other_deriv_desc",
}

_OPTIONAL_FILING_KEYS = {
    "cur_metrics_json", "credit_sprd_risk_ig_json", "credit_sprd_risk_nonig_json",
}

_OPTIONAL_CONFIG_KEYS = {"reg_street2"}


def _parse_kv_file(path: Path) -> dict[str, str]:
    """Parse a key=value text file, skipping comments and blank lines."""
    data = {}
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"{path}:{lineno}: expected key=value, got: {line!r}")
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
    return data


def _map_keys(raw: dict, key_map: dict, path: Path, optional: set | None = None) -> dict:
    """Map txt/csv keys to dataclass field names, raising on missing required keys."""
    optional = optional or set()
    kwargs = {}
    for txt_key, field_name in key_map.items():
        if txt_key not in raw:
            if field_name in optional:
                kwargs[field_name] = ""
                continue
            raise ValueError(f"{path}: missing required key '{txt_key}'.")
        kwargs[field_name] = raw[txt_key]
    return kwargs


def parse_config(path: str | Path) -> FundConfig:
    path = Path(path)
    return FundConfig(**_map_keys(_parse_kv_file(path), _CONFIG_KEY_MAP, path, _OPTIONAL_CONFIG_KEYS))


def parse_filing(path: str | Path) -> FilingData:
    path = Path(path)
    return FilingData(**_map_keys(_parse_kv_file(path), _FILING_KEY_MAP, path, _OPTIONAL_FILING_KEYS))


def _parse_split_holdings(base_path: Path) -> list[Holding]:
    """Parse holdings from split CSV files (base + optional satellites)."""
    parent = base_path.parent

    # Read base holdings.csv, indexed by holdingId
    base_rows: dict[str, dict[str, str]] = {}
    row_order: list[str] = []
    with open(base_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rownum, row in enumerate(reader, 2):
            hid = row.pop("holdingId", "").strip()
            if not hid:
                raise ValueError(f"{base_path}:{rownum}: missing holdingId value.")
            if hid in base_rows:
                raise ValueError(
                    f"{base_path}:{rownum}: duplicate holdingId '{hid}'."
                )
            base_rows[hid] = dict(row)
            row_order.append(hid)

    # Merge satellite files
    for sat_name in ("debt_securities.csv", "derivatives.csv"):
        sat_path = parent / sat_name
        if not sat_path.is_file():
            continue
        with open(sat_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for rownum, row in enumerate(reader, 2):
                hid = row.pop("holdingId", "").strip()
                if not hid:
                    raise ValueError(
                        f"{sat_path}:{rownum}: missing holdingId value."
                    )
                if hid not in base_rows:
                    warnings.warn(
                        f"{sat_path}:{rownum}: holdingId '{hid}' not in "
                        f"{base_path.name}.",
                        stacklevel=2,
                    )
                    continue
                base_rows[hid].update(row)

    # Construct Holding objects
    holdings = []
    for hid in row_order:
        row = base_rows[hid]
        try:
            kwargs = _map_keys(
                row, _HOLDINGS_KEY_MAP, base_path, _OPTIONAL_HOLDINGS_KEYS
            )
        except ValueError:
            present = set(row.keys())
            expected = {
                k
                for k, v in _HOLDINGS_KEY_MAP.items()
                if v not in _OPTIONAL_HOLDINGS_KEYS
            }
            missing = expected - present
            raise ValueError(
                f"{base_path}: holdingId '{hid}': missing required column(s): "
                f"{', '.join(sorted(missing))}."
            )
        holdings.append(Holding(**kwargs))

    return holdings


def parse_holdings(path: str | Path) -> list[Holding]:
    path = Path(path)
    # Auto-detect split format by checking for holdingId column
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
    if "holdingId" in headers:
        return _parse_split_holdings(path)
    # Existing flat-CSV code path
    holdings = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rownum, row in enumerate(reader, 2):
            try:
                kwargs = _map_keys(row, _HOLDINGS_KEY_MAP, path, _OPTIONAL_HOLDINGS_KEYS)
            except ValueError:
                present = set(row.keys()) if row else set()
                expected = {k for k, v in _HOLDINGS_KEY_MAP.items() if v not in _OPTIONAL_HOLDINGS_KEYS}
                missing = expected - present
                raise ValueError(f"{path}:{rownum}: missing required column(s): {', '.join(sorted(missing))}.")
            holdings.append(Holding(**kwargs))
    return holdings
