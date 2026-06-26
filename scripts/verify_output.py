"""Verify every N-PORT XML in output/ — structure (SEC XSD) + content (every value).

For each file:
  1. well-formedness (lxml parse)
  2. structural validation against the SEC v1.13 XSD (NportValidator)
  3. content walk — every element's text and every attribute value is classified by
     name and checked for sanity (dates, LEIs, CUSIPs, ISINs, currencies, countries,
     numbers, Y/N flags, id patterns) + placeholder scan
  4. cross-field checks (NAV identity, holding %/count, period dates)

Run:  uv run python scripts/verify_output.py [output_dir]
"""
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from lxml import etree

from nport.xsd_validator import NportValidator

# ── value patterns ────────────────────────────────────────────
_LEI = re.compile(r"^[0-9A-Z]{18}[0-9]{2}$")
_CUSIP = re.compile(r"^[0-9A-HJ-NP-Z]{8}[0-9A-HJ-NP-Z]$")
_ISIN = re.compile(r"^[A-Z]{2}[0-9A-Z]{9}[0-9]$")
_SERIES = re.compile(r"^S\d{9}$")
_CLASS = re.compile(r"^C\d{9}$")
_CIK = re.compile(r"^\d{1,10}$")
_CCY = re.compile(r"^[A-Z]{3}$")
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YN = re.compile(r"^[YN]$")
_PLACEHOLDER = re.compile(r"\b(todo|fixme|placeholder|fake|synthetic|dummy|sample|tbd)\b", re.I)
_TENORS = {"Day", "Week", "Month", "Year"}

_NA = "N/A"
_DATE_NAMES = {"reppdend", "reppddate", "datesigned"}
# names ending in "dt" that are NOT calendar dates (N-PORT tenor descriptors)
_NOT_DATES = {"resetdt"}
_TENOR_NAMES = {"ratetenor", "resetdt", "pmntratetenor", "ratetenorunit"}
_NUM_NAMES = {
    "totassets", "totliabs", "netassets", "valusd", "pctval", "balance", "rtn1", "rtn2",
    "rtn3", "netrealizedgain", "netunrealizedappr", "sales", "redemption", "reinvestment",
    "notionalamt", "unrealizedappr", "delta", "exerciseprice", "annualizedrt", "couponrt",
    "assetsattrmiscsec", "assetsinvested", "amtpayoneyrbanksborr", "amtpayoneyrctrldcomp",
    "amtpayoneyrothaffil", "amtpayoneyrother", "amtpayaftoneyrbanksborr",
    "amtpayaftoneyrctrldcomp", "amtpayaftoneyrothaffil", "amtpayaftoneyrother",
    "delaydeliv", "standbycommit", "liquidpref", "pmntpmntamt", "fairvallevel",
}
_YN_NAMES = {
    "isfinalfiling", "isnoncashcollateral", "isdefault", "areintrstpmntsinarrs",
    "ispaidkind", "isrestrictedsec", "iscashcollateral", "isnoncashcollateral",
    "isloanbyfund",
}


def _is_num(v: str) -> bool:
    try:
        float(v.replace(",", ""))
        return True
    except ValueError:
        return False


def _check_value(name: str, value: str, path: str, errs: list, warns: list) -> None:
    """Validate one element-text/attribute value by its (local) name."""
    n = name.lower()
    v = value.strip()
    if v == "":
        warns.append(f"{path}: empty value <{name}>")
        return
    if _PLACEHOLDER.search(v) and n != "ccc":
        warns.append(f"{path}: placeholder-looking value {name}={v!r}")

    if n in ("ratetenor", "resetdt"):
        if v != _NA and v not in _TENORS:
            errs.append(f"{path}: bad tenor {name}={v!r} (expect Day/Week/Month/Year)")
    elif (n in _DATE_NAMES or n.endswith("dt")) and n not in _NOT_DATES:
        if v != _NA and (not _DATE.match(v) or not _valid_date(v)):
            errs.append(f"{path}: bad date {name}={v!r}")
    elif "lei" in n:
        if v != _NA and not _LEI.match(v):
            errs.append(f"{path}: bad LEI {name}={v!r}")
    elif n == "cusip":
        if v not in (_NA, "000000000") and not _CUSIP.match(v):
            errs.append(f"{path}: bad CUSIP {name}={v!r}")
    elif n == "isin" or n.endswith("isin"):
        if v != _NA and not _ISIN.match(v):
            errs.append(f"{path}: bad ISIN {name}={v!r}")
    elif n == "seriesid":
        if not _SERIES.match(v):
            errs.append(f"{path}: bad seriesId {v!r}")
    elif n == "classid":
        if not _CLASS.match(v):
            errs.append(f"{path}: bad classId {v!r}")
    elif n in ("cik", "regcik"):
        if not _CIK.match(v):
            errs.append(f"{path}: bad CIK {name}={v!r}")
    elif "country" in n:
        if v != _NA and not _COUNTRY.match(v):
            errs.append(f"{path}: bad country {name}={v!r}")
    elif n.endswith("curcd") or n == "curcd" or n == "exercisepricecurcd":
        if v != _NA and not _CCY.match(v):
            errs.append(f"{path}: bad currency {name}={v!r}")
    elif n in _YN_NAMES:
        if v not in ("Y", "N", "true", "false"):
            errs.append(f"{path}: bad Y/N {name}={v!r}")
    elif n in _NUM_NAMES:
        if v != _NA and not _is_num(v):
            errs.append(f"{path}: non-numeric {name}={v!r}")


