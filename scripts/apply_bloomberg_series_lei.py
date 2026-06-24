"""Write the REAL per-fund seriesLei (from Bloomberg) into each fund_config.txt,
and set classId to the trust's reference class (per operator instruction).

seriesLei values were fetched live from Bloomberg via the MCP
(LEGAL_ENTITY_IDENTIFIER on "<ticker> US Equity") and verified exact-match to
EDGAR for FDRS/FDRX. 5 funds have no LEI on Bloomberg yet (not-yet-issued) and
keep their existing placeholder. seriesId is NOT changed here — Bloomberg does not
carry the SEC series ID; it must come from the SEC ticker file / fund admin.
"""
import re
from pathlib import Path

FUNDS = Path("data/funds")
CLASS_ID = "C000265520"  # trust reference class (per operator: keep classId the same)

# ticker -> real seriesLei from Bloomberg LEGAL_ENTITY_IDENTIFIER (None = no LEI yet)
BBG_LEI = {
    "AV": "529900615AR0BFA07331", "BAY": "529900W5PL67PXDSXQ71", "BLCK": "529900NW9E8YNN31W688",
    "BREW": "52990050ULTQ71841068", "BRZX": "529900D8UBHQ6X5NE549", "BZZ": "529900TS39FKLCBGCS16",
    "CBIL": "529900N4HGGNS73UTA37", "CBOT": "529900G19OE1Z981UI40", "CCPX": "529900CP2YXI6L3CPU03",
    "CGOV": "52990069N37TP4S86594", "CHYG": "5299006266TMTS8VGR27", "CIEI": "529900X1Q4OLUA05G183",
    "CIVG": "529900MA71XGSE6OLS57", "CJUN": None, "CMAG": "529900VPDO1DOBUNEZ81",
    "CMAY": "529900D7CSG5CAQNGT51", "CQTM": "529900IZDAH8EQQN6G09", "CTJN": None,
    "CTMA": "5299006CIU3J62M43O75", "CUST": "529900B593BSUD7FGR37", "DIPR": "529900JRJQZ1RZEMCK44",
    "DOCK": "529900PFNICEDYP35V27", "EMJN": "529900LIA2UL2VJVL159", "EMMY": "529900LORKFRDO5PXJ73",
    "EMXX": "529900M9A78CBLYAQX53", "EUV": "5299004GBVJQE52S5D46", "EUVX": "529900QR1IS06M2POY49",
    "EYES": "5299007CHX6J49FEC687", "FDRS": "529900Y4TPD7LE3K2C21", "FDRX": "5299009IIPGGROZ8QW15",
    "GASZ": "5299003BTC6BQQTKPZ63", "GLAM": "529900XGYJXUKNB8Q029", "GNMX": "529900U01V74E3830311",
    "GPTZ": "5299008NZHAKYAVRZU52", "HJUN": "529900FU3IDPCDKTCE79", "HMAY": "529900AJLXTZDJNSLR07",
    "HULL": "529900UUTEZR8QB18672", "IDJN": "529900LR38HUPEQRJC33", "IDMY": "529900BRRXMNYB3DCJ64",
    "JOUL": "529900IDWOUXXI44UE80", "JUNC": None, "KRWX": "529900OJSQ4DMJ4PXT78",
    "KYC": "529900QRLQ383GUT8829", "LATR": "529900N3LGDTCIFEF023", "MAYC": "529900AM5MG3ZZIM2K97",
    "MGKX": "529900MXE1R7K9Y0JD73", "NYNY": "5299005ZGZU03GZ3CH27", "ODDZ": "5299006EY74W072B9Y09",
    "OWN": "529900HA6N7Q7VKBT927", "PTNT": "5299007MCXKLD2XG7L85", "QJN": "529900BOR9DE0111KE06",
    "QMY": "529900ONDI0DZ714GE91", "QQJN": None, "QQMY": "529900RMCEXNXITF7468",
    "SCJN": None, "SCMY": "529900933EGLXHFNL575", "STYL": "529900IS7A2RHJU8BE34",
    "TAJX": "5299005SUQCTOPM0WQ39", "USX": "529900Q2HC5REX0SYU25", "VBX": "5299002JOA3HK6OBML25",
    "VOOX": "529900JZYO34FH878054", "WATS": "5299000RXDYZBTPHJA47", "WEBX": "5299008CZS8G5Q1TRR58",
    "WNDR": "529900PPRQAWCJHF5127", "WR": "529900YVGE1BS97J5421", "WX": "529900YCP03OWVJK6311",
    "XA": "529900XGGMJ2O5ISK933", "XAGI": "5299000N6IRUZIT5RM36", "XBIX": "529900Z8QE93POC74721",
    "XCOM": "529900FN6A9WLZR3P503", "XEUR": "529900XI1LPYX9JHD953", "XHOA": "529900B0OY0AJ5T9OG91",
    "XIWC": "529900Y7PBZIOU11ZH81", "XKRE": "529900XD00RDEFATH021", "XLBX": "529900ETZSWYZUCNMO74",
    "XLEX": "529900ZBH29CZAJ66603", "XLFX": "5299001M9O9E7DOD9G92", "XLIX": "5299005SNEPKAHWAVV81",
    "XLKX": "529900FNMZM1594W0L15", "XLPX": "529900EJG524PS36W344", "XLUX": "529900Z4R0NZQGK1ZX90",
    "XLVX": "5299008OY1LKUBM23M40", "XLYX": "529900BHH5W4PDXWFS12", "XPAV": "529900M1ILFV1EYRXX59",
    "XSEM": "5299002VLTNA1P1FDR12", "XTAI": "529900RVYA02GXO32T65", "XVO": "529900AT9VQY9MHU2K08",
    "XVUG": "529900S1PJOVSE9ONQ52", "XW": "52990025XKULJRYMF902", "YUNG": "529900SPXDBSO10DOS26",
}


def main():
    updated = lei_set = missing = 0
    for ticker, lei in BBG_LEI.items():
        cfg = FUNDS / ticker.lower() / "fund_config.txt"
        if not cfg.is_file():
            continue
        text = cfg.read_text(encoding="utf-8")
        # classId -> reference class
        text = re.sub(r"(?m)^classId=.*$", f"classId={CLASS_ID}", text)
        # seriesLei -> real Bloomberg LEI (only when available)
        if lei:
            text = re.sub(r"(?m)^seriesLei=.*$", f"seriesLei={lei}", text)
            lei_set += 1
        else:
            missing += 1
        cfg.write_text(text, encoding="utf-8")
        updated += 1
    print(f"configs updated: {updated}")
    print(f"real Bloomberg seriesLei written: {lei_set}")
    print(f"no Bloomberg LEI (kept placeholder): {missing} -> {[t for t,v in BBG_LEI.items() if v is None]}")


if __name__ == "__main__":
    main()
