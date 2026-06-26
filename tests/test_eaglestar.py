"""EagleSTAR fund-accounting extractor — unit tests over a tiny synthetic mbox.

No real client data: the fixture is generated at test time with hand-chosen numbers
so every expected output is exact. No Bloomberg/network. Period under test: 2026-06
(month-ends baseline=Mar, mon1=Apr, mon2=May, mon3=Jun).
"""
import mailbox
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pytest

from nport import eaglestar

ENT = {"900001": "TESTA", "900002": "TESTB"}


def _csv(header, rows):
    out = [",".join(header)]
    out += [",".join(str(c) for c in r) for r in rows]
    return "\n".join(out) + "\n"


# Trial Balance: only F1086 (name), F64008 (ending bal), F5 (entity) are read.
def _tb(date, balances):
    """balances: {entity: [(account_name, ending_balance), ...]}"""
    rows = []
    for ent, accts in balances.items():
        for name, end in accts:
            rows.append([name, f"{end:.2f}", ent])
    return f"Corgi_Trial_Balance_{date}.csv", _csv(["F1086", "F64008", "F5"], rows)


# Cumulative TB snapshots. net_realized = Σ realized; net_unreal = Σ unreal (excl ACCUM).
_TB_A = {
    "20260331": {"900001": [("REALIZED GAIN ON INVESTMENTS SHORT TERM", 100), ("REALIZED LOSS ON INVESTMENTS SHORT TERM", 0),
                            ("NET UNREAL APPR ON INVESTMENTS", 1000), ("ACCUM NET UNREAL APPR OF INVEST", 99999),
                            ("SUBSCRIPTIONS", 0), ("REDEMPTIONS", 0)],
                 "900002": [("NET UNREAL DEPR ON INVESTMENTS", -500)]},
    "20260430": {"900001": [("REALIZED GAIN ON INVESTMENTS SHORT TERM", 100), ("REALIZED LOSS ON INVESTMENTS SHORT TERM", -40),
                            ("NET UNREAL APPR ON INVESTMENTS", 1200), ("ACCUM NET UNREAL APPR OF INVEST", 99999),
                            ("SUBSCRIPTIONS", 10000), ("REDEMPTIONS", -2000)],
                 "900002": [("NET UNREAL DEPR ON INVESTMENTS", -500)]},
    "20260529": {"900001": [("REALIZED GAIN ON INVESTMENTS SHORT TERM", 250), ("REALIZED LOSS ON INVESTMENTS SHORT TERM", -40),
                            ("NET UNREAL APPR ON INVESTMENTS", 900), ("ACCUM NET UNREAL APPR OF INVEST", 99999),
                            ("SUBSCRIPTIONS", 10000), ("REDEMPTIONS", -3000)],
                 "900002": [("NET UNREAL DEPR ON INVESTMENTS", -700)]},
    # decoy snapshot earlier in June — code must pick the LATEST in the month (0630), not this.
    "20260628": {"900001": [("REALIZED GAIN ON INVESTMENTS SHORT TERM", 0), ("NET UNREAL APPR ON INVESTMENTS", 0),
                            ("SUBSCRIPTIONS", 0), ("REDEMPTIONS", 0)]},
    "20260630": {"900001": [("REALIZED GAIN ON INVESTMENTS SHORT TERM", 250), ("REALIZED LOSS ON INVESTMENTS SHORT TERM", -90),
                            ("NET UNREAL APPR ON INVESTMENTS", 1500), ("ACCUM NET UNREAL APPR OF INVEST", 99999),
                            ("SUBSCRIPTIONS", 15000), ("REDEMPTIONS", -3000),
                            ("ACCRUED UNITARY FEE EXPENSE", 50), ("TOTAL LIABILITIES", 50)],
                 "900002": [("NET UNREAL DEPR ON INVESTMENTS", -400),
                            ("INVESTMENT PAYABLE", 120), ("TOTAL LIABILITIES", 120)]},
}


