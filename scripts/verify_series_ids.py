"""Independently verify every fund's seriesId/classId against SEC primary documents.

Does NOT reuse the Bloomberg name-match that created the mapping. Instead it reads
the trust's per-fund 497K summary prospectuses, each of which ties a ticker to a
series two ways:
  * the document FILENAME — "Corgi_497K_<TICKER>.htm"
  * the SGML header       — <SERIES-ID>/<CLASS-CONTRACT-ID>/<SERIES-NAME>
Then it compares that authoritative ticker -> (seriesId, classId) to each
fund_config.txt. Any disagreement is a real problem.

Run:  uv run python scripts/verify_series_ids.py
"""
import re
import sys
from pathlib import Path

from nport.edgar import EdgarClient, parse_series_blocks

CIK = "0002078265"
UA = "Corgi ETF Trust nport-tool@example.com"
FUNDS = Path("data/funds")
_ARCH = "https://www.sec.gov/Archives/edgar/data/2078265"


def _ticker_in_filename(doc: str, valid: set[str]) -> str | None:
    """The single known ticker appearing (word-bounded) in a 497K filename, else None."""
    # Normalize the form marker so a ticker glued to "497k" (corgi497kCJUN) is bounded.
    name = re.sub(r"497[kK]|buffer|corgi|etftrust1?", "_", doc or "", flags=re.I)
    hits = {t for t in valid if re.search(rf"(?<![A-Za-z]){t}(?![A-Za-z])", name, re.I)}
    return next(iter(hits)) if len(hits) == 1 else None


def authoritative_map(valid: set[str]) -> dict[str, dict]:
    """ticker (upper) -> {seriesId, classId, seriesName} from 497K filename + header."""
    c = EdgarClient(UA)
    out: dict[str, dict] = {}
    for f in c.list_filings(CIK, forms={"497K"}, count=400):
        ticker = _ticker_in_filename(f.primary_document or "", valid)
        if not ticker or ticker in out:
            continue  # unknown/ambiguous filename, or most-recent already taken
        acc = f.accession_number
        url = f"{_ARCH}/{acc.replace('-', '')}/{acc}.txt"
        try:
            header = c._get(url, max_bytes=60000).decode("utf-8", "replace")
        except ConnectionError:
            continue
        series = parse_series_blocks(header)
        if len(series) == 1 and series[0].classes:
            s = series[0]
            out[ticker] = {
                "seriesId": s.series_id,
                "classId": s.classes[0][0],
                "seriesName": s.series_name,
            }
    return out


def config_value(fund_dir: Path, key: str) -> str:
    m = re.search(rf"(?m)^{key}=(.*)$", (fund_dir / "fund_config.txt").read_text(encoding="utf-8"))
    return m.group(1).strip() if m else ""


def main() -> None:
    valid = {d.name.upper() for d in FUNDS.iterdir()
             if (d / "fund_config.txt").is_file() and d.name not in
             ("bond_fund", "buffered_etf", "leveraged_etf")}
    print("Building authoritative ticker->seriesId from SEC 497K filings ...")
    auth = authoritative_map(valid)
    print(f"  {len(auth)} tickers resolved from 497K filenames + headers.\n")

    fix_names = "--fix-names" in sys.argv
    ok, mism, no_auth, blank, name_diffs = [], [], [], [], []
    for d in sorted(FUNDS.iterdir()):
        if not (d / "fund_config.txt").is_file():
            continue
        ticker = d.name.upper()
        our_sid = config_value(d, "seriesId")
        our_cid = config_value(d, "classId")
        a = auth.get(ticker)
        if not our_sid:
            blank.append(ticker)
        elif not a:
            no_auth.append(ticker)
        elif a["seriesId"] == our_sid and a["classId"] == our_cid:
            ok.append(ticker)
            # IDs correct — reconcile the (cosmetic) seriesName to the SEC-current name.
            if config_value(d, "seriesName") != a["seriesName"]:
                name_diffs.append((ticker, config_value(d, "seriesName"), a["seriesName"]))
                if fix_names:
                    cfg = d / "fund_config.txt"
                    cfg.write_text(re.sub(r"(?m)^seriesName=.*$",
                                          f"seriesName={a['seriesName']}",
                                          cfg.read_text(encoding="utf-8")), encoding="utf-8")
        else:
            mism.append((ticker, our_sid, our_cid, a["seriesId"], a["classId"], a["seriesName"]))

    print(f"✓ seriesId+classId MATCH SEC primary docs: {len(ok)}/{len(ok)+len(mism)+len(no_auth)+len(blank)}")
    if mism:
        print(f"\n✗ ID MISMATCH ({len(mism)}) — our config disagrees with the SEC 497K:")
        for t, osid, ocid, asid, acid, an in mism:
            print(f"  {t}: ours={osid}/{ocid}  SEC={asid}/{acid}  ({an})")
    if name_diffs:
        verb = "FIXED" if fix_names else "stale (run --fix-names to update)"
        print(f"\n· seriesName differs from SEC-current — {verb} ({len(name_diffs)}):")
        for t, old, new in name_diffs:
            print(f"  {t}: {old!r} -> {new!r}")
    if blank:
        print(f"\n· blank seriesId in config ({len(blank)}): {blank}")
    if no_auth:
        print(f"\n· no 497K found to cross-check ({len(no_auth)}): {no_auth}")


if __name__ == "__main__":
    main()
