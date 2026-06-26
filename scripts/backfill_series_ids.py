"""Write each fund's REAL seriesId + classId (and seriesName) from EDGAR.

Source chain — nothing fabricated:
  * The trust's series/class spreadsheet (data/reference/series_guide.xlsx, an EDGAR
    export) gives the authoritative (seriesId, classId, seriesName) for every registered
    series. This is the default source: deterministic, offline, every series single-class
    (no ambiguous drops). Pass --from-edgar to instead harvest live from EDGAR filing
    headers (CIK 0002078265).
  * Bloomberg ``LONG_COMP_NAME`` (gathered live via the MCP; embedded below with
    provenance) is the ticker -> official-name bridge, since our config seriesNames
    were placeholders.
  * We match Bloomberg name -> series name (exact after normalization). A fund is
    written ONLY on a confident single match; everything else is left blank and reported.

Run:  uv run python scripts/backfill_series_ids.py [--dry-run] [--from-edgar]
"""
import re
import sys
from pathlib import Path

from nport.edgar import EdgarClient, load_trust_series_from_xlsx, normalize_fund_name

FUNDS = Path("data/funds")
SERIES_GUIDE = Path("data/reference/series_guide.xlsx")
CIK = "0002078265"
USER_AGENT = "Corgi ETF Trust nport-tool@example.com"

