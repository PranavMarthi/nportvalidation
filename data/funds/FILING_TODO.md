# Filing source map — where every field comes from

Sources: **BBG** = Bloomberg MCP, **CUST** = custodian CSV, **AP** = AP creation/redemption
order book (`build-filing-master --ap-orders`), **EDGAR** = SEC filings/datasets,
**ACCT** = fund accounting (no feed — manual), **CONST** = constant/computed.
The security data (master → per-fund security_master.csv) is already generated & traceable.

## 1. fund_config.txt
| field | source | note |
|---|---|---|
| seriesLei | **BBG** | `LEGAL_ENTITY_IDENTIFIER` — done (85/90 real; 5 not-yet-issued) |
| seriesName | **EDGAR** (automated) | real registered name from filing headers (`scripts/backfill_series_ids.py`) |
| seriesId | **EDGAR** (automated) | from filing-header `<SERIES-ID>`, matched to ticker via Bloomberg `LONG_COMP_NAME` — 89/90 (GPTZ unmatched, needs manual) |
| classId | **EDGAR** (automated) | real per-fund `<CLASS-CONTRACT-ID>` from the same header (89/90) |
| cik, regCik | EDGAR | trust CIK 0002078265 (shared, trust-level) |
| regName | EDGAR | "Corgi ETF Trust I" (trust-level) |
| regFileNumber | EDGAR | 811-24117 (trust-level) |
| regLei | EDGAR/GLEIF | TRUST lei 529900HSQC73ZP7RGT16 ≠ seriesLei (trust-level) |
| regStreet1/2, regCity, regState, regCountry, regZip, regPhone | EDGAR/ACCT | trust cover-page address (trust-level) |
| signerOrg, signerName, signerTitle | ACCT/EDGAR | signature block (trust-level) |
| ccc | **manual** | confidential EDGAR filer code — not in any feed |

→ `seriesLei` Bloomberg; `seriesId`/`classId`/`seriesName` now **EDGAR-automated** (89/90); the rest is the EDGAR trust block (set once, shared) + manual `ccc`.

## 2. filing_data.txt (filings/2026-06/)
| field(s) | source | note |
|---|---|---|
| submissionType, liveTestFlag, isFinalFiling | **CONST** | NPORT-P / TEST / N |
| repPdEnd, repPdDate | **CONST/computed** | period-end date |
| dateSigned | manual | date after period end |
| netAssets | **CUST** | NetAssets column (done) |
| totAssets, totLiabs | **CUST (computed)** | totLiabs = Σ\|neg MV\|; totAssets = net+liabs (done) |
| rtn1-3 | **BBG** (approx) or ACCT | monthly NAV total return (historical_data); fund acctg authoritative |
| netRealizedGainMon1-3, netUnrealizedApprMon1-3 | **ACCT only** | not in BBG/custodian/AP (needs cost basis) |
| mon1-3 Sales/Redemption | **AP** (automated) | Σ `Notional` of CREATE/REDEEM (ACCEPTED) by month — `--ap-orders` |
| mon1-3 Reinvestment | **ACCT** | DRIP/reinvested distributions — not in an order book |
| nameDesignatedIndex, indexIdentifier | **BBG** (automated) | broad-based index = `FUND_BENCHMARK_PRIM` → resolved name (`_DESIGNATED_INDEX` in filing_master). 84/90; FDRX (proprietary FDRI) + 5 no-benchmark stay N/A. Verify vs 497K |
| amtPay*/delayDeliv/standByCommit/liquidPref/assetsAttr*/assetsInvested/isNonCashCollateral | **CONST/ACCT** | 0/N default for plain ETFs |
| cur_metrics_json, credit_sprd_risk_*_json (B.3) | **BBG** (approx, automated) | debt funds: per-holding `DUR_ADJ_MID`/`OAS_SPREAD_DUR_MID` × MV, bucketed by maturity (`risk` sheet). Admin risk engine authoritative |

→ CUST gives net/total assets; BBG gives monthly returns + B.3 risk (approx); **AP order book gives gross Sales/Redemption**; **realized/unrealized gains + reinvestment remain fund-accounting-only**; rest is constant/EDGAR. Set `liveTestFlag=LIVE` only at the very end.

## 3. Derivative economics — funds holding options/swaps
**Counterparty + LEI now resolved automatically** (no longer manual):
  * Swaps: custodian counterparty code (CANT/CLST/CS/MREX) → legal name + GLEIF LEI (constant map in `custodian.py`)
  * Options: OCC central counterparty (`The Options Clearing Corporation`, LEI 549300CII6SLYGKNHA04)

Still manual — enter in the MASTER (option/swap rows), then re-run split-master. Not in any feed:
  * Options: **delta** (FLEX options don't price on Bloomberg)
  * Swaps:   **notionalAmt, unrealizedAppr** (broker/admin confirms; for a TRS the custodian MV may equal unrealizedAppr — confirm)

| fund | options | swaps |
|---|---|---|
| brzx | 0 | 1 |
| buffered_etf | 8 | 0 |
| ccpx | 0 | 1 |
| cjun | 4 | 0 |
| cmag | 0 | 7 |
| cmay | 4 | 0 |
| ctjn | 4 | 0 |
| ctma | 4 | 0 |
| emjn | 4 | 0 |
| emmy | 4 | 0 |
| emxx | 0 | 1 |
| euvx | 0 | 1 |
| fdrx | 0 | 1 |
| hjun | 3 | 0 |
| hmay | 3 | 0 |
| idjn | 4 | 0 |
| idmy | 4 | 0 |
| junc | 4 | 0 |
| krwx | 0 | 2 |
| leveraged_etf | 0 | 3 |
| mayc | 6 | 0 |
| mgkx | 0 | 1 |
| qjn | 4 | 0 |
| qmy | 4 | 0 |
| qqjn | 4 | 0 |
| qqmy | 4 | 0 |
| scjn | 4 | 0 |
| scmy | 4 | 0 |
| tajx | 0 | 1 |
| usx | 0 | 1 |
| vbx | 0 | 1 |
| voox | 0 | 1 |
| webx | 0 | 1 |
| wx | 0 | 1 |
| xagi | 0 | 1 |
| xbix | 0 | 1 |
| xcom | 0 | 1 |
| xeur | 0 | 1 |
| xhoa | 0 | 1 |
| xiwc | 0 | 1 |
| xkre | 0 | 1 |
| xlbx | 0 | 1 |
| xlex | 0 | 1 |
| xlfx | 0 | 1 |
| xlix | 0 | 1 |
| xlkx | 0 | 1 |
| xlpx | 0 | 1 |
| xlux | 0 | 1 |
| xlvx | 0 | 1 |
| xlyx | 0 | 1 |
| xpav | 0 | 1 |
| xsem | 0 | 1 |
| xtai | 0 | 1 |
| xvo | 0 | 1 |
| xvug | 0 | 1 |
| xw | 0 | 1 |
