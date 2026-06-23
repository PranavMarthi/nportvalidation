"""XSD schema validation for N-PORT XML.

Solely responsible for validating generated XML against the SEC's
N-PORT XSD schema. Input-level validation lives in input_validation.py.
"""

from pathlib import Path

from lxml import etree

from nport.constants import DEFAULT_SCHEMA_DIR, ROOT_SCHEMA_FILE


class NportValidator:
    def __init__(self, schema_dir: str | Path | None = None):
        schema_dir = Path(schema_dir) if schema_dir else DEFAULT_SCHEMA_DIR
        schema_path = schema_dir / ROOT_SCHEMA_FILE
        if not schema_path.exists():
            raise FileNotFoundError(
                f"Schema not found: {schema_path}. "
                f"Download from: https://www.sec.gov/files/edgar/filer-information/"
                f"specifications/edgar-form-n-port-xml-tech-spec-113.zip"
            )
        try:
            self.schema = etree.XMLSchema(etree.parse(str(schema_path)))
        except (etree.XMLSyntaxError, etree.XMLSchemaParseError) as e:
            raise ValueError(f"Malformed XSD schema at {schema_path}: {e}")

    def validate_xsd(self, xml_bytes: bytes) -> list[str]:
        """Returns list of error messages. Empty = valid."""
        try:
            doc = etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as e:
            return [f"XML parse error: {e}"]

        if self.schema.validate(doc):
            return []

        # Known EDGAR quirk: v1.13 XSD requires medianDailyVarPct in varInfo,
        # but EDGAR accepts filings without it (Rule 18f-4 exemption).
        return [
            f"Line {err.line}: {err.message}"
            for err in self.schema.error_log
            if "medianDailyVarPct" not in err.message
        ]
