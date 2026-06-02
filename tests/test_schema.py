"""Tests for the data schema module."""

from dataclasses import fields

from nport.config import _HOLDINGS_KEY_MAP
from nport.models import Holding
from nport.schema import FIELD_BY_NAME, FIELD_SPECS, FieldSpec, get_required_fields


class TestFieldSpecCoverage:
    def test_covers_every_holding_field(self):
        """Every Holding dataclass field should have a FieldSpec."""
        holding_fields = {f.name for f in fields(Holding)}
        schema_fields = {s.name for s in FIELD_SPECS}
        missing = holding_fields - schema_fields
        assert not missing, f"Holding fields missing from schema: {missing}"

    def test_covers_every_key_map_entry(self):
        """Every _HOLDINGS_KEY_MAP value should have a FieldSpec."""
        key_map_fields = set(_HOLDINGS_KEY_MAP.values())
        schema_fields = {s.name for s in FIELD_SPECS}
        missing = key_map_fields - schema_fields
        assert not missing, f"Key map fields missing from schema: {missing}"

    def test_csv_headers_match_key_map(self):
        """FieldSpec csv_header should match _HOLDINGS_KEY_MAP."""
        field_to_csv = {v: k for k, v in _HOLDINGS_KEY_MAP.items()}
        for spec in FIELD_SPECS:
            expected = field_to_csv.get(spec.name, spec.name)
            assert spec.csv_header == expected, f"{spec.name}: expected '{expected}', got '{spec.csv_header}'"

    def test_field_by_name_lookup(self):
        assert "name" in FIELD_BY_NAME
        assert FIELD_BY_NAME["name"].group == "base"
        assert FIELD_BY_NAME["deriv_cat"].group == "deriv_common"

    def test_field_spec_is_frozen(self):
        spec = FIELD_SPECS[0]
        assert isinstance(spec, FieldSpec)
        import pytest
        with pytest.raises(AttributeError):
            spec.name = "changed"


class TestGetRequiredFields:
    def test_equity(self):
        """Equity: only base always-required fields."""
        required = get_required_fields(deriv_cat="", has_debt=False)
        assert "name" in required
        assert "cusip" in required
        assert "val_usd" in required
        # No derivative or debt fields
        assert "deriv_cat" not in required
        assert "maturity_dt" not in required
        assert "put_or_call" not in required

    def test_debt(self):
        """Debt: base + debt fields."""
        required = get_required_fields(deriv_cat="", has_debt=True)
        assert "name" in required
        assert "maturity_dt" in required
        assert "coupon_kind" in required
        assert "annualized_rt" in required
        # No derivative fields
        assert "deriv_cat" not in required

    def test_option(self):
        """OPT: base + deriv_common + option fields."""
        required = get_required_fields(deriv_cat="OPT", has_debt=False)
        assert "name" in required
        assert "deriv_cat" in required
        assert "counterparty_name" in required
        assert "put_or_call" in required
        assert "exercise_price" in required
        assert "exp_dt" in required
        assert "delta" in required
        # No swap fields
        assert "termination_dt" not in required

    def test_swap(self):
        """SWP: base + deriv_common + swap fields."""
        required = get_required_fields(deriv_cat="SWP", has_debt=False)
        assert "name" in required
        assert "deriv_cat" in required
        assert "counterparty_name" in required
        assert "termination_dt" in required
        assert "notional_amt" in required
        assert "rec_fixed_or_floating" in required
        assert "pmnt_fixed_or_floating" in required
        # No option fields
        assert "put_or_call" not in required

    def test_forward(self):
        """FWD: base + deriv_common + forward fields."""
        required = get_required_fields(deriv_cat="FWD", has_debt=False)
        assert "name" in required
        assert "deriv_cat" in required
        assert "payoff_prof_deriv" in required
        # No swap or option fields
        assert "termination_dt" not in required
        assert "put_or_call" not in required

    def test_future(self):
        """FUT: same as FWD."""
        required = get_required_fields(deriv_cat="FUT", has_debt=False)
        assert "payoff_prof_deriv" in required
        assert "deriv_cat" in required


class TestGroupCounts:
    def test_total_field_count(self):
        """Schema should cover all Holding fields."""
        assert len(FIELD_SPECS) == len(fields(Holding))

    def test_group_distribution(self):
        groups = {}
        for s in FIELD_SPECS:
            groups[s.group] = groups.get(s.group, 0) + 1
        assert groups["base"] == 20
        assert groups["conditional"] == 5
        assert groups["debt"] == 6
        assert groups["deriv_common"] == 4
        assert groups["option"] == 7
        assert groups["ref_instrument"] == 8
        assert groups["forward"] == 1
        assert groups["other_deriv"] == 1
