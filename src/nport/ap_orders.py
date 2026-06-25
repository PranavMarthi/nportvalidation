"""AP creation/redemption order book → per-fund monthly capital flows.

The issuer's authorized-participant order export (one row per CREATE/REDEEM order)
is the source for N-PORT Part B.2 gross flows: ``monXSales`` = value of shares sold
(creations), ``monXRedemption`` = value of shares redeemed. ``Notional`` is the
per-order dollar value (in-kind and cash alike). Reinvestment (DRIP) is *not* in an
order book and stays elsewhere.

Aggregation is deterministic: sum ``Notional`` by fund × reporting month × side over
``ACCEPTED`` orders only. Months align with the filing master's reporting period
(mon1 = period month − 2 … mon3 = the report month).
"""
import csv
from dataclasses import dataclass
from pathlib import Path

# Reporting-period month order: mon1 earliest … mon3 = the report month.
_FLOW_MONTHS = ("mon1", "mon2", "mon3")


@dataclass
class ApOrder:
    ticker: str
    side: str          # CREATE / REDEEM
    trade_date: str    # raw M/D/YYYY
    notional: str
    status: str        # ACCEPTED / CANCELLED


def _fnum(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _year_month(trade_date: str) -> str | None:
    """'M/D/YYYY' -> 'YYYY-MM' (None if unparseable)."""
    parts = (trade_date or "").split("/")
    if len(parts) != 3:
        return None
    try:
        m, _d, y = (int(p) for p in parts)
    except ValueError:
        return None
    return f"{y:04d}-{m:02d}"


def _period_months(period: str) -> list[str]:
    """The 3 reporting-period months as 'YYYY-MM', chronological (mon1 … mon3)."""
    y, m = int(period[:4]), int(period[5:7])
    out: list[str] = []
    for back in (2, 1, 0):
        yy, mm = y, m - back
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def parse_ap_orders(path: Path) -> list[ApOrder]:
    """Read the AP order book CSV into ApOrder rows (header-named columns)."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return [
            ApOrder(
                ticker=(r.get("Ticker") or "").strip(),
                side=(r.get("Side") or "").strip().upper(),
                trade_date=(r.get("Trade Date") or "").strip(),
                notional=(r.get("Notional") or "").strip(),
                status=(r.get("Status") or "").strip().upper(),
            )
            for r in reader
        ]


def aggregate_flows(orders: list[ApOrder], period: str) -> dict[str, dict[str, str]]:
    """Sum Notional by ticker × reporting month × side (ACCEPTED only).

    Returns ``{TICKER: {mon1Sales, mon1Redemption, ... mon3Reinvestment}}`` with
    2dp string dollar values; months/funds with no activity are "0". CREATE → Sales,
    REDEEM → Redemption. Reinvestment is always "0" (no feed in an order book).
    """
    months = _period_months(period)          # ['YYYY-MM' (mon1) … (mon3)]
    month_idx = {ym: _FLOW_MONTHS[i] for i, ym in enumerate(months)}

    sums: dict[str, dict[str, float]] = {}
    for o in orders:
        if o.status != "ACCEPTED":
            continue
        mon = month_idx.get(_year_month(o.trade_date))
        if mon is None:
            continue
        if o.side == "CREATE":
            field = f"{mon}Sales"
        elif o.side == "REDEEM":
            field = f"{mon}Redemption"
        else:
            continue
        sums.setdefault(o.ticker.upper(), {})
        sums[o.ticker.upper()][field] = sums[o.ticker.upper()].get(field, 0.0) + _fnum(o.notional)

    out: dict[str, dict[str, str]] = {}
    for ticker, fld in sums.items():
        rec: dict[str, str] = {}
        for mon in _FLOW_MONTHS:
            rec[f"{mon}Sales"] = f"{fld.get(f'{mon}Sales', 0.0):.2f}"
            rec[f"{mon}Redemption"] = f"{fld.get(f'{mon}Redemption', 0.0):.2f}"
            rec[f"{mon}Reinvestment"] = "N/A"   # reinvested distributions: no feed in an order book
        out[ticker] = rec
    return out


def flows_from_csv(path: Path, period: str) -> dict[str, dict[str, str]]:
    return aggregate_flows(parse_ap_orders(Path(path)), period)