# ticker -> Bloomberg LONG_COMP_NAME (the registered fund name). Gathered live via the
# Bloomberg MCP (reference_data LONG_COMP_NAME on "<ticker> US Equity").
BBG_NAME = {
    "AV": "Corgi Aerospace & Commercial Aviation ETF",
    "BAY": "Corgi Bay Area Based ETF",
    "BLCK": "Corgi Crypto Infrastructure ETF",
    "BREW": "Corgi Coffee & Energy Drinks ETF",
    "BRZX": "Corgi Brazil 2x Daily ETF",
    "BZZ": "Corgi Drones & Urban Air Mobility ETF",
    "CBIL": "Corgi 3-12 Month T-Bill ETF",
    "CBOT": "Corgi Robots & Humanoids ETF",
    "CCPX": "Corgi China 2x Daily ETF",
    "CGOV": "Corgi 0-3 Month T-Bill ETF",
    "CHYG": "Corgi 0-5 Year High Yield Corporate Bond ETF",
    "CIEI": "Corgi 3-7 Year Treasury Bond ETF",
    "CIVG": "Corgi 1-5 Year Investment Grade Corporate Bond ETF",
    "CJUN": "Corgi US Equities 15% Structured Buffer ETF - June Series",
    "CMAG": "Corgi Mag 7 ETF",
    "CMAY": "Corgi US Equities 15% Structured Buffer ETF - May Series",
    "CQTM": "Corgi Quantum Computing ETF",
    "CTJN": "Corgi US Equities 30% Structured Buffer ETF - June Series",
    "CTMA": "Corgi U.S. Equities 30% Structured Buffer ETF - May Series",
    "CUST": "Corgi 1-3 Year Treasury Bond ETF",
    "DIPR": "Corgi Space & Satellite Communications ETF",
    "DOCK": "Corgi Ports Rail & Freight ETF",
    "EMJN": "Corgi Emerging Markets Equities 15% Structured Buffer ETF - June Series",
    "EMMY": "Corgi Emerging Markets Equities 15% Structured Buffer ETF - May Series",
    "EMXX": "Corgi Emerging Markets 2x Daily ETF",
    "EUV": "Corgi Lithography & Semiconductor Photonics ETF",
    "EUVX": "Corgi Lithography & Semiconductor Photonics 2x Daily ETF",
    "EYES": "Corgi Data & Surveillance ETF",
    "FDRS": "Corgi Founder-Led ETF",
    "FDRX": "Corgi Founder-Led 2x Daily ETF",
    "GASZ": "Corgi Natural Gas Power & Turbines ETF",
    "GLAM": "Corgi Beauty Skincare & Aesthetics ETF",
    "GNMX": "Corgi Genomics & Precision Medicine ETF",
    "GPTZ": "Corgi AGI Readiness ETF",
    "HJUN": "Corgi US Equities 100% Structured Buffer ETF - June Series",
    "HMAY": "Corgi US Equities 100% Structured Buffer ETF - May Series",
    "HULL": "Corgi Shipping & Global Logistics ETF",
    "IDJN": "Corgi International Developed Equities 15% Structured Buffer ETF - June Series",
    "IDMY": "Corgi International Developed Equities 15% Structured Buffer ETF - May Series",
    "JOUL": "Corgi High Voltage Grid Equipment ETF",
    "JUNC": "Corgi US Equities 10% Structured Buffer ETF - June Series",
    "KRWX": "Corgi South Korea 2x Daily ETF",
    "KYC": "Corgi Digital Banking & Fintech Infrastructure ETF",
    "LATR": "Corgi Buy Now Pay Later ETF",
    "MAYC": "Corgi US Equities 10% Structured Buffer ETF - May Series",
    "MGKX": "Corgi US Mega-Cap Growth 2x Daily ETF",
    "NYNY": "Corgi NYC Based ETF",
    "ODDZ": "Corgi Sports Betting & Gambling ETF",
    "OWN": "Corgi Inside Ownership 100 ETF",
    "PTNT": "Corgi IP Licensing & Royalties ETF",
    "QJN": "Corgi Growth & Technology 10% Structured Buffer ETF - June Series",
    "QMY": "Corgi Growth & Technology 10% Structured Buffer ETF - May Series",
    "QQJN": "Corgi Growth & Technology 15% Structured Buffer ETF - June Series",
    "QQMY": "Corgi Growth & Technology 15% Structured Buffer ETF - May Series",
    "SCJN": "Corgi US Small-Cap 15% Structured Buffer ETF - June Series",
    "SCMY": "Corgi U.S. Small-Cap 15% Structured Buffer ETF - May Series",
    "STYL": "Corgi Lifestyle Brands ETF",
    "TAJX": "Corgi India 2x Daily ETF",
    "USX": "Corgi Total US Market 2x Daily ETF",
    "VBX": "Corgi US Small-Cap 2x Daily ETF",
    "VOOX": "Corgi US Large-Cap 2x Daily ETF",
    "WATS": "Corgi Battery Energy Storage Systems ETF",
    "WEBX": "Corgi Chinese Internet 2x Daily ETF",
    "WNDR": "Corgi Travel & Leisure ETF",
    "WR": "Corgi U.S. War Machine ETF",
    "WX": "Corgi All World 2x Daily ETF",
    "XA": "Corgi AI Cybersecurity ETF",
    "XAGI": "Corgi AGIX 2x Daily ETF",
    "XBIX": "Corgi US Biotech 2x Daily ETF",
    "XCOM": "Corgi All Commodities 2x Daily ETF",
    "XEUR": "Corgi Europe Equities 2x Daily ETF",
    "XHOA": "Corgi US Real Estate 2x Daily ETF",
    "XIWC": "Corgi US Micro-Cap 2x Daily ETF",
    "XKRE": "Corgi US Regional Banks 2x Daily ETF",
    "XLBX": "Corgi US Materials 2x Daily ETF",
    "XLEX": "Corgi US Energy 2x Daily ETF",
    "XLFX": "Corgi US Financials 2x Daily ETF",
    "XLIX": "Corgi US Industrials 2x Daily ETF",
    "XLKX": "Corgi US Technology 2x Daily ETF",
    "XLPX": "Corgi US Consumer Staples 2x Daily ETF",
    "XLUX": "Corgi US Utilities 2x Daily ETF",
    "XLVX": "Corgi US Healthcare 2x Daily ETF",
    "XLYX": "Corgi US Consumer Discretionary 2x Daily ETF",
    "XPAV": "Corgi US Manufacturing 2x Daily ETF",
    "XSEM": "Corgi US Semiconductors 2x Daily ETF",
    "XTAI": "Corgi Taiwan 2x Daily ETF",
    "XVO": "Corgi US Mid-Cap 2x Daily ETF",
    "XVUG": "Corgi US Growth 2x Daily ETF",
    "XW": "Corgi Ex-US Equities 2x Daily ETF",
    "YUNG": "Corgi Longevity Consumer ETF",
    # 2026-06 new launches
    "ACLZ": "Corgi ACLS 2x Daily ETF", "ACMM": "Corgi ACMR 2x Daily ETF",
    "CAMC": "Corgi CAMT 2x Daily ETF", "CARX": "Corgi CART 2x Daily ETF",
    "CRUC": "Corgi CRUS 2x Daily ETF", "KEYX": "Corgi KEYS 2x Daily ETF",
    "LASC": "Corgi LASR 2x Daily ETF", "LRNX": "Corgi LRN 2x Daily ETF",
    "MNSX": "Corgi MNST 2x Daily ETF", "MSIX": "Corgi MSI 2x Daily ETF",
    "ONTX": "Corgi ONTO 2x Daily ETF", "RMBC": "Corgi RMBS 2x Daily ETF",
    "SIMX": "Corgi SIMO 2x Daily ETF", "TPLX": "Corgi TPL 2x Daily ETF",
    "UMCX": "Corgi UMC 2x Daily ETF",
}


