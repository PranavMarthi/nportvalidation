"""Programmatic data schema for N-PORT holdings CSV columns.

Documents every CSV column, its type, and when it's required.
Used by the ``nport schema`` CLI command and available for
programmatic introspection.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from nport.config import _HOLDINGS_KEY_MAP
from nport.models import Holding


@dataclass(frozen=True)
class FieldSpec:
    """Specification for a single holding field."""

    name: str  # snake_case dataclass field name
    csv_header: str  # camelCase CSV column name
    group: str  # logical group
    required: str  # "always", "never", or "conditional"
    condition: str  # when required=="conditional", describes the condition
    value_type: str  # "str", "decimal", "date", "enum", "Y/N"
    description: str


# ── Build the master list ─────────────────────────────────

_FIELD_TO_CSV = {v: k for k, v in _HOLDINGS_KEY_MAP.items()}

_SPEC_DEFS: list[tuple[str, str, str, str, str, str]] = [
    # (group, required, condition, value_type, description)  — keyed by field name
    # ── base (20) ──
    ("name", "base", "always", "", "str", "Issuer name"),
    ("lei", "base", "always", "", "str", "LEI (20-char or N/A)"),
    ("title", "base", "always", "", "str", "Security title"),
    ("cusip", "base", "always", "", "str", "CUSIP (9-char, N/A, or 000000000)"),
    ("isin", "base", "never", "", "str", "ISIN (12-char, optional)"),
    ("ticker", "base", "never", "", "str", "Ticker symbol (optional)"),
    ("balance", "base", "always", "", "decimal", "Number of shares/units/par"),
    ("units", "base", "always", "", "enum", "Units: NS, PA, NC, OU"),
    ("cur_cd", "base", "always", "", "str", "ISO currency code"),
    ("val_usd", "base", "always", "", "decimal", "Value in USD"),
    ("pct_val", "base", "always", "", "decimal", "Percent of net assets"),
    ("payoff_profile", "base", "always", "", "enum", "Long, Short, or N/A"),
    ("asset_cat", "base", "always", "", "enum", "Asset category (20 values)"),
    ("issuer_cat", "base", "always", "", "enum", "Issuer category (9 values)"),
    ("inv_country", "base", "always", "", "str", "ISO country code (2-char)"),
    ("is_restricted_sec", "base", "always", "", "Y/N", "Is restricted security"),
    ("fair_val_level", "base", "always", "", "enum", "Fair value level: 1, 2, 3, N/A"),
    ("is_cash_collateral", "base", "always", "", "Y/N", "Is cash collateral"),
    ("is_non_cash_collateral", "base", "always", "", "Y/N", "Is non-cash collateral"),
    ("is_loan_by_fund", "base", "always", "", "Y/N", "Is loan by fund"),
    # ── conditional (5) ──
    ("issuer_conditional_desc", "conditional", "conditional", "issuerCat==OTHER", "str", "Issuer conditional description"),
    ("asset_conditional_desc", "conditional", "conditional", "assetCat==OTHER", "str", "Asset conditional description"),
    ("other_desc", "conditional", "never", "", "str", "Other identifier description"),
    ("other_value", "conditional", "never", "", "str", "Other identifier value"),
    ("exchange_rt", "conditional", "conditional", "non-USD currency", "decimal", "Exchange rate to USD"),
    # ── debt (6) ──
    ("maturity_dt", "debt", "conditional", "debt security", "date", "Maturity date"),
    ("coupon_kind", "debt", "conditional", "maturityDt set", "enum", "Fixed, Floating, Variable, None"),
    ("annualized_rt", "debt", "conditional", "maturityDt set", "decimal", "Annualized rate"),
    ("is_default", "debt", "conditional", "maturityDt set", "Y/N", "Is in default"),
    ("are_intrst_pmnts_in_arrs", "debt", "conditional", "maturityDt set", "Y/N", "Are interest payments in arrears"),
    ("is_paid_kind", "debt", "conditional", "maturityDt set", "Y/N", "Is paid in kind"),
    # ── deriv_common (4) ──
    ("deriv_cat", "deriv_common", "conditional", "derivative holding", "enum", "FWD, FUT, SWP, OPT, SWO, WAR, OTH"),
    ("counterparty_name", "deriv_common", "conditional", "derivCat set", "str", "Counterparty name"),
    ("counterparty_lei", "deriv_common", "conditional", "derivCat set", "str", "Counterparty LEI"),
    ("unrealized_appr", "deriv_common", "conditional", "derivCat set", "decimal", "Unrealized appreciation"),
    # ── option (7) ──
    ("put_or_call", "option", "conditional", "derivCat in OPT/SWO/WAR", "enum", "Put or Call"),
    ("written_or_pur", "option", "conditional", "derivCat in OPT/SWO/WAR", "enum", "Written or Purchased"),
    ("share_no", "option", "never", "", "decimal", "Number of shares"),
    ("exercise_price", "option", "conditional", "derivCat in OPT/SWO/WAR", "decimal", "Exercise price"),
    ("exercise_price_cur_cd", "option", "never", "", "str", "Exercise price currency"),
    ("exp_dt", "option", "conditional", "derivCat in OPT/SWO/WAR", "date", "Expiration date"),
    ("delta", "option", "conditional", "derivCat in OPT/SWO/WAR", "decimal", "Delta (or N/A)"),
    # ── ref_instrument (8) ──
    ("ref_inst_type", "ref_instrument", "never", "", "enum", "indexBasket or otherRefInst"),
    ("ref_index_name", "ref_instrument", "conditional", "refInstType==indexBasket", "str", "Reference index name"),
    ("ref_index_identifier", "ref_instrument", "conditional", "refInstType==indexBasket", "str", "Reference index identifier"),
    ("ref_issuer_name", "ref_instrument", "conditional", "refInstType==otherRefInst", "str", "Reference issuer name"),
    ("ref_issue_title", "ref_instrument", "conditional", "refInstType==otherRefInst", "str", "Reference issue title"),
    ("ref_cusip", "ref_instrument", "never", "", "str", "Reference CUSIP"),
    ("ref_isin", "ref_instrument", "never", "", "str", "Reference ISIN"),
    ("ref_ticker", "ref_instrument", "never", "", "str", "Reference ticker"),
    # ── swap (21) ──
    ("swap_flag", "swap", "conditional", "derivCat==SWP", "str", "Swap flag (Y/N)"),
    ("termination_dt", "swap", "conditional", "derivCat==SWP", "date", "Termination date"),
    ("upfront_pmnt", "swap", "never", "", "decimal", "Upfront payment"),
    ("pmnt_cur_cd", "swap", "never", "", "str", "Payment currency code"),
    ("upfront_rcpt", "swap", "never", "", "decimal", "Upfront receipt"),
    ("rcpt_cur_cd", "swap", "never", "", "str", "Receipt currency code"),
    ("notional_amt", "swap", "conditional", "derivCat==SWP", "decimal", "Notional amount"),
    ("swap_cur_cd", "swap", "never", "", "str", "Swap currency code"),
    ("rec_fixed_or_floating", "swap", "conditional", "derivCat==SWP", "enum", "Fixed, Floating, or Other"),
    ("rec_fixed_rt", "swap", "conditional", "recFixedOrFloating==Fixed", "decimal", "Receive fixed rate"),
    ("rec_floating_rt_index", "swap", "conditional", "recFixedOrFloating==Floating", "str", "Receive floating rate index"),
    ("rec_floating_rt_spread", "swap", "conditional", "recFixedOrFloating==Floating", "decimal", "Receive floating rate spread"),
    ("rec_pmnt_amt", "swap", "never", "", "decimal", "Receive payment amount"),
    ("rec_cur_cd", "swap", "never", "", "str", "Receive currency code"),
    ("rec_rate_tenor", "swap", "never", "", "str", "Receive rate tenor"),
    ("rec_rate_unit", "swap", "never", "", "str", "Receive rate unit"),
    ("rec_reset_dt", "swap", "never", "", "str", "Receive reset date"),
    ("rec_reset_unit", "swap", "never", "", "str", "Receive reset unit"),
    ("rec_desc", "swap", "never", "", "str", "Receive leg description"),
    ("pmnt_fixed_or_floating", "swap", "conditional", "derivCat==SWP", "enum", "Fixed, Floating, or Other"),
    ("pmnt_fixed_rt", "swap", "conditional", "pmntFixedOrFloating==Fixed", "decimal", "Pay fixed rate"),
    ("pmnt_floating_rt_index", "swap", "conditional", "pmntFixedOrFloating==Floating", "str", "Pay floating rate index"),
    ("pmnt_floating_rt_spread", "swap", "conditional", "pmntFixedOrFloating==Floating", "decimal", "Pay floating rate spread"),
    ("pmnt_pmnt_amt", "swap", "never", "", "decimal", "Pay payment amount"),
    ("pmnt_cur_cd_leg", "swap", "never", "", "str", "Pay leg currency code"),
    ("pmnt_rate_tenor", "swap", "never", "", "str", "Pay rate tenor"),
    ("pmnt_rate_unit", "swap", "never", "", "str", "Pay rate unit"),
    ("pmnt_reset_dt", "swap", "never", "", "str", "Pay reset date"),
    ("pmnt_reset_unit", "swap", "never", "", "str", "Pay reset unit"),
    # ── forward (2) ──
    ("payoff_prof_deriv", "forward", "conditional", "derivCat in FWD/FUT", "enum", "Long, Short, or N/A"),
    # ── other_deriv (1) ──
    ("other_deriv_desc", "other_deriv", "conditional", "derivCat==OTH", "str", "Other derivative description"),
]


def _build_field_specs() -> list[FieldSpec]:
    specs = []
    for entry in _SPEC_DEFS:
        name, group, required, condition, value_type, description = entry
        csv_header = _FIELD_TO_CSV.get(name, name)
        specs.append(FieldSpec(
            name=name,
            csv_header=csv_header,
            group=group,
            required=required,
            condition=condition,
            value_type=value_type,
            description=description,
        ))
    return specs


FIELD_SPECS: list[FieldSpec] = _build_field_specs()

FIELD_BY_NAME: dict[str, FieldSpec] = {s.name: s for s in FIELD_SPECS}


def get_required_fields(deriv_cat: str = "", has_debt: bool = False) -> list[str]:
    """Return list of required field names for a given holding type.

    Args:
        deriv_cat: Derivative category (e.g. "OPT", "SWP", "FWD"), or "" for non-derivative.
        has_debt: Whether the holding is a debt security.

    Returns:
        List of snake_case field names that are required.
    """
    required = []

    for spec in FIELD_SPECS:
        if spec.required == "always":
            required.append(spec.name)
        elif spec.required == "conditional":
            # Debt fields
            if spec.group == "debt" and has_debt:
                if spec.name in ("maturity_dt", "coupon_kind", "annualized_rt"):
                    required.append(spec.name)

            # Derivative common
            if spec.group == "deriv_common" and deriv_cat:
                required.append(spec.name)

            # Option fields
            if spec.group == "option" and deriv_cat in ("OPT", "SWO", "WAR"):
                if spec.name != "share_no":  # share_no is never required
                    required.append(spec.name)

            # Swap fields
            if spec.group == "swap" and deriv_cat == "SWP":
                if spec.condition == "derivCat==SWP":
                    required.append(spec.name)

            # Forward/future fields
            if spec.group == "forward" and deriv_cat in ("FWD", "FUT"):
                required.append(spec.name)

            # Other derivative
            if spec.group == "other_deriv" and deriv_cat == "OTH":
                required.append(spec.name)

    return required


def print_schema() -> None:
    """Print a human-readable table of the data schema."""
    # Group fields
    groups: dict[str, list[FieldSpec]] = {}
    for spec in FIELD_SPECS:
        groups.setdefault(spec.group, []).append(spec)

    group_titles = {
        "base": "Base Fields (always required)",
        "conditional": "Conditional Fields",
        "debt": "Debt Security Fields (C.9)",
        "deriv_common": "Derivative Common Fields",
        "option": "Option Fields (C.11.c)",
        "ref_instrument": "Reference Instrument Fields",
        "swap": "Swap Fields (C.11.f)",
        "forward": "Forward/Future Fields",
        "other_deriv": "Other Derivative Fields",
    }

    header = f"{'CSV Column':<30} {'Field Name':<30} {'Type':<8} {'Required':<12} {'Description'}"
    sep = "-" * len(header)

    print("N-PORT Holdings Data Schema")
    print("=" * 27)
    print()

    for group_key in group_titles:
        specs = groups.get(group_key, [])
        if not specs:
            continue
        print(f"  {group_titles[group_key]} ({len(specs)} fields)")
        print(f"  {sep}")
        print(f"  {header}")
        print(f"  {sep}")
        for s in specs:
            req = s.required
            if s.condition:
                req = f"{s.required}*"
            print(f"  {s.csv_header:<30} {s.name:<30} {s.value_type:<8} {req:<12} {s.description}")
        print()

    total = len(FIELD_SPECS)
    always = sum(1 for s in FIELD_SPECS if s.required == "always")
    cond = sum(1 for s in FIELD_SPECS if s.required == "conditional")
    never = sum(1 for s in FIELD_SPECS if s.required == "never")
    print(f"Total: {total} fields ({always} always, {cond} conditional, {never} optional)")
