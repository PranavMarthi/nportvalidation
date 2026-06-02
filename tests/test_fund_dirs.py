"""Parametrized tests — load each fund dir, validate, build XML, XSD check."""

from pathlib import Path

import pytest

from nport.builder import NportBuilder
from nport.data_loader import DataLoader
from nport.input_validation import validate_all
from nport.xsd_validator import NportValidator

_FUNDS_DIR = Path(__file__).resolve().parent.parent / "data" / "funds"
_FUND_DIRS = sorted(p for p in _FUNDS_DIR.iterdir() if p.is_dir() and (p / "fund_config.txt").is_file())
_FUND_IDS = [p.name for p in _FUND_DIRS]


@pytest.mark.parametrize("fund_dir", _FUND_DIRS, ids=_FUND_IDS)
class TestFundDirectory:
    def test_load_and_validate(self, fund_dir: Path):
        """Load fund, validate inputs — no errors expected."""
        loader = DataLoader(fund_dir)
        config, filing, holdings = loader.load_all("2025-12")
        errors, _ = validate_all(config, filing, holdings)
        assert not errors, f"Validation errors for {fund_dir.name}: {errors}"

    def test_build_and_xsd(self, fund_dir: Path):
        """Load fund, build XML, XSD validate — no errors expected."""
        loader = DataLoader(fund_dir)
        config, filing, holdings = loader.load_all("2025-12")
        xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
        xsd_errors = NportValidator().validate_xsd(xml_bytes)
        assert not xsd_errors, f"XSD errors for {fund_dir.name}: {xsd_errors}"
