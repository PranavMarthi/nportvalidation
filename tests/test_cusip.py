"""Tests for spreadsheet-corrupted CUSIP normalization and recovery."""

from nport.cusip import (
    cusip_check_digit,
    cusip_from_isin,
    is_valid_cusip,
    normalize_cusip,
)


class TestCheckDigit:
    def test_known_check_digits(self):
        assert cusip_check_digit("75513E10") == "1"   # RTX
        assert cusip_check_digit("34959E10") == "9"   # Fortinet
        assert cusip_check_digit("40051E20") == "2"   # Grupo Sureste
        assert cusip_check_digit("00036110") == "5"   # AAR Corp

    def test_unparseable_returns_none(self):
        assert cusip_check_digit("123") is None       # wrong length
        assert cusip_check_digit("12345!78") is None  # bad char


class TestIsValid:
    def test_valid(self):
        assert is_valid_cusip("75513E101")
        assert is_valid_cusip("037833100")  # Apple
        assert is_valid_cusip("011659109")  # Alaska Air

    def test_invalid(self):
        assert not is_valid_cusip("361105")        # too short
        assert not is_valid_cusip("7.55E+105")     # corrupted
        assert not is_valid_cusip("037833101")     # wrong check digit


class TestCusipFromIsin:
    def test_us_isin(self):
        assert cusip_from_isin("US34959E1091") == "34959E109"

    def test_canadian_isin(self):
        assert cusip_from_isin("CA82509L1076") == "82509L107"  # Shopify

    def test_non_north_american(self):
        assert cusip_from_isin("NL0009805522") is None

    def test_blank(self):
        assert cusip_from_isin("") is None
        assert cusip_from_isin("N/A") is None


class TestNormalize:
    def test_sentinels_pass_through(self):
        assert normalize_cusip("") == ("", None)
        assert normalize_cusip("N/A") == ("N/A", None)
        assert normalize_cusip("000000000") == ("000000000", None)

    def test_valid_untouched(self):
        assert normalize_cusip("037833100") == ("037833100", None)

    def test_dropped_leading_zeros(self):
        assert normalize_cusip("361105") == ("000361105", None)
        assert normalize_cusip("11659109") == ("011659109", None)
        assert normalize_cusip("9066101") == ("009066101", None)

    def test_scientific_notation_recovered_from_isin(self):
        cusip, warning = normalize_cusip("3.50E+113", "US34959E1091")
        assert cusip == "34959E109"
        assert warning is None

    def test_bloomberg_error_text_becomes_na(self):
        cusip, warning = normalize_cusip("#N/A N/A")
        assert cusip == "N/A"
        assert warning is not None
        assert normalize_cusip("#N/A Invalid Security")[0] == "N/A"

    def test_scientific_notation_unrecoverable_warns(self):
        cusip, warning = normalize_cusip("7.55E+105")
        assert cusip == "7.55E+105"       # returned unchanged
        assert warning is not None        # flagged for manual fix

    def test_isin_preferred_when_padding_check_fails(self):
        # A short numeric value whose zero-pad fails the check digit but
        # whose ISIN gives a clean answer.
        cusip, warning = normalize_cusip("34959109", "US34959E1091")
        assert cusip == "34959E109"
        assert warning is None
