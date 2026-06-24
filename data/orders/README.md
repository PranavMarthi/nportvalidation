# AP order book drop folder

Save your authorized-participant creation/redemption order export here, named by reporting period:

```
data/orders/2026-06_orders.csv
```

`nport masters` finds it automatically and fills each fund's monthly capital flows
(`monXSales` = CREATE orders, `monXRedemption` = REDEEM orders, summed by `Notional`,
ACCEPTED only). It's optional — without it, flows are left at 0.

Required columns: `Ticker`, `Side` (CREATE/REDEEM), `Trade Date`, `Notional`, `Status`.