def _pval(date):
    header = ["Investment Type Desc", "Primary Asset ID", "Issue Name", "Total Unreal G/L Base", "Entity/Sector Number"]
    rows = [
        ["Options", "2SPY  270430C00143730", "SPY 04/30/2027 143.73 C", "208376.10", "900001"],
        ["SWAPS", "218946101-TRS-01/19/28-L", "CORGI ETF TR SWAP CS", "0.00", "900001"],
        ["SWAPS", "218946101-TRS-01/19/28-L", "CORGI ETF TR SWAP CS_P", "0.00", "900001"],
        ["SWAPS", "218946101-TRS-01/19/28-L", "CORGI ETF TR SWAP CS_R", "3182194.74", "900001"],
        ["Equity", "037833100", "Apple Inc", "5000.00", "900002"],   # not a deriv -> ignored
    ]
    return f"Corgi_PVal_{date}.csv", _csv(header, rows)


def _nav(date):
    header = ["Entity Number", "NASDAQ", "Total Net Assets"]
    rows = [["900001", "TESTA", "1000000.00"], ["900002", "TESTB", "2000000.00"]]
    return f"Corgi_NAV_Sum_{date}.csv", _csv(header, rows)


def _attachments():
    atts = [_tb(d, b) for d, b in _TB_A.items()]
    atts.append(_pval("20260630"))
    atts.append(_nav("20260630"))
    # decoy non-target attachments that must be ignored
    atts.append(("Corgi_Custom_Pricing_20260630.csv", "x,y\n1,2\n"))
    return atts


def _build_mbox(path: Path):
    mb = mailbox.mbox(str(path))
    mb.lock()
    for fname, text in _attachments():
        m = EmailMessage()
        m["From"] = "EagleSTARScheduler_M8V@usbank.com"
        m["Subject"] = fname
        m.set_content("EagleSTAR export")
        m.add_attachment(text.encode("utf-8"), maintype="text", subtype="csv", filename=fname)
        mb.add(m)
    mb.flush()
    mb.unlock()


@pytest.fixture
def fixture(tmp_path):
    """Returns a namespace with .mbox, .zip, .folder for the synthetic export."""
    folder = tmp_path / "fund_accounting"
    folder.mkdir()
    mbox_path = folder / "export.mbox"
    _build_mbox(mbox_path)
    zip_path = folder / "takeout.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(mbox_path, "Mail/export.mbox")
    return type("F", (), {"mbox": mbox_path, "zip": zip_path, "folder": folder})


# ── Discovery ──────────────────────────────────────────────────

def test_resolve_export_finds_archive(fixture):
    # newest wins; both exist, zip written after mbox
    assert eaglestar.resolve_export(fixture.folder) is not None

def test_resolve_export_empty(tmp_path):
    (tmp_path / "empty").mkdir()
    assert eaglestar.resolve_export(tmp_path / "empty") is None


# ── Extraction / cache ─────────────────────────────────────────

def test_zip_and_mbox_decode_identically(fixture, tmp_path):
    ca, cb = tmp_path / "ca", tmp_path / "cb"
    eaglestar.extract_to_cache(fixture.mbox, ca)
    eaglestar.extract_to_cache(fixture.zip, cb)
    for sub in ("pval", "tb", "nav"):
        a = sorted((ca / sub).glob("*.csv"))
        b = sorted((cb / sub).glob("*.csv"))
        assert [p.name for p in a] == [p.name for p in b]
        for pa, pb in zip(a, b):
            assert pa.read_bytes() == pb.read_bytes()