def _set_kv(text: str, key: str, value: str) -> str:
    if re.search(rf"(?m)^{key}=.*$", text):
        return re.sub(rf"(?m)^{key}=.*$", f"{key}={value}", text)
    return text.rstrip() + f"\n{key}={value}\n"


def main() -> None:
    dry = "--dry-run" in sys.argv
    from_edgar = "--from-edgar" in sys.argv
    if from_edgar:
        print(f"Harvesting series for CIK {CIK} from EDGAR filing headers ...")
        by_name = EdgarClient(USER_AGENT).harvest_trust_series(CIK)
        print(f"  {len(by_name)} distinct series harvested from EDGAR.\n")
    else:
        if not SERIES_GUIDE.is_file():
            sys.exit(f"ERROR: series guide not found: {SERIES_GUIDE}\n"
                     f"  (place the export there, or pass --from-edgar to use live EDGAR.)")
        print(f"Loading series from {SERIES_GUIDE} ...")
        by_name = load_trust_series_from_xlsx(SERIES_GUIDE)
        print(f"  {len(by_name)} distinct series loaded from spreadsheet.\n")

    matched, unmatched, ambiguous = [], [], []
    for d in sorted(FUNDS.iterdir()):
        cfg = d / "fund_config.txt"
        if not cfg.is_file():
            continue
        ticker = d.name.upper()
        bbg = BBG_NAME.get(ticker)
        if not bbg:
            unmatched.append((ticker, "no Bloomberg name (example/non-Corgi fund)"))
            continue
        s = by_name.get(normalize_fund_name(bbg))
        if not s:
            unmatched.append((ticker, f"no EDGAR series matches '{bbg}'"))
            continue
        if len(s.classes) != 1:
            ambiguous.append((ticker, f"{len(s.classes)} classes for {s.series_id}"))
            continue
        class_id = s.classes[0][0]
        matched.append((ticker, s.series_id, class_id, s.series_name))
        if not dry:
            text = cfg.read_text(encoding="utf-8")
            text = _set_kv(text, "seriesId", s.series_id)
            text = _set_kv(text, "classId", class_id)
            text = _set_kv(text, "seriesName", s.series_name)
            cfg.write_text(text, encoding="utf-8")

    verb = "WOULD write" if dry else "wrote"
    print(f"MATCHED ({len(matched)}) — {verb} seriesId+classId+seriesName:")
    for t, sid, cid, name in matched:
        print(f"  {t:6} {sid}  {cid}  {name}")
    if ambiguous:
        print(f"\nAMBIGUOUS ({len(ambiguous)}) — multiple classes, left blank:")
        for t, why in ambiguous:
            print(f"  {t:6} {why}")
    if unmatched:
        print(f"\nUNMATCHED ({len(unmatched)}) — left blank (needs manual EDGAR lookup):")
        for t, why in unmatched:
            print(f"  {t:6} {why}")


if __name__ == "__main__":
    main()
