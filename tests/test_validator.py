"""Tests for XSD schema validation."""

from nport.builder import NportBuilder
from nport.xsd_validator import NportValidator


def test_generated_xml_passes_xsd(sample_data, schema_dir):
    config, filing, holdings = sample_data
    xml_bytes = NportBuilder(config, filing, holdings).to_xml_bytes()
    errors = NportValidator(schema_dir).validate_xsd(xml_bytes)
    assert errors == [], f"XSD validation errors: {errors}"


def test_malformed_xml_fails():
    validator = NportValidator()
    errors = validator.validate_xsd(b"<not valid xml")
    assert len(errors) == 1
    assert "parse error" in errors[0].lower()