def _valid_date(v: str) -> bool:
    try:
        datetime.strptime(v, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _scan_raw_lines(raw: bytes, errs: list, warns: list) -> int:
    """Literal per-physical-line pass: byte-level integrity of every single line."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        errs.append(f"file is not valid UTF-8: {e}")
        text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    for i, ln in enumerate(lines, 1):
        if "�" in ln:
            errs.append(f"L{i}: contains the Unicode replacement char (encoding damage)")
        bad = [hex(ord(c)) for c in ln if ord(c) < 0x20 and c != "\t"]
        if bad:
            errs.append(f"L{i}: control characters {bad}")
        # a data line should be a balanced single-element line: <tag ...>text</tag> or <tag/>
        s = ln.strip()
        if s and not s.startswith("<?") and s.count("<") != s.count(">"):
            errs.append(f"L{i}: unbalanced angle brackets: {s[:60]!r}")
    return len(lines)


def verify_file(path: Path, validator: NportValidator) -> tuple[list, list, int]:
    errs: list[str] = []
    warns: list[str] = []
    raw = path.read_bytes()

    nlines = _scan_raw_lines(raw, errs, warns)

    # 1. well-formedness
    try:
        root = etree.fromstring(raw)
    except etree.XMLSyntaxError as e:
        return [f"not well-formed XML: {e}", *errs], [], nlines

    # 2. structure vs SEC XSD
    for e in validator.validate_xsd(raw):
        errs.append(f"XSD: {e}")

    # 3. content walk — every element text + every attribute
    for el in root.iter():
        name = _local(el.tag)
        line = el.sourceline
        if el.text and el.text.strip():
            _check_value(name, el.text, f"L{line} <{name}>", errs, warns)
        for an, av in el.attrib.items():
            _check_value(_local(an), av, f"L{line} <{name} @{_local(an)}>", errs, warns)

    # 4. cross-field sanity
    ns = {"n": "http://www.sec.gov/edgar/nport"}

    def num(xp):
        el = root.find(xp, ns)
        try:
            return float(el.text)
        except (AttributeError, TypeError, ValueError):
            return None
    ta, tl, na = num(".//n:totAssets"), num(".//n:totLiabs"), num(".//n:netAssets")
    if None not in (ta, tl, na) and abs(na - (ta - tl)) > 0.05:
        errs.append(f"NAV identity: netAssets {na} != totAssets {ta} - totLiabs {tl}")
    holdings = root.findall(".//n:invstOrSec", ns)
    if not holdings:
        warns.append("no holdings (invstOrSec) in filing")
    pcts = []
    for h in holdings:
        p = h.find("n:pctVal", ns)
        if p is not None and p.text and _is_num(p.text):
            pcts.append(float(p.text))
    if pcts:
        tot = sum(pcts)
        if not (90 <= tot <= 110):
            warns.append(f"sum(pctVal) = {tot:.1f}% (expected ~100)")
    return errs, warns, nlines


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("output")
    files = sorted(out_dir.glob("*.xml"))
    if not files:
        print(f"No XML files in {out_dir}")
        sys.exit(1)
    validator = NportValidator()
    clean, with_err, with_warn = [], [], []
    err_kinds: Counter = Counter()
    total_lines = 0
    print(f"Verifying {len(files)} XML files in {out_dir}/ ...\n")
    for f in files:
        errs, warns, nlines = verify_file(f, validator)
        total_lines += nlines
        for e in errs:
            err_kinds[e.split(":")[0].replace("XSD", "XSD-structure")] += 1
        if errs:
            with_err.append((f.name, errs, warns))
        elif warns:
            with_warn.append((f.name, warns))
        else:
            clean.append(f.name)

    for name, errs, warns in with_err:
        print(f"✗ {name}: {len(errs)} error(s)")
        for e in errs[:6]:
            print(f"    {e}")
        if len(errs) > 6:
            print(f"    … +{len(errs) - 6} more")
    print()
    for name, warns in with_warn:
        print(f"⚠ {name}: {'; '.join(warns[:3])}")
    print(f"\n{'='*60}")
    print(f"Physical XML lines checked:     {total_lines:,} across {len(files)} files")
    print(f"CLEAN (structure + content OK): {len(clean)}/{len(files)}")
    print(f"WARN only:                      {len(with_warn)}/{len(files)}")
    print(f"ERRORS:                         {len(with_err)}/{len(files)}")
    if err_kinds:
        print("\nError categories:")
        for k, c in err_kinds.most_common():
            print(f"  {c:4}  {k}")


if __name__ == "__main__":
    main()
