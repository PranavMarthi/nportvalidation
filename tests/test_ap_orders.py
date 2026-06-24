"""Tests for the AP creation/redemption order book → capital flows."""

from nport.ap_orders import (
    ApOrder,
    _period_months,
    _year_month,
    aggregate_flows,
    flows_from_csv,
    parse_ap_orders,
)


def _o(ticker, side, date, notional, status="ACCEPTED"):
    return ApOrder(ticker=ticker, side=side, trade_date=date,
                   notional=notional, status=status)


def test_year_month():
    assert _year_month("12/29/2025") == "2025-12"
    assert _year_month("1/6/2026") == "2026-01"
    assert _year_month("") is None
    assert _year_month("bad") is None


def test_period_months():
    assert _period_months("2026-06") == ["2026-04", "2026-05", "2026-06"]
    assert _period_months("2026-01") == ["2025-11", "2025-12", "2026-01"]


def test_aggregate_create_redeem_by_month():
    orders = [
        _o("FDRS", "CREATE", "4/10/2026", "1000"),
        _o("FDRS", "CREATE", "4/20/2026", "500"),    # same month → summed
        _o("FDRS", "REDEEM", "5/3/2026", "300"),
        _o("fdrs", "CREATE", "6/1/2026", "200"),      # lowercase ticker folds in
    ]
    flows = aggregate_flows(orders, "2026-06")
    f = flows["FDRS"]
    assert f["mon1Sales"] == "1500.00"        # April creations
    assert f["mon1Redemption"] == "0.00"
    assert f["mon2Redemption"] == "300.00"    # May redemption
    assert f["mon2Sales"] == "0.00"
    assert f["mon3Sales"] == "200.00"         # June creation
    assert f["mon1Reinvestment"] == "0"       # never sourced from an order book


def test_aggregate_excludes_cancelled_and_out_of_period():
    orders = [
        _o("AAA", "CREATE", "6/1/2026", "999", status="CANCELLED"),  # dropped
        _o("AAA", "CREATE", "1/1/2026", "777"),                       # out of period
        _o("AAA", "CREATE", "6/2/2026", "10"),
    ]
    flows = aggregate_flows(orders, "2026-06")
    assert flows["AAA"]["mon3Sales"] == "10.00"
    # cancelled + out-of-period contribute nothing
    assert flows["AAA"]["mon1Sales"] == "0.00"


def test_notional_blank_and_commas():
    orders = [
        _o("BBB", "CREATE", "6/1/2026", ""),          # blank → 0
        _o("BBB", "CREATE", "6/2/2026", "1,234.50"),  # comma-formatted
    ]
    flows = aggregate_flows(orders, "2026-06")
    assert flows["BBB"]["mon3Sales"] == "1234.50"


def test_parse_and_flows_from_csv(tmp_path):
    p = tmp_path / "orders.csv"
    p.write_text(
        "Ticker,Side,Trade Date,Notional,Status\n"
        "FDRS,CREATE,6/1/2026,1000,ACCEPTED\n"
        "FDRS,REDEEM,6/2/2026,400,ACCEPTED\n"
        "FDRS,CREATE,6/3/2026,50,CANCELLED\n",
        encoding="utf-8",
    )
    orders = parse_ap_orders(p)
    assert len(orders) == 3 and orders[0].ticker == "FDRS"
    flows = flows_from_csv(p, "2026-06")
    assert flows["FDRS"]["mon3Sales"] == "1000.00"
    assert flows["FDRS"]["mon3Redemption"] == "400.00"
