"""Schema version monitoring.

Checks SEC website for N-PORT schema updates and verifies local
schema files are present and intact.
"""

import hashlib
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

from nport.constants import DEFAULT_SCHEMA_DIR

_TECH_SPECS_URL = "https://www.sec.gov/submit-filings/technical-specifications"

CURRENT_SCHEMA_VERSION = "1.13"
CURRENT_SCHEMA_DATE = "2025-03-17"
CURRENT_SCHEMA_ZIP = (
    "https://www.sec.gov/files/edgar/filer-information/"
    "specifications/edgar-form-n-port-xml-tech-spec-113.zip"
)

_CACHE_FILE = DEFAULT_SCHEMA_DIR / ".schema_check_cache.json"

EXPECTED_SCHEMA_FILES = [
    "eis_NPORT_Filer.xsd",
    "eis_NPORT_common.xsd",
    "eis_Common.xsd",
    "eis_ISO_StateCodes.xsd",
    "eis_stateCodes.xsd",
]


def check_schema_files(schema_dir: str | Path | None = None) -> tuple[list[str], list[str]]:
    """Verify all required XSD files are present and non-empty."""
    schema_dir = Path(schema_dir) if schema_dir else DEFAULT_SCHEMA_DIR
    errors, warnings = [], []

    if not schema_dir.exists():
        errors.append(f"Schema directory not found: {schema_dir}. Download from: {CURRENT_SCHEMA_ZIP}")
        return errors, warnings

    for filename in EXPECTED_SCHEMA_FILES:
        path = schema_dir / filename
        if not path.exists():
            errors.append(f"Missing schema file: {path}. Download from: {CURRENT_SCHEMA_ZIP}")
        elif path.stat().st_size == 0:
            errors.append(f"Schema file is empty: {path}.")

    return errors, warnings


def check_for_schema_update(force: bool = False, cache_days: int = 7) -> tuple[str | None, list[str]]:
    """Check SEC website for a newer N-PORT schema version. Uses local cache."""
    warnings = []

    if not force and _CACHE_FILE.exists():
        try:
            cache = json.loads(_CACHE_FILE.read_text())
            if (datetime.now() - datetime.fromisoformat(cache["last_check"])).days < cache_days:
                if cache.get("newer_version"):
                    warnings.append(
                        f"Schema update available: v{cache['newer_version']} "
                        f"(you have v{CURRENT_SCHEMA_VERSION}). Check: {_TECH_SPECS_URL}"
                    )
                    return cache["newer_version"], warnings
                return None, warnings
        except (json.JSONDecodeError, KeyError, ValueError):
            pass

    try:
        req = urllib.request.Request(
            _TECH_SPECS_URL,
            headers={"User-Agent": "Corgi NportFilingTool/0.1 research@corgi.insure"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        warnings.append(f"Could not check for schema updates: {e}")
        return None, warnings

    # Extract version from ZIP filenames (e.g. n-port-xml-tech-spec-113.zip -> 1.13)
    zip_matches = re.findall(r"n-port-xml-tech-spec[s]?-?(\d+)\.zip", html, re.IGNORECASE)
    newer_version = None

    if zip_matches:
        versions = {(int(m[0]), int(m[1:])) for m in zip_matches if len(m) >= 2}
        if versions:
            latest = max(versions)
            current = tuple(int(x) for x in CURRENT_SCHEMA_VERSION.split("."))
            if latest > current:
                newer_version = f"{latest[0]}.{latest[1]}"
                warnings.append(
                    f"SCHEMA UPDATE: N-PORT v{newer_version} available "
                    f"(you have v{CURRENT_SCHEMA_VERSION}). Check: {_TECH_SPECS_URL}"
                )

    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps({
            "last_check": datetime.now().isoformat(),
            "current_version": CURRENT_SCHEMA_VERSION,
            "newer_version": newer_version,
        }))
    except OSError:
        pass  # Cache is non-critical

    return newer_version, warnings


def get_schema_integrity_report(schema_dir: Path | None = None) -> dict:
    schema_dir = Path(schema_dir) if schema_dir else DEFAULT_SCHEMA_DIR
    files = {}
    for filename in EXPECTED_SCHEMA_FILES:
        path = schema_dir / filename
        if path.exists():
            files[filename] = {
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        else:
            files[filename] = {"missing": True}
    return {
        "schema_dir": str(schema_dir),
        "schema_version": CURRENT_SCHEMA_VERSION,
        "files": files,
    }
