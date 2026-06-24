"""Unit tests for extended validation — derivatives, debt, conditionals, pctVal tolerance."""

from nport.input_validation import validate_holding, validate_holdings
from nport.models import Holding


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


# ── Derivative validation ─────────────────────────────────


class TestDerivativeValidation:
    def test_valid_option(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="Goldman Sachs",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call",
            written_or_pur="Purchased",
            exercise_price="150.00",
            exp_dt="2026-06-30",
            delta="0.65",
            unrealized_appr="500.00",
        )
        errors, _ = validate_holding(h, 0)
        assert not errors

    def test_bad_deriv_cat(self):
        h = _holding(
            deriv_cat="INVALID",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("derivCat" in e for e in errors)

    def test_missing_counterparty(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call",
            written_or_pur="Purchased",
            exercise_price="150.00",
            exp_dt="2026-06-30",
            delta="0.65",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("counterpartyName" in e for e in errors)

    def test_bad_counterparty_lei(self):
        h = _holding(
            deriv_cat="FWD",
            counterparty_name="GS",
            counterparty_lei="BADLEI",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("counterpartyLei" in e for e in errors)

    def test_bad_put_call(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="INVALID",
            written_or_pur="Purchased",
            exercise_price="100",
            exp_dt="2026-01-01",
            delta="0.5",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("putOrCall" in e for e in errors)

    def test_bad_written_pur(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call",
            written_or_pur="INVALID",
            exercise_price="100",
            exp_dt="2026-01-01",
            delta="0.5",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("writtenOrPur" in e for e in errors)

    def test_written_option_positive_balance_warns(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Put",
            written_or_pur="Written",
            balance="100",
            exercise_price="100",
            exp_dt="2026-01-01",
            delta="-0.4",
            unrealized_appr="0",
        )
        _, warnings = validate_holding(h, 0)
        assert any("written option" in w for w in warnings)

    def test_swap_missing_legs(self):
        h = _holding(
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2027-01-01",
            notional_amt="1000000",
            rec_fixed_or_floating="",
            pmnt_fixed_or_floating="",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("recFixedOrFloating" in e for e in errors)
        assert any("pmntFixedOrFloating" in e for e in errors)

    def test_swap_bad_termination_date(self):
        h = _holding(
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="NOT-A-DATE",
            notional_amt="1000000",
            rec_fixed_or_floating="Fixed",
            pmnt_fixed_or_floating="Floating",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("terminationDt" in e for e in errors)

    def test_swap_bad_notional(self):
        h = _holding(
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2027-01-01",
            notional_amt="NOT_NUMERIC",
            rec_fixed_or_floating="Fixed",
            pmnt_fixed_or_floating="Floating",
            unrealized_appr="0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("notionalAmt" in e for e in errors)

    def test_no_deriv_validation_when_empty(self):
        """Equity holdings should not trigger derivative validation."""
        h = _holding()
        errors, _ = validate_holding(h, 0)
        assert not errors


# ── Debt validation ───────────────────────────────────────


class TestDebtValidation:
    def test_valid_debt(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Fixed",
            annualized_rt="5.25",
        )
        errors, _ = validate_holding(h, 0)
        assert not errors

    def test_bad_maturity_date(self):
        h = _holding(
            maturity_dt="NOT-A-DATE",
            coupon_kind="Fixed",
            annualized_rt="5.0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("maturityDt" in e for e in errors)

    def test_bad_coupon_kind(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="INVALID",
            annualized_rt="5.0",
        )
        errors, _ = validate_holding(h, 0)
        assert any("couponKind" in e for e in errors)

    def test_valid_coupon_kinds(self):
        for kind in ("Fixed", "Floating", "Variable", "None"):
            h = _holding(
                maturity_dt="2030-12-31",
                coupon_kind=kind,
                annualized_rt="0",
            )
            errors, _ = validate_holding(h, 0)
            assert not any("couponKind" in e for e in errors), f"Failed for {kind}"

    def test_bad_annualized_rt(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Fixed",
            annualized_rt="NOT_NUMERIC",
        )
        errors, _ = validate_holding(h, 0)
        assert any("annualizedRt" in e for e in errors)

    def test_bad_default_flag(self):
        h = _holding(
            maturity_dt="2030-12-31",
            coupon_kind="Fixed",
            annualized_rt="5.0",
            is_default="BAD",
        )
        errors, _ = validate_holding(h, 0)
        assert any("isDefault" in e for e in errors)

    def test_no_debt_validation_when_empty(self):
        h = _holding()
        errors, _ = validate_holding(h, 0)
        assert not errors


# ── Conditional element validation ────────────────────────


class TestConditionalValidation:
    def test_other_issuer_cat_without_desc_warns(self):
        h = _holding(issuer_cat="OTHER")
        _, warnings = validate_holding(h, 0)
        assert any("issuerConditionalDesc" in w for w in warnings)

    def test_other_issuer_cat_with_desc_no_warning(self):
        h = _holding(issuer_cat="OTHER", issuer_conditional_desc="Private fund")
        _, warnings = validate_holding(h, 0)
        assert not any("issuerConditionalDesc" in w for w in warnings)

    def test_other_asset_cat_without_desc_warns(self):
        h = _holding(asset_cat="OTHER")
        _, warnings = validate_holding(h, 0)
        assert any("assetConditionalDesc" in w for w in warnings)

    def test_other_asset_cat_with_desc_no_warning(self):
        h = _holding(asset_cat="OTHER", asset_conditional_desc="FLEX option")
        _, warnings = validate_holding(h, 0)
        assert not any("assetConditionalDesc" in w for w in warnings)


# ── pctVal tolerance ──────────────────────────────────────


class TestPctValTolerance:
    def test_equity_strict_tolerance(self):
        """Equity-only: 5% tolerance."""
        holdings = [_holding(pct_val="93.0")]
        _, warnings = validate_holdings(holdings)
        assert any("pctVal sum" in w for w in warnings)

    def test_equity_within_tolerance(self):
        holdings = [_holding(pct_val="96.0")]
        _, warnings = validate_holdings(holdings)
        assert not any("pctVal sum" in w for w in warnings)

    def test_derivative_wide_tolerance(self):
        """Derivative funds: 20% tolerance."""
        deriv = _holding(
            pct_val="150.0",
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2027-01-01",
            notional_amt="1000000",
            rec_fixed_or_floating="Fixed",
            pmnt_fixed_or_floating="Floating",
            unrealized_appr="0",
        )
        equity = _holding(pct_val="-40.0")
        _, warnings = validate_holdings([deriv, equity])
        # 150 + (-40) = 110, within ±20 of 100
        assert not any("pctVal sum" in w for w in warnings)

    def test_derivative_exceeds_wide_tolerance(self):
        deriv = _holding(
            pct_val="250.0",
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2027-01-01",
            notional_amt="1000000",
            rec_fixed_or_floating="Fixed",
            pmnt_fixed_or_floating="Floating",
            unrealized_appr="0",
        )
        _, warnings = validate_holdings([deriv])
        # 250 is > 120 threshold
        assert any("pctVal sum" in w for w in warnings)


# ── Swap leg validation ──────────────────────────────────


class TestSwapLegValidation:
    def _swap(self, **overrides):
        defaults = dict(
            deriv_cat="SWP",
            counterparty_name="GS",
            counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2027-01-01",
            notional_amt="1000000",
            unrealized_appr="0",
        )
        defaults.update(overrides)
        return _holding(**defaults)

    def test_valid_fixed_receive_floating_pay(self):
        h = self._swap(
            rec_fixed_or_floating="Fixed", rec_fixed_rt="0.05",
            pmnt_fixed_or_floating="Floating",
            pmnt_floating_rt_index="USD-SOFR", pmnt_floating_rt_spread="0.01",
        )
        errors, _ = validate_holding(h, 0)
        assert not errors

    def test_invalid_rec_fixed_or_floating(self):
        h = self._swap(
            rec_fixed_or_floating="INVALID",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.03",
        )
        errors, _ = validate_holding(h, 0)
        assert any("recFixedOrFloating" in e for e in errors)

    def test_fixed_receive_requires_rate(self):
        h = self._swap(
            rec_fixed_or_floating="Fixed", rec_fixed_rt="NOT_NUMERIC",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.03",
        )
        errors, _ = validate_holding(h, 0)
        assert any("recFixedRt" in e for e in errors)

    def test_floating_receive_requires_index(self):
        h = self._swap(
            rec_fixed_or_floating="Floating",
            rec_floating_rt_index="",
            rec_floating_rt_spread="0.5",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.03",
        )
        errors, _ = validate_holding(h, 0)
        assert any("recFloatingRtIndex" in e for e in errors)

    def test_floating_receive_requires_spread(self):
        h = self._swap(
            rec_fixed_or_floating="Floating",
            rec_floating_rt_index="USD-SOFR",
            rec_floating_rt_spread="NOT_NUMERIC",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.03",
        )
        errors, _ = validate_holding(h, 0)
        assert any("recFloatingRtSpread" in e for e in errors)

    def test_floating_pay_requires_index_and_spread(self):
        h = self._swap(
            rec_fixed_or_floating="Fixed", rec_fixed_rt="0.05",
            pmnt_fixed_or_floating="Floating",
            pmnt_floating_rt_index="",
            pmnt_floating_rt_spread="BAD",
        )
        errors, _ = validate_holding(h, 0)
        assert any("pmntFloatingRtIndex" in e for e in errors)
        assert any("pmntFloatingRtSpread" in e for e in errors)


# ── Cross-field derivative checks ────────────────────────


class TestCrossFieldDerivChecks:
    def test_exercise_price_warning(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call", written_or_pur="Purchased",
            exercise_price="0", exp_dt="2026-06-30",
            delta="0.5", unrealized_appr="0",
        )
        _, warnings = validate_holding(h, 0)
        assert any("exercisePrice" in w and "positive" in w for w in warnings)

    def test_delta_out_of_range_warning(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call", written_or_pur="Purchased",
            exercise_price="100", exp_dt="2026-06-30",
            delta="1.5", unrealized_appr="0",
        )
        _, warnings = validate_holding(h, 0)
        assert any("delta" in w and "[-1, 1]" in w for w in warnings)

    def test_delta_na_no_warning(self):
        h = _holding(
            deriv_cat="OPT",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            put_or_call="Call", written_or_pur="Purchased",
            exercise_price="100", exp_dt="2026-06-30",
            delta="N/A", unrealized_appr="0",
        )
        _, warnings = validate_holding(h, 0)
        assert not any("delta" in w and "[-1, 1]" in w for w in warnings)

    def test_swap_expired_warning(self):
        h = _holding(
            deriv_cat="SWP",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            termination_dt="2025-12-01",
            notional_amt="1000000",
            rec_fixed_or_floating="Fixed", rec_fixed_rt="0.05",
            pmnt_fixed_or_floating="Fixed", pmnt_fixed_rt="0.03",
            unrealized_appr="0",
        )
        _, warnings = validate_holding(h, 0, rep_pd_end="2025-12-31")
        assert any("expired" in w for w in warnings)


# ── Counterparty LEI warning ─────────────────────────────


class TestCounterpartyLeiWarning:
    def test_na_lei_warns(self):
        h = _holding(
            deriv_cat="FWD",
            counterparty_name="Private Dealer",
            counterparty_lei="N/A",
            unrealized_appr="0",
            payoff_prof_deriv="Long",
        )
        _, warnings = validate_holding(h, 0)
        assert any("real counterparties should have LEIs" in w for w in warnings)


# ── Forward/Future validation ────────────────────────────


class TestForwardFutureValidation:
    def test_valid_forward(self):
        h = _holding(
            deriv_cat="FWD",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            unrealized_appr="0",
            payoff_prof_deriv="Long",
            exp_dt="2026-06-30",
            notional_amt="500000",
        )
        errors, _ = validate_holding(h, 0)
        assert not errors

    def test_missing_payoff_profile(self):
        h = _holding(
            deriv_cat="FWD",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            unrealized_appr="0",
            payoff_prof_deriv="INVALID",
        )
        errors, _ = validate_holding(h, 0)
        assert any("payoffProfDeriv" in e for e in errors)

    def test_bad_exp_dt(self):
        h = _holding(
            deriv_cat="FUT",
            counterparty_name="CME", counterparty_lei="W22LROWP2IHZNBB6K528",
            unrealized_appr="0",
            payoff_prof_deriv="Long",
            exp_dt="NOT-A-DATE",
        )
        errors, _ = validate_holding(h, 0)
        assert any("expDt" in e for e in errors)

    def test_bad_notional(self):
        h = _holding(
            deriv_cat="FWD",
            counterparty_name="GS", counterparty_lei="W22LROWP2IHZNBB6K528",
            unrealized_appr="0",
            payoff_prof_deriv="Long",
            notional_amt="BAD",
        )
        errors, _ = validate_holding(h, 0)
        assert any("notionalAmt" in e for e in errors)


# ── Reference instrument validation ──────────────────────


class TestRefInstrumentValidation:
    def test_valid_index_basket(self):
        h = _holding(
            ref_inst_type="indexBasket",
            ref_index_name="S&P 500",
            ref_index_identifier="SPX",
        )
        errors, _ = validate_holding(h, 0)
        assert not any("refInstType" in e or "refIndex" in e for e in errors)

    def test_invalid_ref_type(self):
        h = _holding(ref_inst_type="INVALID")
        errors, _ = validate_holding(h, 0)
        assert any("refInstType" in e for e in errors)

    def test_index_basket_missing_fields(self):
        h = _holding(
            ref_inst_type="indexBasket",
            ref_index_name="",
            ref_index_identifier="",
        )
        errors, _ = validate_holding(h, 0)
        assert any("refIndexName" in e for e in errors)
        assert any("refIndexIdentifier" in e for e in errors)

    def test_other_ref_inst_missing_fields(self):
        h = _holding(
            ref_inst_type="otherRefInst",
            ref_issuer_name="",
            ref_issue_title="",
        )
        errors, _ = validate_holding(h, 0)
        assert any("refIssuerName" in e for e in errors)
        assert any("refIssueTitle" in e for e in errors)
