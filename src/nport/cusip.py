"""CUSIP normalization and recovery from spreadsheet corruption.

Opening a CSV in Excel (or any spreadsheet) and re-saving silently
corrupts CUSIPs two ways, because a CUSIP looks like a number:

  * **Dropped leading zeros** on all-numeric CUSIPs::

        000361105 -> 361105        011659109 -> 11659109

  * **Scientific notation** on CUSIPs containing an embedded ``E``
    (a legal CUSIP character), rewritten with lost precision::

        75513E101 -> 7.55E+105     34959E109 -> 3.50E+113

A CUSIP is always exactly 9 characters: an 8-char body plus a mod-10
check digit. The leading-zero case is fully reversible (left-pad to 9).
The scientific-notation case is **not** reversible from the mangled
string alone, so we recover it from the row's ISIN when present — a US
or Canadian ISIN embeds the CUSIP in positions 3-11 — and otherwise
report it for manual repair rather than guessing.

This module is dependency-free so it can be imported from any read path
(custodian parser, security master loader) and from repair scripts.
"""

import re

_SCI_NOTATION_RE = re.compile(r"^\d(?:\.\d+)?[eE][+-]?\d+$")
_ALL_DIGITS_RE = re.compile(r"^\d+$")
_SENTINELS = {"", "N/A", "000000000"}

# ISINs whose national identifier *is* a CUSIP (North America).
_CUSIP_ISIN_PREFIXES = ("US", "CA")

# CUSIP character values for the check-digit calculation.
_CHAR_VALUES = {
    **{str(d): d for d in range(10)},
    **{chr(ord("A") + i): 10 + i for i in range(26)},
    "*": 36, "@": 37, "#": 38,
}


def cusip_check_digit(body: str) -> str | None:
    """Return the check digit for an 8-char CUSIP body, or None if unparseable.

    Standard CUSIP modulus-10 ``double-add-double`` over the first 8 chars.
    """
    if len(body) != 8:
        return None
    total = 0
    for i, ch in enumerate(body):
        v = _CHAR_VALUES.get(ch.upper())
        if v is None:
            return None
        if i % 2 == 1:  # even position (1-indexed) is doubled
            v *= 2
        total += v // 10 + v % 10
    return str((10 - (total % 10)) % 10)


def is_valid_cusip(cusip: str) -> bool:
    """True if a 9-char string has a self-consistent check digit."""
    if len(cusip) != 9 or not cusip[8].isdigit():
        return False
    return cusip_check_digit(cusip[:8]) == cusip[8]


def cusip_from_isin(isin: str) -> str | None:
    """Extract a valid CUSIP from a US/CA ISIN, or None."""
    isin = (isin or "").strip().upper()
    if len(isin) == 12 and isin[:2] in _CUSIP_ISIN_PREFIXES:
        candidate = isin[2:11]
        if is_valid_cusip(candidate):
            return candidate
    return None


def normalize_cusip(raw: str, isin: str = "") -> tuple[str, str | None]:
    """Repair a possibly spreadsheet-corrupted CUSIP.

    Returns ``(cusip, warning)``. ``warning`` is None on success; on an
    unrecoverable corruption it is a human-readable message and ``cusip``
    is returned unchanged so existing format validation still surfaces it.

    Recovery rules, in order:
      1. Sentinels (``""``, ``N/A``, ``000000000``) and already-valid
         CUSIPs pass through untouched.
      2. Scientific notation -> recover from the ISIN, else warn.
      3. All-numeric and shorter than 9 -> left-pad to 9 (dropped zeros).
      4. Anything else still invalid -> try the ISIN as a last resort.
    """
    cusip = (raw or "").strip()
    if cusip in _SENTINELS:
        return cusip, None

    # Bloomberg-error text saved as a literal ("#N/A N/A", "#N/A Invalid
    # Security") is not a CUSIP — treat it as the N/A sentinel.
    if cusip.startswith("#"):
        return "N/A", f"CUSIP '{cusip}' is Bloomberg-error text; treated as N/A."

    if is_valid_cusip(cusip):
        return cusip, None

    # Scientific-notation corruption — the original digits are gone.
    if _SCI_NOTATION_RE.match(cusip):
        recovered = cusip_from_isin(isin)
        if recovered:
            return recovered, None
        return cusip, (
            f"CUSIP '{cusip}' looks spreadsheet-corrupted (scientific "
            f"notation) and has no ISIN to recover it from — fix by hand."
        )

    # Dropped leading zeros — padding to 9 is the only way to reach length 9.
    if _ALL_DIGITS_RE.match(cusip) and len(cusip) < 9:
        padded = cusip.zfill(9)
        if is_valid_cusip(padded):
            return padded, None
        # Check digit disagrees; prefer the ISIN if it gives a clean answer.
        recovered = cusip_from_isin(isin)
        if recovered:
            return recovered, None
        return padded, None  # best effort: a 9-char numeric CUSIP

    # Last resort for any other invalid value.
    recovered = cusip_from_isin(isin)
    if recovered:
        return recovered, None
    return cusip, None