def test_extract_is_idempotent(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    sentinel = cache / "tb" / "_sentinel"
    sentinel.write_text("keep")
    eaglestar.extract_to_cache(fixture.zip, cache)   # marker unchanged -> skip, no rmtree
    assert sentinel.exists()

def test_corrupt_archive_raises(tmp_path):
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("notes.txt", "no mbox here")
    with pytest.raises(ValueError):
        eaglestar.extract_to_cache(bad, tmp_path / "c")

def test_decoy_attachments_ignored(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    assert not (cache / "pricing").exists()
    assert {p.stem for p in (cache / "pval").glob("*.csv")} == {"20260630"}


# ── Maps ───────────────────────────────────────────────────────

def test_entity_ticker_map(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    assert eaglestar.entity_ticker_map(cache) == ENT

def test_derivative_values_swap_R_leg_only_and_option_direct(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    derivs, snap = eaglestar.derivative_values(cache, "2026-06", ENT)
    assert snap == "20260630"
    # option: direct; swap: the _R leg value, keyed by base Primary Asset ID; equity ignored
    assert derivs == {
        ("TESTA", "2SPY  270430C00143730"): {"unrealizedAppr": "208376.10"},
        ("TESTA", "218946101-TRS-01/19/28-L"): {"unrealizedAppr": "3182194.74"},
    }

def test_filing_values_gains_are_monthend_deltas(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    vals, liabs, as_of = eaglestar.filing_values(cache, "2026-06", ENT)
    a = vals["TESTA"]
    # net_realized cumulative: Mar100 Apr60 May210 Jun160 -> deltas -40, 150, -50
    assert a["netRealizedGainMon1"] == "-40.00"
    assert a["netRealizedGainMon2"] == "150.00"
    assert a["netRealizedGainMon3"] == "-50.00"
    # net_unreal (ACCUM excluded): Mar1000 Apr1200 May900 Jun1500 -> 200, -300, 600
    assert a["netUnrealizedApprMon1"] == "200.00"
    assert a["netUnrealizedApprMon2"] == "-300.00"
    assert a["netUnrealizedApprMon3"] == "600.00"
    assert a["amtPayOneYrOther"] == "50.00"
    assert liabs["TESTA"] == pytest.approx(50.0)
    # latest-in-month must have picked 0630, not the 0628 decoy
    assert as_of["realized_unreal_monthends"][-1] == "20260630"

def test_filing_values_second_fund(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    vals, liabs, _ = eaglestar.filing_values(cache, "2026-06", ENT)
    b = vals["TESTB"]
    # net_unreal: Mar-500 Apr-500 May-700 Jun-400 -> 0, -200, 300
    assert (b["netUnrealizedApprMon1"], b["netUnrealizedApprMon2"], b["netUnrealizedApprMon3"]) == ("0.00", "-200.00", "300.00")
    assert b["amtPayOneYrOther"] == "120.00"
    assert liabs["TESTB"] == pytest.approx(120.0)

def test_flow_values_deltas(fixture, tmp_path):
    cache = tmp_path / "c"
    eaglestar.extract_to_cache(fixture.zip, cache)
    flows = eaglestar.flow_values(cache, "2026-06", ENT)
    a = flows["TESTA"]
    # subs cumulative 0/10000/10000/15000 -> 10000, 0, 5000 ; reds 0/-2000/-3000/-3000 -> 2000,1000,0
    assert (a["mon1Sales"], a["mon2Sales"], a["mon3Sales"]) == ("10000.00", "0.00", "5000.00")
    assert (a["mon1Redemption"], a["mon2Redemption"], a["mon3Redemption"]) == ("2000.00", "1000.00", "0.00")


# ── Bundle ─────────────────────────────────────────────────────

def test_load_bundles_everything(fixture):
    data = eaglestar.load(fixture.zip, "2026-06")
    assert data.entity_ticker == ENT
    assert len(data.derivatives) == 2
    assert set(data.filing) == {"TESTA", "TESTB"}
    assert data.nav_net_assets == {"TESTA": 1000000.0, "TESTB": 2000000.0}
    assert data.as_of["pval"] == "20260630"


# ── Integration: through the real workbook builders ────────────

import csv  # noqa: E402

from nport.custodian import parse_custodian_csv  # noqa: E402
from nport.filing_master import build_filing_master, read_filing_master  # noqa: E402
from nport.master_sheet import read_master_xlsx, refresh_master  # noqa: E402

_CUST_HEADERS = ["Date", "Account", "StockTicker", "CUSIP", "SecurityName", "Shares",
                 "Price", "MarketValue", "Weightings", "NetAssets", "SharesOutstanding",
                 "CreationUnits", "MoneyMarketFlag"]


def _crow(account, ticker, cusip, name):
    return {"Date": "06/30/2026", "Account": account, "StockTicker": ticker, "CUSIP": cusip,
            "SecurityName": name, "Shares": "100", "Price": "10", "MarketValue": "1000",
            "Weightings": "1.00%", "NetAssets": "100000", "SharesOutstanding": "5000",
            "CreationUnits": "10", "MoneyMarketFlag": ""}


def _write_custodian(tmp_path):
    rows = [
        _crow("TESTA", "AAPL", "037833100", "Apple Inc"),
        _crow("TESTA", "2SPY  270430C00143730", "2SPY  270430C00143730", "SPY 04/30/2027 143.73 C"),
        _crow("TESTA", "218946101-TRS-01/19/28-L", "218946101-TRS-01/19/28-L", "CORGI ETF TR SWAP CS-L"),
        _crow("TESTB", "MSFT", "594918104", "Microsoft Corp"),
    ]
    p = tmp_path / "2026-06_holdings.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CUST_HEADERS)
        w.writeheader()
        w.writerows(rows)
    return parse_custodian_csv(p)


def _deriv_appr(master_rows):
    return {(r["Account"], r.get("ticker") or r.get("cusip")): (r.get("unrealizedAppr") or "").strip()
            for r in master_rows if (r.get("derivCat") or "").strip()}


def test_master_prefills_unrealizedAppr(fixture, tmp_path):
    eag = eaglestar.load(fixture.zip, "2026-06")
    rows = _write_custodian(tmp_path)
    sm = tmp_path / "sm.xlsx"
    refresh_master(rows, sm, None, None, formulas=False, deriv_values=eag.derivatives)
    mrows, _ = read_master_xlsx(sm)
    appr = {(r["Account"], (r.get("cusip") or "")): (r.get("unrealizedAppr") or "").strip()
            for r in mrows if (r.get("derivCat") or "").strip()}
    assert appr[("TESTA", "2SPY  270430C00143730")] == "208376.10"
    assert appr[("TESTA", "218946101-TRS-01/19/28-L")] == "3182194.74"


def test_master_empty_drop_leaves_unrealizedAppr_blank(fixture, tmp_path):
    rows = _write_custodian(tmp_path)
    sm = tmp_path / "sm.xlsx"
    refresh_master(rows, sm, None, None, formulas=False, deriv_values=None)   # no EagleSTAR
    mrows, _ = read_master_xlsx(sm)
    appr = [(r.get("unrealizedAppr") or "").strip() for r in mrows if (r.get("derivCat") or "").strip()]
    assert appr and all(v == "" for v in appr)   # additive guarantee: unchanged from today


def test_master_unrealizedAppr_refreshes_and_falls_back(fixture, tmp_path):
    eag = eaglestar.load(fixture.zip, "2026-06")
    rows = _write_custodian(tmp_path)
    sm = tmp_path / "sm.xlsx"
    key = ("TESTA", "218946101-TRS-01/19/28-L")
    # run 1: fill from EagleSTAR
    refresh_master(rows, sm, None, None, formulas=False, deriv_values=eag.derivatives)
    mrows, _ = read_master_xlsx(sm)
    assert _deriv_appr(mrows)[key] == "3182194.74"
    # run 2: no EagleSTAR -> existing value preserved (fallback)
    refresh_master(rows, sm, None, None, formulas=False, deriv_values=None)
    mrows, _ = read_master_xlsx(sm)
    assert _deriv_appr(mrows)[key] == "3182194.74"
    # run 3: new EagleSTAR value -> refreshes (authoritative, not frozen)
    refresh_master(rows, sm, None, None, formulas=False,
                   deriv_values={key: {"unrealizedAppr": "111.11"}})
    mrows, _ = read_master_xlsx(sm)
    assert _deriv_appr(mrows)[key] == "111.11"


def test_filing_master_fills_gains_and_additive(fixture, tmp_path):
    eag = eaglestar.load(fixture.zip, "2026-06")
    rows = _write_custodian(tmp_path)
    # with EagleSTAR
    fm = tmp_path / "fm.xlsx"
    build_filing_master(rows, "2026-06", fm, None, fund_acct=eag.filing)
    a = next(r for r in read_filing_master(fm) if r["Account"] == "TESTA")
    assert a["netRealizedGainMon1"] == "-40.00"
    assert a["netUnrealizedApprMon3"] == "600.00"
    assert a["amtPayOneYrOther"] == "50.00"
    # without EagleSTAR -> defaults unchanged (additive guarantee)
    fm0 = tmp_path / "fm0.xlsx"
    build_filing_master(rows, "2026-06", fm0, None, fund_acct=None)
    a0 = next(r for r in read_filing_master(fm0) if r["Account"] == "TESTA")
    assert a0["netRealizedGainMon1"] == "N/A"
    assert a0["amtPayOneYrOther"] == "0"


# ── §7d e2e: EagleSTAR values produce XSD-valid XML ────────────

from nport.builder import NportBuilder  # noqa: E402
from nport.xsd_validator import NportValidator  # noqa: E402


def test_eaglestar_unrealizedAppr_and_gains_are_xsd_valid(schema_dir, factories):
    """A swap pre-filled with EagleSTAR unrealizedAppr + filing-level gains -> valid XML."""
    config = factories.config()
    swap = factories.swap(unrealized_appr="3182194.74", val_usd="0.00", pct_val="0.00")
    filing = factories.filing(live_test_flag="LIVE", net_realized_gain_mon1="-40.00",
                              net_unrealized_appr_mon3="600.00", amt_pay_one_yr_other="50.00")
    xml = NportBuilder(config, filing, [swap]).to_xml_bytes()
    assert NportValidator(schema_dir).validate_xsd(xml) == []
    assert b"3182194.74" in xml and b"-40.00" in xml and b"600.00" in xml


def test_blank_unrealizedAppr_is_xsd_invalid(schema_dir, factories):
    """The pre-EagleSTAR state: a blank swap unrealizedAppr fails XSD (decimal required)."""
    config = factories.config()
    swap = factories.swap(unrealized_appr="", val_usd="0.00", pct_val="0.00")
    filing = factories.filing(live_test_flag="LIVE")
    xml = NportBuilder(config, filing, [swap]).to_xml_bytes()
    assert NportValidator(schema_dir).validate_xsd(xml) != []   # EagleSTAR is what fixes this


# ── §7e: reconciliation flags seeded gaps ──────────────────────

def test_reconciliation_flags_seeded_gaps(tmp_path, monkeypatch):
    from nport import cli
    monkeypatch.setattr(cli, "_MASTER_DIR", tmp_path)
    rows = _write_custodian(tmp_path)   # TESTA (equity+opt+swap), TESTB (equity)
    data = eaglestar.EagleStarData(
        filing={"TESTA": {"amtPayOneYrOther": "10.00"}},
        # swap present in custodian but absent here -> deriv_no_pval; option present
        derivatives={("TESTA", "2SPY  270430C00143730"): {"unrealizedAppr": "1.00"}},
        flows={"TESTA": {"mon1Sales": "999.00"}},          # vs AP (none) -> flow flag
        tb_total_liabs={"TESTA": 50.0},                    # vs mapped 10 -> liabilities flag
        nav_net_assets={"TESTA": 1.0},                     # vs custodian 100000 -> netAssets flag
        entity_ticker={"900001": "TESTA"},                 # TESTB unresolved -> entity flag
        as_of={"pval": "20260630", "realized_unreal_monthends": ["20260630"]},
    )
    cli._write_provenance_and_reconciliation("2026-06", rows, None, data)

    recon = list(csv.DictReader(open(tmp_path / "reconciliation_2026-06.csv", encoding="utf-8")))
    review = {r["check"] for r in recon if r["flag"] == "REVIEW"}
    checks = {r["check"] for r in recon}
    assert "netAssets" in review
    assert "liabilities" in review
    assert "flow:mon1Sales" in review
    assert "deriv_no_pval" in checks          # custodian swap with no PVal value
    assert "entity_unresolved" in checks      # TESTB has no NAV ticker
    # provenance manifest written too
    prov = list(csv.DictReader(open(tmp_path / "provenance_2026-06.csv", encoding="utf-8")))
    assert any(r["source"] == "EagleSTAR PVal" for r in prov)
