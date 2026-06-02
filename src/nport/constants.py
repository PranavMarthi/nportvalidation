"""Namespace URIs and paths for N-PORT XML generation."""

from pathlib import Path

# XML Namespaces
NS_NPORT = "http://www.sec.gov/edgar/nport"
NS_COMMON = "http://www.sec.gov/edgar/common"
NS_NPORTCOMMON = "http://www.sec.gov/edgar/nportcommon"
NS_XSI = "http://www.w3.org/2001/XMLSchema-instance"

NSMAP = {
    None: NS_NPORT,
    "com": NS_COMMON,
    "ncom": NS_NPORTCOMMON,
    "xsi": NS_XSI,
}

# src/nport/constants.py -> src/nport -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_DIR = PROJECT_ROOT / "schemas" / "v1_13"
ROOT_SCHEMA_FILE = "eis_NPORT_Filer.xsd"
