"""Parametrized tests — load each fund dir, validate, build XML, XSD check.

Discovers every (fund, period) pair that actually has both a filing_data.txt and
a built holdings.csv, so the suite covers each fund for the period(s) it has data
for (rather than a single hardcoded period).
"""

from pathlib import Path

import pytest

from nport.builder import NportBuilder
from nport.data_loader import DataLoader
from nport.input_validation import validate_all
from nport.xsd_validator import NportValidator

_FUNDS_DIR = Path(__file__).resolve().parent.parent / "data" / "funds"


def _fund_period_pairs():
    pairs = []
    for p in sorted(_FUNDS_DIR.iterdir()):
        if not (p.is_dir() and (p / "fund_config.txt").is_file()):
            continue
        filings = p / "filings"
        if not filings.is_dir():
            continue
        for per in sorted(filings.iterdir()):
            if (per / "filing_data.txt").is_file() and (per / "holdings.csv").is_file():
                pairs.append((p, per.name))
    return pairs


_PAIRS = _fund_period_pairs()
_IDS = [f"{p.name}-{per}" for p, per in _PAIRS]


@pytest.mark.parametrize("fund_dir,period", _PAIRS, ids=_IDS)
class TestFundDirectory:
    def test_load_and_validate(self, fund_dir: Path, period: str):
        """Load fund, validate inputs — no errors expected."""
        loader = DataLoader(fund_dir)
        config, filing, holdings = loader.load_all(period)
        errors, _ = validate_all(config, filing, holdings)
        assert not errors, f"Validation errors for {fund_dir.name} {period}: {errors}"

    def test_build_and_xsd(self, fund_dir: Path, period: str):
        """Load fund, build XML, XSD validate — no errors expected."""
        loader = DataLoader(fund_dir)
        config, filing, holdings = loader.load_all(period)
        xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
        xsd_errors = NportValidator().validate_xsd(xml_bytes)
        assert not xsd_errors, f"XSD errors for {fund_dir.name} {period}: {xsd_errors}"
